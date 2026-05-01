# Versiunea curenta a API-ului
API_VERSION = "1.0.0"

# Calitatea de serviciu MQTT
# 0 = fire-and-forget (fara confirmare)
# 1 = at-least-once (cel putin o livrare confirmata)
# 2 = exactly-once (livrare exacta o singura data)
DEFAULT_MQTT_QOS = 1

# Numarul maxim de intrari returnate din istoricul comenzilor
MAX_COMMAND_HISTORY = 100

# Parametri implicitii pentru algoritmul ML de detectie rutine
ML_DAYS_BACK = 30           # Cate zile din trecut se analizeaza
ML_MIN_OCCURRENCES = 5      # Minimum de aparitii pentru a forma un cluster DBSCAN
ML_TIME_EPSILON = 15.0      # Toleranta in minute intre doua comenzi din acelasi cluster

# Prefixul token-ului JWT in header-ul Authorization
JWT_TOKEN_PREFIX = "Bearer"

# Actiunile IR suportate pentru fiecare tip de dispozitiv
# Folosit de endpoint-ul /devices/supported-actions si validare frontend
SUPPORTED_IR_ACTIONS: dict[str, list[str]] = {
    "ir_rgb": [
        "power",            # Pornire / oprire bec RGB
        "color",            # Culoare directa: red, green, blue, warm_white, cool_white
        "brightness_up",    # Creste luminozitatea (un pas)
        "brightness_down",  # Scade luminozitatea (un pas)
        "flash",            # Efect flash (disponibil pe 44-key si 24-key)
        "fade",             # Efect fade (disponibil pe 44-key si 24-key)
    ],
    "ir_tv": [
        "power",            # Pornire / oprire televizor
        "volume_up",        # Creste volumul
        "volume_down",      # Scade volumul
        "channel_up",       # Canal urmator
        "channel_down",     # Canal anterior
        "mute",             # Silentios
        "source",           # Schimba sursa de intrare
    ],
    "ir_ac": [
        "power",        # Pornire / oprire AC
        "temperature",  # Seteaza temperatura (ex: "22")
        "mode",         # Modul de functionare (cool, heat, fan, auto)
        "fan_speed",    # Viteza ventilatorului (low, medium, high, auto)
    ],
    "relay": [
        "power",    # Pornire sau oprire releu (on/off)
    ],
    "wol": [
        "wake",     # Trimite magic packet Wake-on-LAN
    ],
}
