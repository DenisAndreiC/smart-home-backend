from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.db import Command, Device, User, get_db
from models.schemas import CommandResponse, CommandSend, WolRequest
from services.auth_service import get_current_user
from services.mqtt_service import mqtt_service
from services.notification_service import notify_device_command
from services.wol_service import wake_device
from utils.constants import MAX_COMMAND_HISTORY
from utils.exceptions import DeviceNotFoundException

router = APIRouter(prefix="/commands", tags=["Comenzi"])


def _get_owned_device(device_id: int, current_user: User, db: Session) -> Device:
    """Helper: returnează dispozitivul dacă aparține user-ului curent, altfel 404."""
    device = db.query(Device).filter(
        Device.id == device_id,
        Device.owner_id == current_user.id,
    ).first()
    if not device:
        raise DeviceNotFoundException()
    return device


@router.post("/send", response_model=CommandResponse)
def send_command(
    date: CommandSend,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trimite o comandă la un dispozitiv prin MQTT sau Wake-on-LAN.
    Salvează comanda în DB și creează notificare pentru utilizator.
    """
    device = _get_owned_device(date.device_id, current_user, db)

    if device.device_type == "wol":
        wake_device(device.mac_address)
    else:
        mqtt_service.publish_command(device.mqtt_topic, date.action, date.value)

    # Înregistrăm comanda — CRITIC pentru ML
    comanda = Command(
        device_id=device.id,
        user_id=current_user.id,
        action=date.action,
        value=date.value,
        source="app",
    )
    db.add(comanda)
    device.last_status = date.value

    # Notificare pentru utilizator
    notify_device_command(db, current_user.id, device.name, date.action, date.value)
    db.commit()
    db.refresh(comanda)

    return CommandResponse(
        id=comanda.id,
        device_id=comanda.device_id,
        action=comanda.action,
        value=comanda.value,
        source=comanda.source,
        timestamp=comanda.timestamp,
        device_name=device.name,
    )


@router.get("/history", response_model=List[CommandResponse])
def get_history(
    device_id: Optional[int] = None,
    limit: int = MAX_COMMAND_HISTORY,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returnează istoricul comenzilor user-ului curent.
    Limita implicită e MAX_COMMAND_HISTORY din constants.py.
    """
    query = (
        db.query(Command, Device.name.label("device_name"))
        .join(Device, Command.device_id == Device.id)
        .filter(Command.user_id == current_user.id)
    )
    if device_id:
        query = query.filter(Command.device_id == device_id)

    rezultate = query.order_by(Command.timestamp.desc()).limit(limit).all()
    return [
        CommandResponse(
            id=cmd.id,
            device_id=cmd.device_id,
            action=cmd.action,
            value=cmd.value,
            source=cmd.source,
            timestamp=cmd.timestamp,
            device_name=device_name,
        )
        for cmd, device_name in rezultate
    ]


@router.post("/wol")
def wake_on_lan(
    date: WolRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Endpoint dedicat Wake-on-LAN. Trimite magic packet și înregistrează comanda."""
    device = _get_owned_device(date.device_id, current_user, db)

    if device.device_type != "wol":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dispozitivul nu este de tip Wake-on-LAN",
        )

    succes = wake_device(device.mac_address)
    if not succes:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Trimiterea magic packet a eșuat — verificați adresa MAC",
        )

    comanda = Command(
        device_id=device.id,
        user_id=current_user.id,
        action="wol",
        value="magic_packet",
        source="app",
    )
    db.add(comanda)
    notify_device_command(db, current_user.id, device.name, "wake", None)
    db.commit()

    return {"message": "Magic packet trimis", "mac_address": device.mac_address}
