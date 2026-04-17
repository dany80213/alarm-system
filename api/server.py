import json
import logging
import hashlib
import secrets
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger(__name__)

WEB_DIR   = Path(__file__).parent.parent / "web"
USERS_PATH = Path(__file__).parent.parent / "config" / "users.json"

VALID_TYPES  = {"door", "window", "motion", "gate", "controller"}
VALID_ZONES  = {"perimeter", "internal"}
VALID_LEVELS = {10, 50, 100}

# ─── In-memory auth state ─────────────────────────────────────────────────────
_sessions: dict = {}    # token -> {"username": str, "level": int}
_listening: bool = True  # accept / process unknown devices


# ─── Pydantic models ──────────────────────────────────────────────────────────
class CommandRequest(BaseModel):
    action: str

class DismissRequest(BaseModel):
    code: str

class DismissBridgeRequest(BaseModel):
    topic: str

class DevicePosition(BaseModel):
    x: float
    y: float

class AddDeviceRequest(BaseModel):
    code: str
    name: str
    type: str
    zone: str
    position: DevicePosition

class UpdateDeviceRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    zone: Optional[str] = None
    position: Optional[DevicePosition] = None
    enabled: Optional[bool] = None

class AddBridgeRequest(BaseModel):
    client: str
    topic: str
    position: DevicePosition

class UpdateBridgeRequest(BaseModel):
    client: Optional[str] = None
    position: Optional[DevicePosition] = None
    enabled: Optional[bool] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreateRequest(BaseModel):
    username: str
    password: str
    level: int

class UserUpdateRequest(BaseModel):
    password: Optional[str] = None
    level: Optional[int] = None


