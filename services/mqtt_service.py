import json
import logging

import paho.mqtt.client as mqtt

from config import settings

logger = logging.getLogger(__name__)


class MQTTService:
    def __init__(self):
        # Folosim CallbackAPIVersion.VERSION2 — API-ul nou din paho-mqtt 2.x
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def connect(self):
        """Conectează clientul la broker și pornește loop-ul de rețea în background."""
        # Dacă sunt setate credențiale în .env, le aplicăm înainte de connect
        if settings.mqtt_username:
            self.client.username_pw_set(settings.mqtt_username, settings.mqtt_password)

        self.client.connect(settings.mqtt_broker, settings.mqtt_port)
        # loop_start() rulează într-un thread separat — nu blochează FastAPI
        self.client.loop_start()

        # Ascultăm topic-ul de status de la toate dispozitivele ESP32
        # Structura: home/{cameră}/{dispozitiv}/status
        self.client.subscribe("home/+/+/status", qos=1)
        logger.info("Subscris la home/+/+/status")

    def disconnect(self):
        """Oprește loop-ul și închide conexiunea la broker."""
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("Deconectat de la broker MQTT")

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """Callback apelat după conectarea la broker."""
        logger.info("Conectat la MQTT broker — reason code: %s", reason_code)

    def _on_message(self, client, userdata, message):
        """
        Callback apelat la primirea unui mesaj MQTT.
        Placeholder — va fi extins pentru a actualiza statusul dispozitivului în DB.
        """
        logger.info(
            "Mesaj primit — topic: %s, payload: %s",
            message.topic,
            message.payload.decode("utf-8", errors="replace"),
        )

    def publish_command(self, topic: str, action: str, value: str = None):
        """
        Publică o comandă JSON pe topic-ul MQTT al dispozitivului.
        Format payload: {"action": "power", "value": "ON"}
        """
        payload = json.dumps({"action": action, "value": value})
        self.client.publish(topic, payload, qos=1)
        logger.info("Comandă publicată → topic=%s | action=%s | value=%s", topic, action, value)


# Instanță singleton folosită în toată aplicația
mqtt_service = MQTTService()
