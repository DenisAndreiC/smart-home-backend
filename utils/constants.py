# Versiunea API-ului
API_VERSION = "1.0.0"

# Calitate de serviciu MQTT (0=fire-and-forget, 1=at-least-once, 2=exactly-once)
DEFAULT_MQTT_QOS = 1

# Numărul maxim de intrări returnate din istoricul comenzilor
MAX_COMMAND_HISTORY = 100

# Parametri impliciți pentru algoritmul ML de detecție rutine
ML_DAYS_BACK = 30           # Câte zile din trecut se analizează
ML_MIN_OCCURRENCES = 5      # Minimum de apariții pentru a forma un cluster
ML_TIME_EPSILON = 15.0      # Toleranță în minute pentru DBSCAN

# Prefix token JWT în header-ul Authorization
JWT_TOKEN_PREFIX = "Bearer"

# Acțiunile IR suportate pentru fiecare tip de dispozitiv
SUPPORTED_IR_ACTIONS: dict[str, list[str]] = {
    "ir_rgb": ["power", "color", "brightness"],
    "ir_tv": [
        "power",
        "volume_up",
        "volume_down",
        "channel_up",
        "channel_down",
        "mute",
        "source",
    ],
    "ir_ac": ["power", "temperature", "mode", "fan_speed"],
    "relay": ["power"],
    "wol": ["wake"],
}
