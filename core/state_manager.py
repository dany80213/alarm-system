import json
import time
import threading
import logging
from collections import deque
from pathlib import Path

logger = logging.getLogger(__name__)

VALID_MODES = {"DISARMED", "ARMING", "ARMED_HOME", "ARMED_AWAY", "TRIGGERED", "ENTERING"}


class StateManager:
    def __init__(self, settings: dict, devices: dict, devices_path=None,
                 bridges: dict = None, bridges_path=None):
        self._lock = threading.Lock()
        self._settings = settings
        self._devices = devices
        self._devices_path = Path(devices_path) if devices_path else None
        self._bridges = bridges if bridges is not None else {}
        self._bridges_path = Path(bridges_path) if bridges_path else None
        self._unknown_devices: list = []   # [{code, time}, ...]
        self._unknown_bridges: list = []   # [{topic, time}, ...]

        self._mode = "DISARMED"
        self._alarm = False
        self._triggered_device = None
        self._last_change = time.time()
        self._arming_target = None
        self._arming_timer = None
        self._entry_timer = None
        self._entry_generation = 0

        max_events = settings.get("max_events", 200)
        self._events = deque(maxlen=max_events)

        log_path = Path(settings.get("log_file", "logs/events.log"))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_file = log_path

    # ─── Lettura stato ────────────────────────────────────────────────────────

    def get_state(self) -> dict:
        with self._lock:
            return self._state_dict()

    def _state_dict(self) -> dict:
        return {
            "mode": self._mode,
            "alarm": self._alarm,
            "triggered_device": self._triggered_device,
            "last_change": self._last_change,
            "arming_target": self._arming_target,
        }

    def get_devices(self) -> dict:
        return self._devices

    # ─── Dispositivi sconosciuti ─────────────────────────────────────────────

    def add_unknown_device(self, code: str):
        with self._lock:
            if not any(d["code"] == code for d in self._unknown_devices):
                self._unknown_devices.append({"code": code, "time": time.time()})
                logger.info(f"Dispositivo sconosciuto in coda: {code}")

    def get_unknown_devices(self) -> list:
        with self._lock:
            return list(self._unknown_devices)

    def dismiss_unknown_device(self, code: str):
        with self._lock:
            self._unknown_devices = [d for d in self._unknown_devices if d["code"] != code]

    # ─── CRUD dispositivi ─────────────────────────────────────────────────────

    def add_device(self, code: str, data: dict):
        with self._lock:
            self._devices[code] = data
            self._unknown_devices = [d for d in self._unknown_devices if d["code"] != code]
            self._save_devices()

    def remove_device(self, code: str):
        with self._lock:
            if code in self._devices:
                del self._devices[code]
                self._save_devices()

    def update_device(self, code: str, updates: dict) -> bool:
        with self._lock:
            if code not in self._devices:
                return False
            if "position" in updates:
                self._devices[code]["position"] = updates.pop("position")
            self._devices[code].update(updates)
            self._save_devices()
            return True

    def _save_devices(self):
        if self._devices_path:
            try:
                with open(self._devices_path, "w") as f:
                    json.dump(self._devices, f, indent=2)
                logger.info(f"Dispositivi salvati in {self._devices_path}")
            except OSError as e:
                logger.error(f"Errore salvataggio devices.json: {e}")

    # ─── CRUD bridge ──────────────────────────────────────────────────────────

    def get_bridges(self) -> dict:
        return self._bridges

    def add_bridge(self, topic: str, data: dict):
        with self._lock:
            self._bridges[topic] = data
            self._unknown_bridges = [b for b in self._unknown_bridges if b["topic"] != topic]
            self._save_bridges()
            logger.info(f"Bridge aggiunto: {topic}")

    def update_bridge(self, topic: str, updates: dict) -> bool:
        with self._lock:
            if topic not in self._bridges:
                return False
            if "position" in updates:
                self._bridges[topic]["position"] = updates.pop("position")
            self._bridges[topic].update(updates)
            self._save_bridges()
            return True

    def remove_bridge(self, topic: str):
        with self._lock:
            if topic in self._bridges:
                del self._bridges[topic]
                self._save_bridges()
                logger.info(f"Bridge rimosso: {topic}")

    def _save_bridges(self):
        if self._bridges_path:
            try:
                with open(self._bridges_path, "w") as f:
                    json.dump(self._bridges, f, indent=2)
            except OSError as e:
                logger.error(f"Errore salvataggio bridges.json: {e}")

    # ─── Bridge sconosciuti ───────────────────────────────────────────────────

    def add_unknown_bridge(self, topic: str):
        with self._lock:
            if any(b["topic"] == topic for b in self._unknown_bridges):
                return
            self._unknown_bridges.append({"topic": topic, "time": time.time()})
            logger.info(f"Bridge sconosciuto rilevato: {topic}")

    def get_unknown_bridges(self) -> list:
        with self._lock:
            return list(self._unknown_bridges)

    def dismiss_unknown_bridge(self, topic: str):
        with self._lock:
            self._unknown_bridges = [b for b in self._unknown_bridges if b["topic"] != topic]

    # ─── Cambio modalità ─────────────────────────────────────────────────────

    def set_mode(self, new_mode: str) -> dict:
        if new_mode not in VALID_MODES:
            raise ValueError(f"Modalità non valida: {new_mode}")

        with self._lock:
            self._cancel_arming_timer()
            self._cancel_entry_timer_locked()

            if new_mode == "DISARMED":
                self._mode = "DISARMED"
                self._alarm = False
                self._triggered_device = None

            elif new_mode in ("ARM_HOME", "ARMED_HOME"):
                self._mode = "ARMING"
                self._arming_target = "ARMED_HOME"
                self._start_arming_timer()

            elif new_mode in ("ARM_AWAY", "ARMED_AWAY"):
                self._mode = "ARMING"
                self._arming_target = "ARMED_AWAY"
                self._start_arming_timer()

            else:
                self._mode = new_mode

            self._last_change = time.time()
            logger.info(f"Modalità aggiornata: {self._mode}")
            return self._state_dict()

    def _start_arming_timer(self):
        delay = self._settings.get("timers", {}).get("arming_delay_sec", 30)
        self._arming_timer = threading.Timer(delay, self._complete_arming)
        self._arming_timer.daemon = True
        self._arming_timer.start()
        logger.info(f"ARMING avviato, transizione a {self._arming_target} in {delay}s")

    def _complete_arming(self):
        with self._lock:
            if self._mode == "ARMING" and self._arming_target:
                self._mode = self._arming_target
                self._arming_target = None
                self._last_change = time.time()
                logger.info(f"Sistema armato: {self._mode}")

    def _cancel_arming_timer(self):
        if self._arming_timer and self._arming_timer.is_alive():
            self._arming_timer.cancel()
            self._arming_timer = None
        self._arming_target = None

    # ─── Entry delay ──────────────────────────────────────────────────────────

    def start_entry_delay(self, device_name: str, delay_sec: int, on_expire) -> None:
        """
        Imposta lo stato ENTERING e avvia un timer.
        Se il sistema viene disarmato prima della scadenza, il timer viene
        annullato tramite il meccanismo di generazione.
        """
        with self._lock:
            self._cancel_entry_timer_locked()
            self._entry_generation += 1
            gen = self._entry_generation
            self._mode = "ENTERING"
            self._triggered_device = device_name
            self._last_change = time.time()

        def _guarded():
            with self._lock:
                if self._entry_generation != gen:
                    logger.info("Entry delay annullato (sistema disarmato)")
                    return
            on_expire()

        timer = threading.Timer(delay_sec, _guarded)
        timer.daemon = True
        timer.start()
        self._entry_timer = timer
        logger.info(f"Ritardo ingresso avviato: {delay_sec}s per '{device_name}'")

    def _cancel_entry_timer_locked(self):
        """Da chiamare con self._lock già acquisito."""
        self._entry_generation += 1
        if self._entry_timer and self._entry_timer.is_alive():
            self._entry_timer.cancel()
        self._entry_timer = None

    # ─── Allarme ──────────────────────────────────────────────────────────────

    def trigger_alarm(self, device_name: str) -> bool:
        """
        Ritorna True se l'allarme è stato attivato, False se il sistema
        era già disarmato (es. utente ha disarmato durante l'entry delay).
        """
        with self._lock:
            if self._mode == "DISARMED":
                logger.info(f"trigger_alarm ignorato: sistema già disarmato ({device_name})")
                return False
            self._mode = "TRIGGERED"
            self._alarm = True
            self._triggered_device = device_name
            self._last_change = time.time()
            logger.warning(f"ALLARME TRIGGERATO da: {device_name}")
            return True

    def reset_alarm(self):
        with self._lock:
            self._cancel_entry_timer_locked()
            self._alarm = False
            self._triggered_device = None
            self._mode = "DISARMED"
            self._last_change = time.time()
            logger.info("Allarme resettato")

    # ─── Eventi ───────────────────────────────────────────────────────────────

    def add_event(self, event: dict):
        with self._lock:
            self._events.append(event)
        try:
            with open(self._log_file, "a") as f:
                f.write(json.dumps(event) + "\n")
        except OSError as e:
            logger.error(f"Errore scrittura log: {e}")

    def get_events(self, limit: int = 50) -> list:
        with self._lock:
            events = list(self._events)
        return events[-limit:][::-1]
