import json
import sys
import logging
import argparse
import threading
from pathlib import Path

from core.state_manager import StateManager
from core.alarm_logic import AlarmLogic
from core.rf_decoder import RFDecoder
from core.event_engine import EventEngine
from core.mqtt_client import MQTTClient

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("main")

# ─── Config ───────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent

with open(ROOT / "config" / "settings.json") as f:
    settings = json.load(f)

with open(ROOT / "config" / "devices.json") as f:
    devices = json.load(f)

bridges_path = ROOT / "config" / "bridges.json"
try:
    with open(bridges_path) as f:
        bridges = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    bridges = {}

# Risolvi il percorso del log file relativo alla root del progetto
settings["log_file"] = str(ROOT / settings.get("log_file", "logs/events.log"))

# ─── Dependency graph ─────────────────────────────────────────────────────────

state_mgr = StateManager(
    settings, devices,
    devices_path=ROOT / "config" / "devices.json",
    bridges=bridges,
    bridges_path=bridges_path,
)
alarm_logic = AlarmLogic(state_mgr)
rf_decoder = RFDecoder(state_mgr)

# Risolvi dipendenza circolare: MQTTClient <-> EventEngine
mqtt_client = MQTTClient(settings, event_engine=None)
event_engine = EventEngine(state_mgr, alarm_logic, rf_decoder, mqtt_client.publish)
mqtt_client.event_engine = event_engine

# ─── Avvio ────────────────────────────────────────────────────────────────────

def avvia_api():
    import uvicorn
    from api.server import create_app

    app = create_app(state_mgr, event_engine)
    api_cfg = settings.get("api", {})
    uvicorn.run(
        app,
        host=api_cfg.get("host", "0.0.0.0"),
        port=api_cfg.get("port", 8080),
        log_level="warning",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Home Alarm System")
    parser.add_argument("--api", action="store_true", help="Avvia il web server API")
    parser.add_argument("--no-cli", action="store_true", help="Disabilita il CLI interattivo")
    args = parser.parse_args()

    mqtt_client.connect()
    mqtt_client.start()
    logger.info("Sistema avviato")

    if args.api:
        api_thread = threading.Thread(target=avvia_api, daemon=True)
        api_thread.start()
        logger.info(f"API web avviata su http://localhost:{settings['api']['port']}")

    try:
        if not args.no_cli:
            while True:
                cmd = input("Comando (disarm/home/away/reset/quit): ").strip().lower()
                if cmd == "quit":
                    break
                elif cmd == "disarm":
                    event_engine.process_command(b'{"action": "DISARM"}')
                elif cmd == "home":
                    event_engine.process_command(b'{"action": "ARM_HOME"}')
                elif cmd == "away":
                    event_engine.process_command(b'{"action": "ARM_AWAY"}')
                elif cmd == "reset":
                    event_engine.process_command(b'{"action": "RESET"}')
                elif cmd == "stato":
                    print(state_mgr.get_state())
                else:
                    print("Comandi: disarm / home / away / reset / stato / quit")
        else:
            threading.Event().wait()
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        mqtt_client.stop()
        logger.info("Sistema spento")
