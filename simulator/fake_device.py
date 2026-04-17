import json
import time
import random
import argparse
from pathlib import Path
import paho.mqtt.client as mqtt

# ─── Config ───────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent

with open(ROOT / "config" / "settings.json") as f:
    settings = json.load(f)

BROKER = settings["mqtt"]["broker"]
PORT   = settings["mqtt"]["port"]
TOPIC  = settings["topics"]["input_test"]
TOPIC_CMD = settings["topics"]["cmd"]

DEVICES = {
    "cancello":        "E1F2G3",
    "porta_ingresso":  "A1B2C3",
    "capannone":       "H4I5J6",
    "giardino_pir":    "K7L8M9",
    "soggiorno_pir":   "D4E5F6",
    "cucina_pir":      "N0O1P2",
    "camera_da_letto": "Q3R4S5",
    "cameretta":       "T6U7V8",
    "telecomando":     "D6U89A",
}

# ─── MQTT ─────────────────────────────────────────────────────────────────────

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="alarm-sim")

def connect():
    client.connect(BROKER, PORT, 60)
    client.loop_start()
    print(f"Simulatore connesso a {BROKER}:{PORT}")

# ─── Invio eventi ─────────────────────────────────────────────────────────────

def invia_evento(device_name: str):
    if device_name not in DEVICES:
        print(f"Dispositivo sconosciuto: {device_name}")
        print(f"Disponibili: {list(DEVICES.keys())}")
        return

    payload = {"code": DEVICES[device_name]}
    client.publish(TOPIC, json.dumps(payload))
    print(f"[+] Evento inviato: {device_name} ({DEVICES[device_name]})")

def invia_comando(action: str):
    payload = {"action": action.upper()}
    client.publish(TOPIC_CMD, json.dumps(payload))
    print(f"[CMD] Comando inviato: {action}")

# ─── Modalità ─────────────────────────────────────────────────────────────────

def modo_manual():
    print("Modalità manuale. Dispositivi:", list(DEVICES.keys()))
    print("Digita il nome del dispositivo o 'quit' per uscire.")
    while True:
        try:
            nome = input("Dispositivo > ").strip()
            if nome == "quit":
                break
            invia_evento(nome)
        except (KeyboardInterrupt, EOFError):
            break

def modo_random(device: str = None):
    targets = [device] if device else list(DEVICES.keys())
    print(f"Modalità random → {targets}. Ctrl+C per fermare.")
    while True:
        nome = random.choice(targets)
        invia_evento(nome)
        pausa = random.uniform(5, 15)
        print(f"    prossimo evento in {pausa:.1f}s...")
        time.sleep(pausa)

def modo_burst():
    """Invia rapidamente tutti i dispositivi in sequenza, utile per test."""
    print("Modalità burst: invio tutti i dispositivi in sequenza.")
    for nome in DEVICES:
        invia_evento(nome)
        time.sleep(0.5)
    print("Burst completato.")

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulatore dispositivi allarme")
    parser.add_argument(
        "--mode", choices=["manual", "random", "burst"],
        default="manual", help="Modalità di simulazione (default: manual)"
    )
    parser.add_argument(
        "--device", metavar="NAME",
        help="Limita il random a un solo dispositivo (es: porta_ingresso)"
    )
    parser.add_argument(
        "--cmd", metavar="ACTION",
        help="Invia un comando al sistema (es: ARM_AWAY, ARM_HOME, DISARM, RESET)"
    )
    args = parser.parse_args()

    connect()

    if args.cmd:
        invia_comando(args.cmd)
        time.sleep(0.5)

    try:
        if args.mode == "manual":
            modo_manual()
        elif args.mode == "random":
            modo_random(args.device)
        elif args.mode == "burst":
            modo_burst()
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()
        print("Simulatore disconnesso.")
