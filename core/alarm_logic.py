import logging

logger = logging.getLogger(__name__)


class AlarmLogic:
    def __init__(self, state_manager):
        self._state = state_manager

    def evaluate(self, device: dict) -> bool:
        """
        Ritorna True se il dispositivo deve triggerare l'allarme
        in base alla modalità corrente.
        """
        mode = self._state.get_state()["mode"]

        # Legge il campo enabled dalla sorgente autoritativa (state_manager),
        # non dalla copia passata dal decoder che potrebbe essere stale.
        code = device.get("code")
        current = self._state.get_devices().get(code, device) if code else device
        if not current.get("enabled", True):
            logger.debug(f"Dispositivo disabilitato, ignoro {device['name']}")
            return False

        if mode == "DISARMED":
            logger.debug(f"Sistema disattivato, ignoro {device['name']}")
            return False

        if mode == "ARMING":
            logger.debug(f"Sistema in armamento, ignoro {device['name']}")
            return False

        if mode == "TRIGGERED":
            logger.debug("Allarme già attivo")
            return False

        if mode == "ARMED_HOME":
            if device.get("zone") == "perimeter":
                logger.info(f"ARMED_HOME: sensore perimetrale attivato -> {device['name']}")
                return True
            else:
                logger.debug(f"ARMED_HOME: sensore interno ignorato -> {device['name']}")
                return False

        if mode == "ARMED_AWAY":
            logger.info(f"ARMED_AWAY: sensore attivato -> {device['name']}")
            return True

        return False
