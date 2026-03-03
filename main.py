import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.db import Base, engine
from routers.auth import router as auth_router
from routers.commands import router as commands_router
from routers.dashboard import router as dashboard_router
from routers.devices import router as devices_router
from routers.notifications import router as notifications_router
from routers.rooms import router as rooms_router
from routers.routines import router as routines_router
from routers.scenes import router as scenes_router
from services.mqtt_service import mqtt_service
from services.scheduler_service import scheduler_service
from utils.middleware import ActivityMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Pornire aplicație ---
    Base.metadata.create_all(bind=engine)

    try:
        mqtt_service.connect()
    except Exception as e:
        logger.warning("MQTT indisponibil la startup: %s", e)

    scheduler_service.start()

    yield

    # --- Oprire aplicație ---
    scheduler_service.stop()
    mqtt_service.disconnect()


app = FastAPI(
    title="Smart Home API",
    version="1.0.0",
    description="Backend pentru sistemul IoT de automatizare a dispozitivelor non-smart",
    lifespan=lifespan,
)

# Middleware CORS permisiv pentru development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware de activity logging (adăugat după CORS)
app.add_middleware(ActivityMiddleware)

# Înregistrare routere cu prefixul /api
app.include_router(auth_router, prefix="/api")
app.include_router(devices_router, prefix="/api")
app.include_router(commands_router, prefix="/api")
app.include_router(routines_router, prefix="/api")
app.include_router(rooms_router, prefix="/api")
app.include_router(scenes_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")


@app.get("/")
def root():
    """Endpoint de verificare a stării serviciului."""
    return {"status": "online", "service": "Smart Home API"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
