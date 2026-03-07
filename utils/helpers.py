import re
from datetime import datetime


# Pattern regex pentru validarea adresei MAC (format AA:BB:CC:DD:EE:FF)
# Accepta litere mari si mici, cifre hex, separate prin ':'
_MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

# Pattern regex pentru validarea orei in format HH:MM (ex: "08:30", "23:59")
_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


def validate_mac_address(mac: str) -> bool:
    """
    Valideaza ca un string respecta formatul adresei MAC (AA:BB:CC:DD:EE:FF).
    Returneaza True daca formatul este corect, False altfel.
    """
    # Aplica pattern-ul regex si returneaza True/False
    return bool(_MAC_PATTERN.match(mac))


def validate_time_format(time_str: str) -> bool:
    """
    Valideaza ca un string respecta formatul HH:MM si ca valorile sunt in limite.
    Verifica atat formatul cat si valorile numerice (ora 0-23, minut 0-59).
    """
    # Verifica formatul general HH:MM cu regex
    if not _TIME_PATTERN.match(time_str):
        return False

    # Desparte ora si minutul si le converteste la int pentru validare numerica
    hour, minute = map(int, time_str.split(":"))

    # Ora trebuie sa fie intre 0 si 23, minutul intre 0 si 59
    return 0 <= hour <= 23 and 0 <= minute <= 59


def format_timestamp(dt: datetime) -> str:
    """
    Formateaza un obiect datetime in stilul romanesc: '03.03.2026, 14:30'.
    Folosit pentru afisarea datelor in interfata utilizator.
    """
    # Formatul strftime corespunzator: zi.luna.an, ora:minut
    return dt.strftime("%d.%m.%Y, %H:%M")


def generate_mqtt_topic(room: str, device_name: str) -> str:
    """
    Genereaza un topic MQTT standard din camera si numele dispozitivului.
    Exemplu: ('Living', 'Bec Living') -> 'home/living/bec-living'

    Toate caracterele speciale si diacriticele sunt inlocuite pentru compatibilitate MQTT.
    """
    def slugify(text: str) -> str:
        """
        Converteste un text arbitrar intr-un slug URL-safe pentru topic MQTT.
        Inlocuieste diacriticele romanesti si spatiile cu caractere sigure.
        """
        # Tabela de inlocuire pentru diacriticele romanesti frecvente
        replacements = {
            "a": "a", "a": "a", "i": "i", "s": "s", "t": "t",
            "A": "a", "A": "a", "I": "i", "S": "s", "T": "t",
        }
        # Aplica fiecare inlocuire din tabela
        for char, replacement in replacements.items():
            text = text.replace(char, replacement)

        # Converteste la lowercase si inlocuieste spatiile cu cratime
        return text.lower().replace(" ", "-")

    # Construieste topic-ul in formatul home/{camera}/{dispozitiv}
    return f"home/{slugify(room)}/{slugify(device_name)}"
