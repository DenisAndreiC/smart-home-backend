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

        # Subscriptii pentru statusul ESP32 IR si Relay Controller
        self.client.subscribe("smarthome/devices/ir/status", qos=1)
        self.client.subscribe("smarthome/devices/relay/status", qos=1)
        logger.info("Subscris la smarthome/devices/ir/status si smarthome/devices/relay/status")

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

    def publish_ir_command(
        self,
        device_name: str,
        device_type: str,
        action: str,
        value: str = None,
        ir_remote_type: str = None,
    ):
        """
        Publish an IR command to the ESP32 IR Controller topic.

        For ir_rgb devices the "data" field is included in the payload so the
        ESP32 knows which IR library / remote layout to use:
          {"device": "rgb", "command": "red", "data": "44"}

        For other IR types (tv, ac) the payload is:
          {"device": "tv", "command": "power"}

        Topic: smarthome/devices/ir/command
        """
        # Determine the device category string expected by the ESP32 firmware
        device_category = "tv"  # default
        name_lower = device_name.lower()

        if "tv" in name_lower or "television" in name_lower or device_type == "ir_tv":
            device_category = "tv"
        elif "ac" in name_lower or "air" in name_lower or "conditioner" in name_lower or device_type == "ir_ac":
            device_category = "ac"
        elif "bulb" in name_lower or "rgb" in name_lower or "light" in name_lower or device_type == "ir_rgb":
            device_category = "rgb"

        # Map the high-level app action to the command string the ESP32 understands
        command = self._map_action_to_command(device_category, action, value)

        # Build the base payload dict
        data: dict = {"device": device_category, "command": command}

        # Include the remote type for RGB devices so the ESP32 picks the right IR codes
        if device_type == "ir_rgb" and ir_remote_type:
            data["data"] = ir_remote_type

        self.client.publish("smarthome/devices/ir/command", json.dumps(data), qos=1)
        logger.info(
            "IR command -> device=%s command=%s data=%s",
            device_category, command, data.get("data"),
        )

    def publish_relay_command(self, mqtt_topic: str, action: str, value: str = None):
        """
        Publica o comanda pentru ESP32 Relay Controller.
        Topic: mqtt_topic al dispozitivului (ex: smarthome/devices/relay/command)
        Payload: {"device": "relay", "command": "on"}
        """
        command = value if value else ("on" if action == "power" else action)
        payload = json.dumps({
            "device": "relay",
            "command": command
        })
        self.client.publish(mqtt_topic, payload, qos=1)
        logger.info("Relay comanda -> topic=%s, command=%s", mqtt_topic, command)

    def publish_brand_config(self, brand: str):
        """
        Trimite comanda de schimbare brand TV la ESP32.
        """
        payload = json.dumps({
            "device": "config",
            "command": "set_brand",
            "data": brand.lower()
        })
        self.client.publish("smarthome/devices/ir/command", payload, qos=1)
        logger.info("Brand TV schimbat: %s", brand)

    def publish_rgb_config(self, ir_remote_type: str):
        """
        Send the RGB remote type configuration to the ESP32 IR Controller.

        Must be called before the first RGB command so the firmware loads the
        correct IR code set.  Payload format:
          {"device": "config", "command": "set_rgb_type", "data": "44"}

        Args:
            ir_remote_type: "44" or "24" (number of keys on the physical IR remote)
        """
        payload = json.dumps({
            "device": "config",
            "command": "set_rgb_type",
            "data": ir_remote_type,
        })
        self.client.publish("smarthome/devices/ir/command", payload, qos=1)
        logger.info("RGB config sent: set_rgb_type=%s", ir_remote_type)

    @staticmethod
    def _map_action_to_command(device_category: str, action: str, value: str = None) -> str:
        """
        Mapeaza actiunea din app la comanda pe care ESP32 o intelege.

        App trimite:
          action="power", value="on"/"off"/"toggle"
          action="volume_up"
          action="set_temperature", value="25"
          action="set_mode", value="cool"

        ESP32 asteapta:
          TV: "power", "volume_up", "volume_down", "channel_up", "channel_down",
              "mute", "ok", "back", "menu", "nav_up", "nav_down", "nav_left", "nav_right", "source"
          AC: "power_on", "power_off", "temp_up", "temp_down", "mode", "swing", "fan_up", "fan_down"
        """
        action_lower = action.lower()

        if device_category == "ac":
            if action_lower == "power":
                if value and value.lower() == "off":
                    return "power_off"
                return "power_on"
            elif action_lower in ("set_temperature", "set_temperature_up", "temp_up"):
                return "temp_up"
            elif action_lower in ("set_temperature_down", "temp_down"):
                return "temp_down"
            elif action_lower in ("set_mode", "mode"):
                return "mode"
            elif action_lower in ("set_swing", "swing"):
                return "swing"
            elif action_lower in ("set_fan_speed", "set_fan_speed_up", "fan_speed", "fan_up"):
                return "fan_up"
            elif action_lower in ("set_fan_speed_down", "fan_down"):
                return "fan_down"
            else:
                return action_lower
        else:
            # TV si alte dispozitive IR — actiunea merge direct
            if action_lower == "power" and value and value.lower() == "toggle":
                return "power"
            return action_lower


# Instanta singleton folosita in toata aplicatia
# Importata direct in routere si scheduler: from services.mqtt_service import mqtt_service
mqtt_service = MQTTService()
