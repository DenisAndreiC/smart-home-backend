from .auth import router as auth_router
from .commands import router as commands_router
from .dashboard import router as dashboard_router
from .devices import router as devices_router
from .notifications import router as notifications_router
from .rooms import router as rooms_router
from .routines import router as routines_router
from .scenes import router as scenes_router

__all__ = [
    "auth_router", "devices_router", "commands_router", "routines_router",
    "rooms_router", "scenes_router", "dashboard_router", "notifications_router",
]
