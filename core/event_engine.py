import json
import time
import logging

logger = logging.getLogger(__name__)

ACTION_MAP = {
    "DISARM": "DISARMED",
    "ARM_HOME": "ARMED_HOME",
    "ARM_AWAY": "ARMED_AWAY",
}


class EventEngine:
    def __init__(self, state_manager, alarm_logic, rf_decoder,
                 mqtt_publish_fn, notifier=None):
        self._state   = state_manager
        self._logic   = alarm_logic
        self._decoder = rf_decoder
        self._publish = mqtt_publish_fn
        self._notifier = notifier
        # Anti-spam RF: {code: last_event_timestamp}
        self._last_rf_event: dict[str, float] = {}

    def process_message(self, topic: str, payload: bytes):
        """
        Pipeline principale:
        payload → [bridge check] → [anti-spam] → decode → evento
                → log → publish → logic → [entry delay | alert]
        """
        try:
            topics    = self._state._settings["topics"]
            rf_prefix = topics["input_rf"].rstrip("/#")
            is_rf     = topic.startswith(rf_prefix + "/")
            is_test   = topic == topics.get("input_test", "")

            # ── Validazione bridge per messaggi RF (non per test) ─────────────
            if is_rf and not is_test:
                bridges = self._state.get_bridges()
                if topic not in bridges:
                    self._state.add_unknown_bridge(topic)
                    self._publish(
                        topics.get("unknown_bridge", "home/alarm/unknown_bridge"),
                        {"topic": topic, "time": time.time()},
                    )
                    logger.info(f"Bridge non autorizzato, messaggio ignorato: {topic}")
                    return
                if not bridges[topic].get("enabled", True):
                    logger.debug(f"Bridge disabilitato, messaggio ignorato: {topic}")
                    return

            device = self._decoder.decode(topic, payload)
            if device is None:
                return

            if device.get("unknown"):
                code = device["code"]
                self._state.add_unknown_device(code)
                self._publish(topics["unknown"], {"code": code, "time": time.time()})
                logger.info(f"Dispositivo sconosciuto rilevato: {code}")
                return

            # ── Controller: cicla gli stati del sistema ───────────────────────
            if device.get("type") == "controller":
                self._handle_controller(device)
                return

            # ── Anti-spam RF ──────────────────────────────────────────────────
            code     = device.get("code", "")
            cooldown = self._state._settings.get("timers", {}).get("rf_cooldown_sec", 2)
            now      = time.time()
            if code and cooldown > 0:
                last = self._last_rf_event.get(code, 0)
                if now - last < cooldown:
                    logger.debug(f"Anti-spam: {device['name']} ignorato "
                                 f"({now - last:.1f}s < {cooldown}s)")
                    return
                self._last_rf_event[code] = now

            evento = {
                "device": device["name"],
                "type":   device["type"],
                "zone":   device["zone"],
                "code":   device["code"],
                "time":   now,
            }

            self._state.add_event(evento)
            self._publish(topics["events"], evento)
            logger.info(f"Evento: {device['name']} ({device['type']}, {device['zone']})")

            if self._logic.evaluate(device):
                self._fire_alarm(device, topics)

        except Exception as e:
            logger.error(f"Errore in process_message: {e}", exc_info=True)

    # ── Gestione allarme (con o senza entry delay) ─────────────────────────────

    def _fire_alarm(self, device: dict, topics: dict):
        # Entry delay solo se il sensore è marcato come "ingresso"
        configured_delay = self._state._settings.get("timers", {}).get("entry_delay_sec", 0)
        entry_delay = configured_delay if device.get("entry_delay", False) else 0

        # Cattura il modo corrente PRIMA del cambio di stato
        mode_prima = self._state.get_state()["mode"]

        if entry_delay > 0:
            _dev    = dict(device)
            _topics = dict(topics)

            def on_entry_expired():
                triggered = self._state.trigger_alarm(_dev["name"])
                if not triggered:
                    return
                alert = {
                    "trigger": _dev["name"],
                    "type":    _dev["type"],
                    "zone":    _dev["zone"],
                    "time":    time.time(),
                }
                self._publish(_topics["alert"], alert)
                self._publish(_topics["state"], self._state.get_state())
                if self._notifier:
                    self._notifier.send_alarm(
                        _dev["name"], mode_prima, _dev["zone"],
                        _dev["type"], time.time(),
                    )
                logger.warning(f"ALLARME dopo entry delay: {_dev['name']}")

            self._state.start_entry_delay(_dev["name"], entry_delay, on_entry_expired)
            self._publish(topics["state"], self._state.get_state())
            logger.info(f"Entry delay {entry_delay}s avviato per {device['name']}")
        else:
            triggered = self._state.trigger_alarm(device["name"])
            if not triggered:
                return
            alert = {
                "trigger": device["name"],
                "type":    device["type"],
                "zone":    device["zone"],
                "time":    time.time(),
            }
            self._publish(topics["alert"], alert)
            self._publish(topics["state"], self._state.get_state())
            if self._notifier:
                self._notifier.send_alarm(
                    device["name"], mode_prima, device["zone"],
                    device["type"], time.time(),
                )
            logger.warning(f"ALLARME pubblicato per {device['name']}")

    def _handle_controller(self, device: dict):
        """
        Ciclo stati per dispositivo controller:
          DISARMED                          → ARMING → ARMED_HOME
          ARMING (target HOME) / ARMED_HOME → ARMING → ARMED_AWAY
          ARMING (target AWAY) / ARMED_AWAY / TRIGGERED / ENTERING → DISARMED
        """
        state   = self._state.get_state()
        current = state["mode"]
        target  = state.get("arming_target")

        if current == "DISARMED":
            self._state.set_mode("ARMED_HOME")
            logger.info(f"Controller {device['name']}: DISARMED → ARMING (home)")
        elif current == "ARMED_HOME" or (current == "ARMING" and target == "ARMED_HOME"):
            self._state.set_mode("ARMED_AWAY")
            logger.info(f"Controller {device['name']}: {current}/{target} → ARMING (away)")
        else:
            if current == "TRIGGERED":
                self._state.reset_alarm()
            else:
                self._state.set_mode("DISARMED")
            logger.info(f"Controller {device['name']}: {current} → DISARMED")

        topics = self._state._settings["topics"]
        self._publish(topics["state"], self._state.get_state())

    def process_command(self, payload: bytes):
        """
        Gestisce comandi da home/alarm/cmd.
        Formato: {"action": "ARM_AWAY"} | {"action": "DISARM"} | {"action": "ARM_HOME"} | {"action": "RESET"}
        """
        try:
            data   = json.loads(payload.decode())
            action = data.get("action", "").upper()

            if action not in ACTION_MAP and action != "RESET":
                logger.warning(f"Comando sconosciuto: {action}")
                return

            if action == "RESET":
                self._state.reset_alarm()
            else:
                self._state.set_mode(ACTION_MAP[action])

            topics = self._state._settings["topics"]
            self._publish(topics["state"], self._state.get_state())
            logger.info(f"Comando eseguito: {action}")

        except Exception as e:
            logger.error(f"Errore in process_command: {e}", exc_info=True)
