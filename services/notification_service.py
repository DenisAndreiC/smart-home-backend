"""
Serviciu helper pentru crearea notificărilor.
Funcțiile primesc sesiunea DB și adaugă notificarea — caller-ul face commit.
"""
from sqlalchemy.orm import Session

from database.db import Notification


def create_notification(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    type: str = "info",
) -> Notification:
    """Creează o notificare și o adaugă în sesiunea DB (fără commit)."""
    notificare = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=type,
    )
    db.add(notificare)
    return notificare


def notify_device_command(
    db: Session,
    user_id: int,
    device_name: str,
    action: str,
    value: str | None,
) -> Notification:
    """Notificare trimisă după executarea unei comenzi manuale."""
    value_str = f" {value}" if value else ""
    return create_notification(
        db,
        user_id,
        title="Comandă trimisă",
        message=f"Comandă trimisă: {action}{value_str} → {device_name}",
        type="success",
    )


def notify_routine_executed(
    db: Session,
    user_id: int,
    routine_name: str,
) -> Notification:
    """Notificare trimisă când scheduler-ul execută o rutină activă."""
    return create_notification(
        db,
        user_id,
        title="Rutină executată",
        message=f"Rutina '{routine_name}' a fost executată automat",
        type="info",
    )


def notify_scene_executed(
    db: Session,
    user_id: int,
    scene_name: str,
    actions_count: int,
) -> Notification:
    """Notificare trimisă după activarea unei scene."""
    return create_notification(
        db,
        user_id,
        title="Scenă executată",
        message=f"Scena '{scene_name}' executată ({actions_count} acțiuni)",
        type="success",
    )


def notify_ml_routines_detected(
    db: Session,
    user_id: int,
    count: int,
) -> Notification:
    """Notificare trimisă când algoritmul ML detectează rutine noi."""
    return create_notification(
        db,
        user_id,
        title="Rutine detectate de ML",
        message=f"ML a detectat {count} rutine noi! Verifică în secțiunea Rutine.",
        type="info",
    )
