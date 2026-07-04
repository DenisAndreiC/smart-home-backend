"""
Dispatch central pentru trimiterea comenzilor catre dispozitive.

Alege canalul corect in functie de device_type (WoL, IR, relay sau MQTT generic).
Folosit atat de comenzile manuale (routers/commands.py) cat si de scheduler-ul
de rutine (services/scheduler_service.py) — evita duplicarea logicii de dispatch
si garanteaza ca rutinele trimit exact acelasi payload ca o comanda manuala.
"""

import json

from database.db import Device
from services.mqtt_service import mqtt_service
from services.wol_service import wake_device

_ON_VALUES = {"on", "1", "true", "power_on"}


def is_device_on(device: Device) -> bool:
    """Best-effort check of whether last_status indicates the device is currently on."""
    return (device.last_status or "").strip().lower() in _ON_VALUES


def send_device_command(device: Device, action: str, value: str | None = None) -> None:
    """Trimite comanda catre dispozitiv prin canalul corespunzator tipului sau."""
    if device.device_type == "wol":
        wake_device(device.mac_address)
    elif device.device_type in ("ir_tv", "ir_ac", "ir_rgb"):
        # Extract brand-ul TV din ir_codes JSON (stocat ca {"brand": "samsung"})
        tv_brand = None
        if device.device_type == "ir_tv" and device.ir_codes:
            try:
                tv_brand = json.loads(device.ir_codes).get("brand")
            except Exception:
                pass
        mqtt_service.publish_ir_command(
            device.name, device.device_type, action, value,
            ir_remote_type=device.ir_remote_type,
            brand=tv_brand,
        )
    elif device.device_type == "relay":
        mqtt_service.publish_relay_command(device.mqtt_topic, action, value)
    else:
        mqtt_service.publish_command(device.mqtt_topic, action, value)
