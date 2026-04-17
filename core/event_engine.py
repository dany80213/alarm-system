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
    def __init__(self, state_manager, alarm_logic, rf_decoder, mqtt_publish_fn):
        self._state = state_manager
        self._logic = alarm_logic
        self._decoder = rf_decoder
        self._publish = mqtt_publish_fn

    def process_message(self, topic: str, payload: bytes):
        """
        Pipeline principale:
        payload -> [bridge check] -> decode -> evento -> log -> publish -> logic -> alert
        """
        try:
            topics = self._state._settings["topics"]
            rf_prefix = topics["input_rf"].rstrip("/#")
            is_rf = topic.startswith(rf_prefix + "/")
            is_test = topic == topics.get("input_test", "")

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

            evento = {
                "device": device["name"],
                "type": device["type"],
                "zone": device["zone"],
                "code": device["code"],
                "time": time.time(),
            }

            self._state.add_event(evento)

            self._publish(topics["events"], evento)

            logger.info(f"Evento: {device['name']} ({device['type']}, {device['zone']})")

            if self._logic.evaluate(device):
                self._state.trigger_alarm(device["name"])

                alert = {
                    "trigger": device["name"],
                    "type": device["type"],
                    "zone": device["zone"],
                    "time": time.time(),
                }
                self._publish(topics["alert"], alert)
                self._publish(topics["state"], self._state.get_state())
                logger.warning(f"ALLARME pubblicato per {device['name']}")

        except Exception as e:
            logger.error(f"Errore in process_message: {e}", exc_info=True)

    def _handle_controller(self, device: dict):
        """
        Ciclo stati per dispositivo controller:
          DISARMED                          → ARMING → ARMED_HOME
          ARMING (target HOME) / ARMED_HOME → ARMING → ARMED_AWAY
          ARMING (target AWAY) / ARMED_AWAY / TRIGGERED → DISARMED
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
            data = json.loads(payload.decode())
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