# ─── Auth helpers ─────────────────────────────────────────────────────────────
def _hash(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()

def _load_users() -> dict:
    if USERS_PATH.exists():
        with open(USERS_PATH) as f:
            return json.load(f)
    return {}

def _save_users(users: dict):
    USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(USERS_PATH, "w") as f:
        json.dump(users, f, indent=2)

def _auth(authorization: Optional[str], min_level: int = 10) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Non autenticato")
    token = authorization.split(" ", 1)[1]
    sess = _sessions.get(token)
    if not sess:
        raise HTTPException(status_code=401, detail="Sessione non valida")
    if sess["level"] < min_level:
        raise HTTPException(status_code=403, detail="Permessi insufficienti")
    return sess


# ─── App factory ──────────────────────────────────────────────────────────────
def create_app(state_manager, event_engine) -> FastAPI:
    global _listening

    app = FastAPI(title="Home Alarm System API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )

    @app.middleware("http")
    async def no_cache_api(request: Request, call_next):
        response = await call_next(request)
        # Impedisci al browser di cachare le risposte API
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        return response

    # ── Auth ──────────────────────────────────────────────────────────────────

    @app.post("/auth/login")
    def login(req: LoginRequest):
        users = _load_users()
        user = users.get(req.username)
        if not user or user["password"] != _hash(req.password):
            raise HTTPException(status_code=401, detail="Credenziali non valide")
        token = secrets.token_hex(32)
        _sessions[token] = {"username": req.username, "level": user["level"]}
        return {"token": token, "username": req.username, "level": user["level"]}

    @app.post("/auth/logout")
    def logout(authorization: Optional[str] = Header(None)):
        if authorization and authorization.startswith("Bearer "):
            _sessions.pop(authorization[7:], None)
        return {"ok": True}

    @app.get("/auth/me")
    def me(authorization: Optional[str] = Header(None)):
        sess = _auth(authorization, 10)
        return {"username": sess["username"], "level": sess["level"]}

    # ── State & events ────────────────────────────────────────────────────────

    @app.get("/state")
    def get_state(authorization: Optional[str] = Header(None)):
        _auth(authorization, 10)
        return state_manager.get_state()

    @app.get("/devices")
    def get_devices(authorization: Optional[str] = Header(None)):
        _auth(authorization, 10)
        return state_manager.get_devices()

    @app.get("/events")
    def get_events(limit: int = 50, authorization: Optional[str] = Header(None)):
        _auth(authorization, 10)
        if limit < 1 or limit > 500:
            raise HTTPException(status_code=400, detail="limit deve essere tra 1 e 500")
        return state_manager.get_events(limit)

    @app.post("/command")
    def post_command(req: CommandRequest, authorization: Optional[str] = Header(None)):
        _auth(authorization, 50)
        payload = json.dumps({"action": req.action}).encode()
        event_engine.process_command(payload)
        return {"ok": True, "state": state_manager.get_state()}

    # ── Unknown devices ───────────────────────────────────────────────────────

    @app.get("/unknown")
    def get_unknown(authorization: Optional[str] = Header(None)):
        _auth(authorization, 10)
        return state_manager.get_unknown_devices()

    @app.post("/unknown/dismiss")
    def dismiss_unknown(req: DismissRequest, authorization: Optional[str] = Header(None)):
        _auth(authorization, 50)
        state_manager.dismiss_unknown_device(req.code.upper())
        return {"ok": True}

    # ── Devices CRUD ──────────────────────────────────────────────────────────

    @app.post("/devices/add")
    def add_device(req: AddDeviceRequest, authorization: Optional[str] = Header(None)):
        _auth(authorization, 100)
        code = req.code.upper()
        if req.type not in VALID_TYPES:
            raise HTTPException(status_code=400, detail=f"Tipo non valido: {req.type}")
        if req.zone not in VALID_ZONES:
            raise HTTPException(status_code=400, detail=f"Zona non valida: {req.zone}")
        if not req.name.strip():
            raise HTTPException(status_code=400, detail="Nome obbligatorio")
        devices = state_manager.get_devices()
        if code in devices:
            raise HTTPException(status_code=409, detail="Dispositivo già presente")
        device_data = {
            "name": req.name.strip(),
            "type": req.type,
            "zone": req.zone,
            "position": {"x": req.position.x, "y": req.position.y},
        }
        state_manager.add_device(code, device_data)
        topics = state_manager._settings["topics"]
        event_engine._publish(topics["devices_added"], {"code": code, **device_data})
        logger.info(f"Nuovo dispositivo aggiunto via API: {code}")
        return {"ok": True, "code": code, "device": device_data}

    @app.put("/devices/{code}")
    def update_device(
        code: str,
        req: UpdateDeviceRequest,
        authorization: Optional[str] = Header(None),
    ):
        _auth(authorization, 100)
        code = code.upper()
        devices = state_manager.get_devices()
        if code not in devices:
            raise HTTPException(status_code=404, detail="Dispositivo non trovato")
        updates = {}
        if req.name is not None:
            if not req.name.strip():
                raise HTTPException(status_code=400, detail="Nome obbligatorio")
            updates["name"] = req.name.strip()
        if req.type is not None:
            if req.type not in VALID_TYPES:
                raise HTTPException(status_code=400, detail=f"Tipo non valido: {req.type}")
            updates["type"] = req.type
        if req.zone is not None:
            if req.zone not in VALID_ZONES:
                raise HTTPException(status_code=400, detail=f"Zona non valida: {req.zone}")
            updates["zone"] = req.zone
        if req.position is not None:
            updates["position"] = {"x": req.position.x, "y": req.position.y}
        if req.enabled is not None:
            updates["enabled"] = req.enabled
        state_manager.update_device(code, updates)
        return {"ok": True, "code": code, "device": state_manager.get_devices()[code]}

    @app.delete("/devices/{code}")
    def delete_device(code: str, authorization: Optional[str] = Header(None)):
        _auth(authorization, 100)
        code = code.upper()
        if code not in state_manager.get_devices():
            raise HTTPException(status_code=404, detail="Dispositivo non trovato")
        state_manager.remove_device(code)
        return {"ok": True}

    # ── Bridges CRUD ──────────────────────────────────────────────────────────

    @app.get("/bridges")
    def get_bridges(authorization: Optional[str] = Header(None)):
        _auth(authorization, 10)
        return state_manager.get_bridges()

    @app.post("/bridges")
    def add_bridge(req: AddBridgeRequest, authorization: Optional[str] = Header(None)):
        _auth(authorization, 100)
        topic = req.topic.strip()
        rf_prefix = state_manager._settings["topics"]["input_rf"].rstrip("/#")
        if not topic.startswith(rf_prefix + "/"):
            raise HTTPException(
                status_code=400,
                detail=f"Il topic deve iniziare con '{rf_prefix}/'",
            )
        if not req.client.strip():
            raise HTTPException(status_code=400, detail="Il campo client è obbligatorio")
        bridges = state_manager.get_bridges()
        if topic in bridges:
            raise HTTPException(status_code=409, detail="Bridge già registrato")
        bridge_data = {
            "client": req.client.strip(),
            "topic": topic,
            "position": {"x": req.position.x, "y": req.position.y},
            "enabled": True,
        }
        state_manager.add_bridge(topic, bridge_data)
        # Dismiss dalla lista sconosciuti se presente
        state_manager.dismiss_unknown_bridge(topic)
        logger.info(f"Bridge aggiunto via API: {topic}")
        return {"ok": True, "topic": topic, "bridge": bridge_data}

    @app.put("/bridges/{encoded_topic:path}")
    def update_bridge(
        encoded_topic: str,
        req: UpdateBridgeRequest,
        authorization: Optional[str] = Header(None),
    ):
        _auth(authorization, 100)
        topic = unquote(encoded_topic)
        bridges = state_manager.get_bridges()
        if topic not in bridges:
            raise HTTPException(status_code=404, detail="Bridge non trovato")
        updates = {}
        if req.client is not None:
            if not req.client.strip():
                raise HTTPException(status_code=400, detail="Il campo client è obbligatorio")
            updates["client"] = req.client.strip()
        if req.position is not None:
            updates["position"] = {"x": req.position.x, "y": req.position.y}
        if req.enabled is not None:
            updates["enabled"] = req.enabled
        state_manager.update_bridge(topic, updates)
        return {"ok": True, "topic": topic, "bridge": state_manager.get_bridges()[topic]}

    @app.delete("/bridges/{encoded_topic:path}")
    def delete_bridge(encoded_topic: str, authorization: Optional[str] = Header(None)):
        _auth(authorization, 100)
        topic = unquote(encoded_topic)
        if topic not in state_manager.get_bridges():
            raise HTTPException(status_code=404, detail="Bridge non trovato")
        state_manager.remove_bridge(topic)
        return {"ok": True}

    # ── Unknown bridges ───────────────────────────────────────────────────────

    @app.get("/unknown-bridges")
    def get_unknown_bridges(authorization: Optional[str] = Header(None)):
        _auth(authorization, 10)
        return state_manager.get_unknown_bridges()

    @app.post("/unknown-bridges/dismiss")
    def dismiss_unknown_bridge(req: DismissBridgeRequest, authorization: Optional[str] = Header(None)):
        _auth(authorization, 50)
        state_manager.dismiss_unknown_bridge(req.topic)
        return {"ok": True}

    # ── Listening mode ────────────────────────────────────────────────────────

    @app.get("/listening")
    def get_listening(authorization: Optional[str] = Header(None)):
        _auth(authorization, 10)
        return {"active": _listening}

    @app.post("/listening/toggle")
    def toggle_listening(authorization: Optional[str] = Header(None)):
        global _listening
        _auth(authorization, 100)
        _listening = not _listening
        logger.info(f"Listening mode: {_listening}")
        return {"active": _listening}

    # ── Users management ──────────────────────────────────────────────────────

    @app.get("/users")
    def get_users(authorization: Optional[str] = Header(None)):
        _auth(authorization, 100)
        users = _load_users()
        return [{"username": u, "level": d["level"]} for u, d in users.items()]

    @app.post("/users")
    def create_user(req: UserCreateRequest, authorization: Optional[str] = Header(None)):
        _auth(authorization, 100)
        if req.level not in VALID_LEVELS:
            raise HTTPException(status_code=400, detail="Livello non valido (10, 50, 100)")
        if not req.username.strip():
            raise HTTPException(status_code=400, detail="Username obbligatorio")
        if not req.password:
            raise HTTPException(status_code=400, detail="Password obbligatoria")
        users = _load_users()
        if req.username in users:
            raise HTTPException(status_code=409, detail="Utente già presente")
        users[req.username] = {"password": _hash(req.password), "level": req.level}
        _save_users(users)
        return {"ok": True, "username": req.username, "level": req.level}

    @app.put("/users/{username}")
    def update_user(
        username: str,
        req: UserUpdateRequest,
        authorization: Optional[str] = Header(None),
    ):
        sess = _auth(authorization, 100)
        users = _load_users()
        if username not in users:
            raise HTTPException(status_code=404, detail="Utente non trovato")
        if req.password is not None:
            if not req.password:
                raise HTTPException(status_code=400, detail="Password non può essere vuota")
            users[username]["password"] = _hash(req.password)
        if req.level is not None:
            if req.level not in VALID_LEVELS:
                raise HTTPException(status_code=400, detail="Livello non valido")
            if username == sess["username"] and req.level < sess["level"]:
                raise HTTPException(status_code=400, detail="Non puoi ridurre il tuo livello")
            users[username]["level"] = req.level
            for s in _sessions.values():
                if s["username"] == username:
                    s["level"] = req.level
        _save_users(users)
        return {"ok": True, "username": username, "level": users[username]["level"]}

    @app.delete("/users/{username}")
    def delete_user(username: str, authorization: Optional[str] = Header(None)):
        sess = _auth(authorization, 100)
        if username == sess["username"]:
            raise HTTPException(status_code=400, detail="Non puoi eliminare il tuo account")
        users = _load_users()
        if username not in users:
            raise HTTPException(status_code=404, detail="Utente non trovato")
        del users[username]
        _save_users(users)
        to_remove = [t for t, s in _sessions.items() if s["username"] == username]
        for t in to_remove:
            del _sessions[t]
        return {"ok": True}

    # ── Static files (web UI) ─────────────────────────────────────────────────
    if WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")

    return app
