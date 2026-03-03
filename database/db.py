from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from config import settings

# Motor SQLAlchemy — conectare la baza de date din settings
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Modele
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relații existente
    devices: Mapped[list["Device"]] = relationship("Device", back_populates="owner")
    commands: Mapped[list["Command"]] = relationship("Command", back_populates="user")
    routines: Mapped[list["Routine"]] = relationship("Routine", back_populates="user")
    # Relații noi
    rooms: Mapped[list["Room"]] = relationship("Room", back_populates="owner", cascade="all, delete-orphan")
    scenes: Mapped[list["Scene"]] = relationship("Scene", back_populates="owner", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )
    activity_logs: Mapped[list["ActivityLog"]] = relationship("ActivityLog", back_populates="user")
    preferences: Mapped["UserPreferences | None"] = relationship(
        "UserPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class Room(Base):
    """Camera fizică din locuință — dispozitivele pot fi asociate unei camere."""
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Iconița pentru aplicație (ex: "sofa", "bed", "utensils")
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner: Mapped["User"] = relationship("User", back_populates="rooms")
    devices: Mapped[list["Device"]] = relationship("Device", back_populates="room_ref")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    device_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Câmp legacy — păstrat pentru compatibilitate
    room: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Câmp nou — FK către tabelul rooms
    room_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("rooms.id"), nullable=True)
    mqtt_topic: Mapped[str] = mapped_column(String(255), nullable=False)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_status: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mac_address: Mapped[str | None] = mapped_column(String(17), nullable=True)
    ir_codes: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner: Mapped["User"] = relationship("User", back_populates="devices")
    commands: Mapped[list["Command"]] = relationship(
        "Command", back_populates="device", cascade="all, delete-orphan"
    )
    room_ref: Mapped["Room | None"] = relationship("Room", back_populates="devices")
    scene_actions: Mapped[list["SceneAction"]] = relationship("SceneAction", back_populates="device")


class Scene(Base):
    """Scenă — grupare de comenzi executate simultan sau cu delay (ex: 'Mod Film')."""
    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner: Mapped["User"] = relationship("User", back_populates="scenes")
    # Cascade on delete — acțiunile se șterg odată cu scena
    actions: Mapped[list["SceneAction"]] = relationship(
        "SceneAction", back_populates="scene", cascade="all, delete-orphan"
    )


class SceneAction(Base):
    """O acțiune individuală dintr-o scenă (comandă trimisă unui dispozitiv)."""
    __tablename__ = "scene_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scene_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Ordinea de execuție în cadrul scenei
    exec_order: Mapped[int] = mapped_column(Integer, default=0)
    # Delay în secunde înainte de a executa această acțiune
    delay_seconds: Mapped[int] = mapped_column(Integer, default=0)

    scene: Mapped["Scene"] = relationship("Scene", back_populates="actions")
    device: Mapped["Device"] = relationship("Device", back_populates="scene_actions")


class Command(Base):
    """
    Tabel CRITIC pentru algoritmul ML.
    Fiecare comandă trimisă de utilizator (sau generată de o rutină/scenă) se salvează aici.
    """
    __tablename__ = "commands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="app")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    device: Mapped["Device"] = relationship("Device", back_populates="commands")
    user: Mapped["User"] = relationship("User", back_populates="commands")


class Routine(Base):
    __tablename__ = "routines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trigger_time: Mapped[str] = mapped_column(String(5), nullable=False)
    days_of_week: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ml_suggested: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship("User", back_populates="routines")
    device: Mapped["Device"] = relationship("Device")


class Notification(Base):
    """Notificare push pentru utilizator (comenzi, rutine, ML, scene)."""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # Tipuri: "info", "warning", "error", "success"
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="info")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship("User", back_populates="notifications")


class ActivityLog(Base):
    """Jurnal de activitate — înregistrează toate acțiunile importante din sistem."""
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # user_id nullable — null pentru acțiuni generate de sistem
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user: Mapped["User | None"] = relationship("User", back_populates="activity_logs")


class UserPreferences(Base):
    """Preferințele personalizate ale unui utilizator (one-to-one cu User)."""
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    tz: Mapped[str] = mapped_column("timezone", String(50), default="Europe/Bucharest")
    language: Mapped[str] = mapped_column(String(10), default="ro")
    theme: Mapped[str] = mapped_column(String(20), default="dark")
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_detect_routines: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship("User", back_populates="preferences")


# ---------------------------------------------------------------------------
# Dependency FastAPI — sesiune per request
# ---------------------------------------------------------------------------


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Creare automată a tabelelor la pornirea aplicației
Base.metadata.create_all(bind=engine)
