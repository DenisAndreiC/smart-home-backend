import logging
import os
from contextlib import asynccontextmanager

# Configure root logger so INFO messages from all app modules appear in Docker logs
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
)

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from database.db import Base, engine
from routers.auth import router as auth_router
from routers.commands import router as commands_router
from routers.dashboard import router as dashboard_router
from routers.devices import router as devices_router
from routers.notifications import router as notifications_router
from routers.rooms import router as rooms_router
from routers.routines import router as routines_router
from routers.scenes import router as scenes_router
from routers.stats import router as stats_router
from routers.users import router as users_router
from services.mqtt_service import mqtt_service
from services.scheduler_service import scheduler_service
from utils.middleware import ActivityMiddleware

# Logger dedicat acestui modul
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Context manager pentru ciclul de viata al aplicatiei FastAPI.
    Bloc inainte de yield: startup (creare tabele, conectare MQTT, pornire scheduler).
    Bloc dupa yield: shutdown (oprire scheduler, deconectare MQTT).
    """
    # --- Pornire aplicatie ---

    # Creeaza toate tabelele in baza de date daca nu exista deja
    Base.metadata.create_all(bind=engine)

    # Migrare simpla: adauga coloanele noi la tabelele existente daca lipsesc
    # SQLite nu suporta IF NOT EXISTS pe ALTER TABLE, deci folosim try/except
    with engine.connect() as conn:
        for ddl in [
            "ALTER TABLE users ADD COLUMN display_name VARCHAR(100)",
            "ALTER TABLE users ADD COLUMN avatar_url VARCHAR(500)",
            "ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT 0",
            "ALTER TABLE users ADD COLUMN verification_token VARCHAR(100)",
            "ALTER TABLE users ADD COLUMN reset_token VARCHAR(100)",
            "ALTER TABLE devices ADD COLUMN ir_remote_type VARCHAR(10)",
            "ALTER TABLE users ADD COLUMN password_change_code VARCHAR(6)",
            "ALTER TABLE users ADD COLUMN password_change_code_expires DATETIME",
        ]:
            try:
                conn.execute(text(ddl))
                conn.commit()
            except Exception:
                pass  # Coloana exista deja

    # Conectare la brokerul MQTT; eroarea e prinsa pentru a nu bloca startupul
    try:
        mqtt_service.connect()
    except Exception as e:
        logger.warning("MQTT indisponibil la startup: %s", e)

    # Porneste scheduler-ul APScheduler pentru rutinele automate
    scheduler_service.start()

    # Cedeaza controlul catre aplicatie
    yield

    # --- Oprire aplicatie ---

    # Opreste scheduler-ul graceful (fara sa astepte job-urile in curs)
    scheduler_service.stop()

    # Deconecteaza clientul MQTT
    mqtt_service.disconnect()


# Instantierea aplicatiei FastAPI cu metadate pentru Swagger UI
app = FastAPI(
    title="Smart Home API",
    version="1.0.0",
    description="Backend pentru sistemul IoT de automatizare a dispozitivelor non-smart",
    lifespan=lifespan,
)

# Middleware CORS permisiv pentru development
# In productie, allow_origins trebuie restrictionat la domeniul aplicatiei
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Permite orice origine
    allow_credentials=True,     # Permite cookies/authorization headers
    allow_methods=["*"],        # Permite toate metodele HTTP
    allow_headers=["*"],        # Permite orice header
)

# Middleware de activity logging (adaugat dupa CORS)
# Inregistreaza in DB toate operatiile POST/PUT/DELETE/PATCH
app.add_middleware(ActivityMiddleware)

# Servim fisierele statice (avatare etc.)
os.makedirs("static/avatars", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Inregistrare routere cu prefixul /api
app.include_router(auth_router, prefix="/api")
app.include_router(devices_router, prefix="/api")
app.include_router(commands_router, prefix="/api")
app.include_router(routines_router, prefix="/api")
app.include_router(rooms_router, prefix="/api")
app.include_router(scenes_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(stats_router, prefix="/api")
app.include_router(users_router, prefix="/api")


@app.get("/")
def root():
    """Endpoint de verificare a starii serviciului (health check)."""
    # Returneaza un JSON simplu cu statusul si numele serviciului
    return {"status": "online", "service": "Smart Home API"}


if __name__ == "__main__":
    # Pornire directa cu uvicorn in modul reload pentru development
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
