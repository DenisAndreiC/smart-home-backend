import json
import logging

import paho.mqtt.client as mqtt

from config import settings

# Logger dedicat serviciului MQTT
logger = logging.getLogger(__name__)


class MQTTService:
    """
    Serviciu singleton pentru comunicarea cu brokerul MQTT.
    Gestioneaza conexiunea, subscriptiile si publicarea comenzilor catre ESP32.
    """

    def __init__(self):
        # Folosim CallbackAPIVersion.VERSION2 - API-ul nou din paho-mqtt 2.x
        # Vechiul API (VERSION1) este deprecat si va fi eliminat in versiuni viitoare
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

        # Inregistreaza callback-urile pentru evenimentele de retea
        self.client.on_connect = self._on_connect     # apelat la conectare reusita
        self.client.on_message = self._on_message     # apelat la primirea unui mesaj

    def connect(self):
        """
        Conecteaza clientul la broker si porneste loop-ul de retea in background.
        Daca sunt credentiale in .env, le aplica inainte de conectare.
        """
        # Daca sunt setate credentiale in .env, le aplicam inainte de connect
        if settings.mqtt_username:
            self.client.username_pw_set(settings.mqtt_username, settings.mqtt_password)

        # Conectare la broker folosind hostname si portul din settings
        self.client.connect(settings.mqtt_broker, settings.mqtt_port)

        # loop_start() ruleaza intr-un thread separat - nu blocheaza FastAPI
        self.client.loop_start()

        # Ascultam topic-ul de status de la toate dispozitivele ESP32
        # Structura wildcards: home/{camera}/{dispozitiv}/status
        self.client.subscribe("home/+/+/status", qos=1)
        logger.info("Subscris la home/+/+/status")

    def disconnect(self):
        """Opreste loop-ul de retea si inchide conexiunea la broker."""
        # Opreste thread-ul de network loop
        self.client.loop_stop()

        # Trimite pachetul DISCONNECT catre broker
        self.client.disconnect()
        logger.info("Deconectat de la broker MQTT")

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """
        Callback apelat dupa conectarea la broker.
        reason_code=0 inseamna succes; orice alt cod indica o eroare.
        """
        logger.info("Conectat la MQTT broker - reason code: %s", reason_code)

    def _on_message(self, client, userdata, message):
        """
        Callback apelat la primirea unui mesaj MQTT pe topic-urile subscrise.
        Placeholder - va fi extins pentru a actualiza statusul dispozitivului in DB.
        """
        logger.info(
            "Mesaj primit - topic: %s, payload: %s",
            message.topic,
            # Decodifica payload-ul din bytes la string; 'replace' evita erori Unicode
            message.payload.decode("utf-8", errors="replace"),
        )

    def publish_command(self, topic: str, action: str, value: str = None):
        """
        Publica o comanda JSON pe topic-ul MQTT al dispozitivului.
        Format payload standard: {"action": "power", "value": "ON"}
        QoS=1 garanteaza cel putin o livrare confirmata de broker.
        """
        # Serializam actiunea si valoarea ca JSON pentru ESP32
        payload = json.dumps({"action": action, "value": value})

        # Publicam cu QoS 1 (at-least-once delivery)
        self.client.publish(topic, payload, qos=1)
        logger.info("Comanda publicata -> topic=%s | action=%s | value=%s", topic, action, value)


# Instanta singleton folosita in toata aplicatia
# Importata direct in routere si scheduler: from services.mqtt_service import mqtt_service
mqtt_service = MQTTService()
