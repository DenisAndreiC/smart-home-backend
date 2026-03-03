from fastapi import HTTPException, status


class SmartHomeException(HTTPException):
    """Excepție de bază pentru toate erorile aplicației Smart Home."""


class DeviceNotFoundException(SmartHomeException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dispozitivul nu a fost găsit",
        )


class DeviceNotOwnedException(SmartHomeException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nu aveți permisiunea de a accesa acest dispozitiv",
        )


class InvalidCredentialsException(SmartHomeException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalid sau expirat",
            headers={"WWW-Authenticate": "Bearer"},
        )


class DuplicateEmailException(SmartHomeException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email-ul este deja înregistrat",
        )


class DuplicateUsernameException(SmartHomeException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username-ul este deja folosit",
        )


class InvalidMacAddressException(SmartHomeException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Adresa MAC este invalidă (format așteptat: AA:BB:CC:DD:EE:FF)",
        )


class MQTTPublishException(SmartHomeException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nu s-a putut publica comanda pe broker-ul MQTT",
        )
