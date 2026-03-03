from enum import Enum


class DeviceType(str, Enum):
    """Tipurile de dispozitive suportate de sistem."""
    IR_RGB = "ir_rgb"
    IR_TV = "ir_tv"
    IR_AC = "ir_ac"
    RELAY = "relay"
    WOL = "wol"


class CommandSource(str, Enum):
    """Sursa unei comenzi — folosit pentru filtrare în algoritmul ML."""
    APP = "app"
    ROUTINE = "routine"
    SCHEDULE = "schedule"
    SCENE = "scene"         # Comandă generată de execuția unei scene


class HomeRoom(str, Enum):
    """Camerele predefinite ale locuinței (enum pentru validare rapidă)."""
    LIVING = "Living"
    DORMITOR = "Dormitor"
    BUCATARIE = "Bucătărie"
    BIROU = "Birou"
    BAIE = "Baie"


class NotificationType(str, Enum):
    """Tipul notificării — determină culoarea și iconița în aplicație."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


class ActivityAction(str, Enum):
    """Acțiunile logate în ActivityLog."""
    DEVICE_CREATE = "device.create"
    DEVICE_DELETE = "device.delete"
    COMMAND_SEND = "command.send"
    ROUTINE_EXECUTE = "routine.execute"
    SCENE_EXECUTE = "scene.execute"
    USER_LOGIN = "user.login"
    ML_DETECT = "ml.detect"
