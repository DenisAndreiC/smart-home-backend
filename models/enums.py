from enum import Enum


class DeviceType(str, Enum):
    """Tipurile de dispozitive suportate de sistem."""

    IR_RGB = "ir_rgb"       # Bec LED RGB controlat prin infrarosu
    IR_TV = "ir_tv"         # Televizor controlat prin infrarosu
    IR_AC = "ir_ac"         # Aer conditionat controlat prin infrarosu
    RELAY = "relay"         # Priza sau bec 220V controlat prin modul relay
    WOL = "wol"             # Calculator trezit prin pachet Wake-on-LAN


class CommandSource(str, Enum):
    """Sursa unei comenzi - folosit pentru filtrare in algoritmul ML."""

    APP = "app"             # Comanda trimisa manual de utilizator din aplicatie
    ROUTINE = "routine"     # Comanda executata automat de un scheduler de rutina
    SCHEDULE = "schedule"   # Comanda executata printr-un schedule extern
    SCENE = "scene"         # Comanda generata de executia unei scene


class HomeRoom(str, Enum):
    """Camerele predefinite ale locuintei (enum pentru validare rapida)."""

    LIVING = "Living"           # Camera de zi
    DORMITOR = "Dormitor"       # Dormitor
    BUCATARIE = "Bucatarie"     # Bucatarie
    BIROU = "Birou"             # Birou / camera de lucru
    BAIE = "Baie"               # Baie


class NotificationType(str, Enum):
    """Tipul notificarii - determina culoarea si iconita in aplicatie."""

    INFO = "info"           # Notificare informativa (status, confirmare)
    WARNING = "warning"     # Avertisment care necesita atentia utilizatorului
    ERROR = "error"         # Eroare grava in sistem
    SUCCESS = "success"     # Operatie finalizata cu succes


class ActivityAction(str, Enum):
    """Actiunile logate in ActivityLog pentru audit trail."""

    DEVICE_CREATE = "device.create"         # Dispozitiv nou adaugat
    DEVICE_DELETE = "device.delete"         # Dispozitiv sters
    COMMAND_SEND = "command.send"           # Comanda trimisa catre dispozitiv
    ROUTINE_EXECUTE = "routine.execute"     # Rutina executata de scheduler
    SCENE_EXECUTE = "scene.execute"         # Scena executata de utilizator
    USER_LOGIN = "user.login"               # Autentificare utilizator
    ML_DETECT = "ml.detect"                 # Detectie rutine prin ML
