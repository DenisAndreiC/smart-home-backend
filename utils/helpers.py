import re
from datetime import datetime


# Pattern MAC Address (format AA:BB:CC:DD:EE:FF)
_MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

# Pattern oră în format HH:MM
_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


def validate_mac_address(mac: str) -> bool:
    """Validează că un string respectă formatul adresei MAC (AA:BB:CC:DD:EE:FF)."""
    return bool(_MAC_PATTERN.match(mac))


def validate_time_format(time_str: str) -> bool:
    """Validează că un string respectă formatul HH:MM."""
    if not _TIME_PATTERN.match(time_str):
        return False
    hour, minute = map(int, time_str.split(":"))
    return 0 <= hour <= 23 and 0 <= minute <= 59


def format_timestamp(dt: datetime) -> str:
    """Formatează un datetime în stilul românesc: '03.03.2026, 14:30'."""
    return dt.strftime("%d.%m.%Y, %H:%M")


def generate_mqtt_topic(room: str, device_name: str) -> str:
    """
    Generează un topic MQTT standard din cameră și numele dispozitivului.
    Ex: ('Living', 'Bec Living') → 'home/living/bec-living'
    """
    def slugify(text: str) -> str:
        # Înlocuiește diacriticele frecvente din română
        replacements = {
            "ă": "a", "â": "a", "î": "i", "ș": "s", "ț": "t",
            "Ă": "a", "Â": "a", "Î": "i", "Ș": "s", "Ț": "t",
        }
        for char, replacement in replacements.items():
            text = text.replace(char, replacement)
        return text.lower().replace(" ", "-")

    return f"home/{slugify(room)}/{slugify(device_name)}"
