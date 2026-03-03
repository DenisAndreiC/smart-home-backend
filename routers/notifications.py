from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.db import Notification, User, get_db
from models.schemas import NotificationResponse
from services.auth_service import get_current_user

router = APIRouter(prefix="/notifications", tags=["Notificări"])


def _get_owned_notification(notif_id: int, current_user: User, db: Session) -> Notification:
    """Helper: returnează notificarea dacă aparține user-ului curent, altfel 404."""
    notif = db.query(Notification).filter(
        Notification.id == notif_id,
        Notification.user_id == current_user.id,
    ).first()
    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notificarea nu a fost găsită",
        )
    return notif


@router.get("/", response_model=List[NotificationResponse])
def list_notifications(
    unread_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returnează notificările user-ului curent, opțional doar cele necitite."""
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        query = query.filter(Notification.is_read == False)  # noqa: E712
    return query.order_by(Notification.created_at.desc()).all()


@router.get("/count")
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returnează numărul de notificări necitite — pentru badge în aplicație."""
    count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read == False)  # noqa: E712
        .count()
    )
    return {"unread_count": count}


@router.put("/{notification_id}/read", response_model=NotificationResponse)
def mark_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marchează o notificare ca citită."""
    notif = _get_owned_notification(notification_id, current_user, db)
    notif.is_read = True
    db.commit()
    db.refresh(notif)
    return notif


@router.put("/read-all")
def mark_all_as_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marchează toate notificările user-ului ca citite."""
    actualizate = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read == False)  # noqa: E712
        .update({"is_read": True}, synchronize_session="fetch")
    )
    db.commit()
    return {"message": f"{actualizate} notificări marcate ca citite"}


@router.delete("/{notification_id}")
def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Șterge o notificare."""
    notif = _get_owned_notification(notification_id, current_user, db)
    db.delete(notif)
    db.commit()
    return {"message": "Notificarea a fost ștearsă"}
