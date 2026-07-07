from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuratia globala a aplicatiei, citita din fisierul .env."""

    # URL-ul bazei de date SQLAlchemy (implicit SQLite local)
    database_url: str

    # Adresa hostname/IP a brokerului MQTT
    mqtt_broker: str

    # Portul brokerului MQTT (implicit 1883)
    mqtt_port: int

    # Username pentru autentificarea la broker (optional, gol pentru development)
    mqtt_username: str = ""

    # Parola pentru autentificarea la broker (optional, gol pentru development)
    mqtt_password: str = ""

    # Cheia secreta folosita pentru semnarea token-urilor JWT
    jwt_secret: str

    # Algoritmul de semnare JWT (HS256 este recomandat)
    jwt_algorithm: str

    # Durata de viata a token-ului JWT in minute (1440 = 24 ore)
    jwt_expiration_minutes: int

    # URL-ul public al backend-ului, folosit in linkurile din email-uri
    # (verify-email, reset-password). Trebuie sa fie adresa/domeniul accesibil
    # din afara retelei locale (ex: IP-ul public de pe Hetzner), nu un IP local.
    base_url: str = "http://localhost:8000"

    # Spune pydantic-settings sa citeasca valorile din fisierul .env
    model_config = {"env_file": ".env"}


# Instanta globala folosita in toata aplicatia
settings = Settings()
