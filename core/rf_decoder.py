from __future__ import annotations
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class RFDecoder:
    def __init__(self, state_manager):
        self._state = state_manager

    def decode(self, topic: str, payload: bytes) -> Optional[dict]:
        """
        Decodifica il payload MQTT in un dict dispositivo.
        Supporta due formati:
          - Test/simulator: {"code": "A1B2C3"}
          - RF bridge (Tasmota): {"RfReceived": {"Data": "0xA1B2C3"}}
        Ritorna il dict del dispositivo con "code" aggiunto, o None se sconosciuto.
        """
        try:
            data = json.loads(payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Payload non valido su {topic}: {e}")
            return None

        code = self._estrai_codice(topic, data)
        if code is None:
            logger.warning(f"Impossibile estrarre codice da payload: {data}")
            return None

        code = code.upper()
        devices = self._state.get_devices()

        if code not in devices:
            logger.warning(f"Codice RF sconosciuto: {code}")
            return {"unknown": True, "code": code}

        device = dict(devices[code])
        device["code"] = code
        return device

    def _estrai_codice(self, topic: str, data: dict) -> Optional[str]:
        # Formato test/simulator: {"code": "A1B2C3"}
        if "code" in data:
            return str(data["code"])

        # Formato RF bridge Tasmota: {"RfReceived": {"Data": "0xA1B2C3"}}
        if "RfReceived" in data:
            raw = data["RfReceived"].get("Data", "")
            return raw.lstrip("0x").lstrip("0X") if raw else None

        return None
