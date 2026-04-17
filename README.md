# alarm-system

> Self-hosted home alarm system with RF bridge support, MQTT, REST API and a web dashboard.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![MQTT](https://img.shields.io/badge/broker-Mosquitto-orange)

---

## Overview

**alarm-system** is a lightweight, self-hosted security system designed to run on any Linux machine or Raspberry Pi. It receives signals from RF sensors via MQTT (e.g. Tasmota-flashed bridges), applies configurable alarm logic, and exposes a clean REST API with a dark-themed web dashboard for real-time monitoring and management.

---

## Features

- **RF bridge support** — receives signals from 433 MHz sensors through any MQTT-capable bridge (Tasmota, etc.)
- **Multi-zone logic** — perimeter and internal zones with independent arming modes
- **Role-based access** — three user levels (view-only, arming, admin)
- **Interactive map** — drag-and-drop device placement on a floor plan
- **Live dashboard** — real-time state, events log, and alarm status
- **Full CRUD** — add, edit, enable/disable and remove devices, bridges and users via UI or API
- **Unknown device detection** — automatic onboarding flow for unrecognized RF codes
- **Device simulator** — built-in tool to test the system without physical hardware

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   alarm-system                      │
│                                                     │
│   MQTT Broker (Mosquitto)                           │
│        │                                            │
│   MQTTClient  ──►  EventEngine  ──►  AlarmLogic    │
│                         │                           │
│                    RFDecoder                        │
│                         │                           │
│                   StateManager  ◄──►  devices.json  │
│                         │         ◄──►  bridges.json │
│                         │                           │
│                   FastAPI (REST)                    │
│                         │                           │
│                   Web Dashboard (vanilla JS)        │
└─────────────────────────────────────────────────────┘
```

---

## Requirements

- Python 3.10+
- An MQTT broker (e.g. [Mosquitto](https://mosquitto.org/))
- A web browser (for the dashboard)
- Optionally: a Tasmota-flashed RF bridge for real hardware

---

## Quick Start

**1. Clone the repository**
```bash
git clone https://github.com/dany80213/alarm-system.git
cd alarm-system
```

**2. Create a virtual environment and install dependencies**
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**3. Start the MQTT broker**
```bash
mosquitto
# or on macOS with Homebrew:
brew services start mosquitto
```

**4. Configure the system**

Copy the example config files and edit them as needed:
```bash
cp config/settings.example.json config/settings.json
cp config/devices.example.json  config/devices.json
```

**5. Start the system**
```bash
python main.py --api
```

**6. Open the dashboard**
```
http://localhost:8080
```

> On first run, create an admin user via the Users tab (level 100).

---

## Configuration

### `config/settings.json`

```json
{
  "mqtt": {
    "broker": "localhost",
    "port": 1883,
    "keepalive": 60
  },
  "topics": {
    "input_rf":      "home/alarm/rf/#",
    "input_test":    "home/alarm/test/device",
    "cmd":           "home/alarm/cmd",
    "events":        "home/alarm/events",
    "state":         "home/alarm/state",
    "alert":         "home/alarm/alert",
    "unknown":       "home/alarm/unknown",
    "devices_added": "home/alarm/devices/added"
  },
  "timers": {
    "arming_delay_sec": 30
  },
  "api": {
    "host": "0.0.0.0",
    "port": 8080
  },
  "log_file": "logs/events.log",
  "max_events": 200
}
```

| Key | Description |
|-----|-------------|
| `mqtt.broker` | Hostname or IP of your MQTT broker |
| `topics.input_rf` | Wildcard topic listened by all RF bridges |
| `timers.arming_delay_sec` | Grace period (seconds) before arming completes |
| `api.port` | Port for the web dashboard and REST API |

---

## System States

| State | Description |
|-------|-------------|
| `DISARMED` | System off — all events ignored |
| `ARMING` | Grace period before arming completes |
| `ARMED_HOME` | Only perimeter sensors active |
| `ARMED_AWAY` | All sensors active |
| `TRIGGERED` | Alarm triggered |

---

## Web Dashboard

The dashboard is a single-page application served directly by the API at `http://localhost:8080`.

### Tabs

| Tab | Min Level | Description |
|-----|-----------|-------------|
| Dashboard | 10 | Live map, state badge, event log |
| Config | 10 | Device and bridge management |
| Users | 100 | User management |

### User Levels

| Level | Role | Permissions |
|-------|------|-------------|
| 10 | Viewer | View state, events, devices |
| 50 | Operator | View + arm / disarm |
| 100 | Admin | Full access including config and user management |

---

## REST API

All endpoints require a `Bearer` token obtained from `/auth/login`.  
Responses use standard HTTP status codes.

### Auth

| Method | Endpoint | Level | Description |
|--------|----------|-------|-------------|
| POST | `/auth/login` | — | Login, returns `token` |
| POST | `/auth/logout` | 10 | Invalidate session |
| GET  | `/auth/me` | 10 | Current user info |

### State & Events

| Method | Endpoint | Level | Description |
|--------|----------|-------|-------------|
| GET  | `/state` | 10 | Current alarm state |
| GET  | `/events?limit=50` | 10 | Last N events (max 500) |
| POST | `/command` | 50 | Send a command (`ARM_HOME`, `ARM_AWAY`, `DISARM`, `RESET`) |

### Devices

| Method | Endpoint | Level | Description |
|--------|----------|-------|-------------|
| GET    | `/devices` | 10 | List all devices |
| POST   | `/devices/add` | 100 | Add a new device |
| PUT    | `/devices/{code}` | 100 | Update device (name, type, zone, position, enabled) |
| DELETE | `/devices/{code}` | 100 | Remove a device |

### Bridges

| Method | Endpoint | Level | Description |
|--------|----------|-------|-------------|
| GET    | `/bridges` | 10 | List all RF bridges |
| POST   | `/bridges` | 100 | Register a new bridge |
| PUT    | `/bridges/{topic}` | 100 | Update bridge (client, position, enabled) |
| DELETE | `/bridges/{topic}` | 100 | Remove a bridge |

### Unknown Devices & Bridges

| Method | Endpoint | Level | Description |
|--------|----------|-------|-------------|
| GET  | `/unknown` | 10 | Unrecognized RF device codes |
| POST | `/unknown/dismiss` | 50 | Dismiss an unknown device |
| GET  | `/unknown-bridges` | 10 | Unrecognized RF bridge topics |
| POST | `/unknown-bridges/dismiss` | 50 | Dismiss an unknown bridge |

### Users

| Method | Endpoint | Level | Description |
|--------|----------|-------|-------------|
| GET    | `/users` | 100 | List all users |
| POST   | `/users` | 100 | Create a user |
| PUT    | `/users/{username}` | 100 | Update password or level |
| DELETE | `/users/{username}` | 100 | Delete a user |

### Listening Mode

| Method | Endpoint | Level | Description |
|--------|----------|-------|-------------|
| GET  | `/listening` | 10 | Get current listening state |
| POST | `/listening/toggle` | 100 | Enable / disable unknown device detection |

---

## MQTT Topics

| Topic | Direction | Description |
|-------|-----------|-------------|
| `home/alarm/rf/#` | INPUT | Signals from RF bridges (Tasmota, etc.) |
| `home/alarm/test/device` | INPUT | Signals from the simulator |
| `home/alarm/cmd` | INPUT | Commands: `ARM_HOME`, `ARM_AWAY`, `DISARM`, `RESET` |
| `home/alarm/events` | OUTPUT | Normalized device events |
| `home/alarm/state` | OUTPUT | State change notifications |
| `home/alarm/alert` | OUTPUT | Alarm trigger notifications |
| `home/alarm/devices/added` | OUTPUT | New device registered |
| `home/alarm/unknown` | OUTPUT | Unknown device detected |
| `home/alarm/unknown_bridge` | OUTPUT | Unknown bridge detected |

---

## Simulator

The built-in simulator lets you test the system without any physical hardware.

```bash
# Random events every 3-8 seconds
python simulator/fake_device.py --mode random

# Manual event selection
python simulator/fake_device.py --mode manual

# Burst — all devices in rapid sequence
python simulator/fake_device.py --mode burst

# Send a direct command
python simulator/fake_device.py --cmd ARM_AWAY
```

---

## Project Structure

```
alarm-system/
├── config/
│   ├── settings.json           # MQTT, API, timers
│   ├── settings.example.json   # Template — copy and edit
│   ├── devices.json            # Registered RF devices
│   ├── devices.example.json    # Template with sample devices
│   └── bridges.json            # Registered RF bridges
├── core/
│   ├── mqtt_client.py          # MQTT wrapper (paho)
│   ├── rf_decoder.py           # RF payload decoder
│   ├── event_engine.py         # Processing pipeline
│   ├── alarm_logic.py          # Alarm rules
│   └── state_manager.py        # Thread-safe global state
├── simulator/
│   └── fake_device.py          # Hardware simulator
├── api/
│   └── server.py               # FastAPI REST + static serving
├── web/
│   ├── index.html              # Dashboard HTML
│   ├── app.js                  # Frontend logic (vanilla JS)
│   └── style.css               # Dark theme
├── logs/
│   └── events.log              # Persistent event log
├── main.py                     # Entry point
├── requirements.txt
├── .gitignore
└── LICENSE
```

---

## Contributing

Contributions are welcome. Please open an issue first to discuss what you would like to change.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'Add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.  
You are free to use, modify and distribute this software, as long as the original copyright notice is retained.
