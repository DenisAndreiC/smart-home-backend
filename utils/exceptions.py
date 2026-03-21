from fastapi import HTTPException, status


class SmartHomeException(HTTPException):
    """
    Exceptie de baza pentru toate erorile aplicatiei Smart Home.
    Mosteneste HTTPException pentru a fi returnata automat de FastAPI ca raspuns HTTP.
    """


class DeviceNotFoundException(SmartHomeException):
    """Ridicata cand dispozitivul cautat nu exista sau nu apartine utilizatorului."""

    def __init__(self):
        # HTTP 404 - resursa nu a fost gasita
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dispozitivul nu a fost gasit",
        )


class DeviceNotOwnedException(SmartHomeException):
    """Ridicata cand utilizatorul incearca sa acceseze un dispozitiv al altui user."""

    def __init__(self):
        # HTTP 403 - acces interzis (resursa exista dar nu ai permisiune)
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nu aveti permisiunea de a accesa acest dispozitiv",
        )


class InvalidCredentialsException(SmartHomeException):
    """Ridicata cand token-ul JWT lipseste, este invalid sau a expirat."""

    def __init__(self):
        # HTTP 401 - neautorizat; headerul WWW-Authenticate indica schema Bearer
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalid sau expirat",
            headers={"WWW-Authenticate": "Bearer"},
        )


class DuplicateEmailException(SmartHomeException):
    """Ridicata la inregistrare cand email-ul este deja folosit de alt cont."""

    def __init__(self):
        # HTTP 400 - cerere invalida (date duplicate)
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email-ul este deja inregistrat",
        )


class DuplicateUsernameException(SmartHomeException):
    """Ridicata la inregistrare cand username-ul este deja ocupat."""

    def __init__(self):
        # HTTP 400 - cerere invalida (username duplicat)
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username-ul este deja folosit",
        )


class InvalidMacAddressException(SmartHomeException):
    """Ridicata cand adresa MAC nu respecta formatul AA:BB:CC:DD:EE:FF."""

    def __init__(self):
        # HTTP 400 - format invalid pentru adresa MAC
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Adresa MAC este invalida (format asteptat: AA:BB:CC:DD:EE:FF)",
        )


class MQTTPublishException(SmartHomeException):
    """Ridicata cand publicarea unei comenzi pe broker-ul MQTT esueaza."""

    def __init__(self):
        # HTTP 503 - serviciu indisponibil (broker MQTT offline sau inaccesibil)
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nu s-a putut publica comanda pe broker-ul MQTT",
        )
