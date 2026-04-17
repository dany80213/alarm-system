import json
import logging
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTClient:
    def __init__(self, settings: dict, event_engine=None):
        self._settings = settings
        self.event_engine = event_engine

        self._topics = settings["topics"]
        # Prefisso RF: es. "home/alarm/rf" (wildcard rimossa se presente)
        self._rf_prefix = self._topics["input_rf"].rstrip("/#")

        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="alarm-core",
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

    def connect(self):
        broker = self._settings["mqtt"]["broker"]
        port = self._settings["mqtt"]["port"]
        keepalive = self._settings["mqtt"].get("keepalive", 60)
        self._client.connect(broker, port, keepalive)
        logger.info(f"Connessione a MQTT broker {broker}:{port}")

    def start(self):
        self._client.loop_start()

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()
        logger.info("MQTT client disconnesso")

    def publish(self, topic: str, payload: dict):
        try:
            self._client.publish(topic, json.dumps(payload))
            logger.debug(f"Pubblicato su {topic}")
        except Exception as e:
            logger.error(f"Errore publish su {topic}: {e}")

    # ─── Callbacks MQTT ───────────────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            logger.error(f"Connessione MQTT fallita: {reason_code}")
            return
        logger.info("Connesso al broker MQTT")
        # Wildcard per tutti i bridge RF
        rf_wildcard = self._rf_prefix + "/#"
        client.subscribe(rf_wildcard)
        logger.info(f"Sottoscritto a: {rf_wildcard}")
        # Topic di test e comandi
        for key in ("input_test", "cmd"):
            topic = self._topics[key]
            client.subscribe(topic)
            logger.info(f"Sottoscritto a: {topic}")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload
        topics = self._topics

        if topic.startswith(self._rf_prefix + "/"):
            if self.event_engine:
                self.event_engine.process_message(topic, payload)
        elif topic == topics["input_test"]:
            if self.event_engine:
                self.event_engine.process_message(topic, payload)
        elif topic == topics["cmd"]:
            if self.event_engine:
                self.event_engine.process_command(payload)
        else:
            logger.debug(f"Messaggio su topic non gestito: {topic}")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        if reason_code.value != 0:
            logger.debug(f"Disconnessione inattesa dal broker ({reason_code})")
