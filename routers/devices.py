import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.db import Device, User, get_db
from models.schemas import DeviceCreate, DeviceResponse, DeviceUpdate
from services.auth_service import get_current_user
from utils.constants import SUPPORTED_IR_ACTIONS
from utils.exceptions import DeviceNotFoundException, InvalidMacAddressException
from utils.helpers import validate_mac_address

router = APIRouter(prefix="/devices", tags=["Dispozitive"])


def _get_owned_device(device_id: int, current_user: User, db: Session) -> Device:
    """Helper: caută dispozitivul și verifică ownership-ul. Aruncă 404 dacă nu există."""
    device = db.query(Device).filter(
        Device.id == device_id,
        Device.owner_id == current_user.id,
    ).first()
    if not device:
        raise DeviceNotFoundException()
    return device


@router.get("/", response_model=List[DeviceResponse])
def list_devices(
    room: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returnează toate dispozitivele user-ului curent, opțional filtrate după cameră."""
    query = db.query(Device).filter(Device.owner_id == current_user.id)
    if room:
        query = query.filter(Device.room == room)
    return query.all()


@router.post("/", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
def create_device(
    date: DeviceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Adaugă un dispozitiv nou asociat user-ului curent."""
    # Adresa MAC este obligatorie și trebuie validată pentru dispozitivele WoL
    if date.device_type == "wol":
        if not date.mac_address:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MAC address obligatoriu pentru WoL",
            )
        if not validate_mac_address(date.mac_address):
            raise InvalidMacAddressException()

    # Codurile IR se stochează ca JSON string în coloana Text
    ir_codes_str = json.dumps(date.ir_codes) if date.ir_codes else None

    device_nou = Device(
        name=date.name,
        device_type=date.device_type,
        room=date.room,
        mqtt_topic=date.mqtt_topic,
        mac_address=date.mac_address,
        ir_codes=ir_codes_str,
        owner_id=current_user.id,
    )
    db.add(device_nou)
    db.commit()
    db.refresh(device_nou)
    return device_nou


@router.get("/supported-actions")
def get_supported_actions():
    """Returnează acțiunile IR suportate per tip de dispozitiv (din constants.py)."""
    return SUPPORTED_IR_ACTIONS


@router.get("/{device_id}", response_model=DeviceResponse)
def get_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returnează detaliile unui dispozitiv (doar dacă aparține user-ului curent)."""
    return _get_owned_device(device_id, current_user, db)


@router.put("/{device_id}", response_model=DeviceResponse)
def update_device(
    device_id: int,
    date: DeviceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Actualizează câmpurile unui dispozitiv. Doar câmpurile trimise sunt modificate."""
    device = _get_owned_device(device_id, current_user, db)

    campuri_actualizate = date.model_dump(exclude_unset=True)

    # Convertim ir_codes din dict la JSON string dacă a fost trimis
    if "ir_codes" in campuri_actualizate and isinstance(campuri_actualizate["ir_codes"], dict):
        campuri_actualizate["ir_codes"] = json.dumps(campuri_actualizate["ir_codes"])

    for camp, valoare in campuri_actualizate.items():
        setattr(device, camp, valoare)

    db.commit()
    db.refresh(device)
    return device


@router.delete("/{device_id}")
def delete_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Șterge un dispozitiv și toate comenzile asociate (cascade)."""
    device = _get_owned_device(device_id, current_user, db)
    db.delete(device)
    db.commit()
    return {"message": "Dispozitivul a fost șters"}
