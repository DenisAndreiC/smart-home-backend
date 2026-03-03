from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Baza de date
    database_url: str

    # Configurare broker MQTT
    mqtt_broker: str
    mqtt_port: int
    mqtt_username: str = ""
    mqtt_password: str = ""

    # Configurare JWT pentru autentificare
    jwt_secret: str
    jwt_algorithm: str
    jwt_expiration_minutes: int

    model_config = {"env_file": ".env"}


# Instanță globală folosită în toată aplicația
settings = Settings()
