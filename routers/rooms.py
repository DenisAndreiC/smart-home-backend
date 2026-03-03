from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.db import Device, Room, User, get_db
from models.schemas import RoomCreate, RoomResponse, RoomUpdate
from services.auth_service import get_current_user

router = APIRouter(prefix="/rooms", tags=["Camere"])


def _get_owned_room(room_id: int, current_user: User, db: Session) -> Room:
    """Helper: returnează camera dacă aparține user-ului curent, altfel 404."""
    room = db.query(Room).filter(
        Room.id == room_id,
        Room.owner_id == current_user.id,
    ).first()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera nu a fost găsită")
    return room


def _room_to_response(room: Room) -> RoomResponse:
    """Convertește modelul ORM la schema de răspuns (include device_count)."""
    return RoomResponse(
        id=room.id,
        name=room.name,
        icon=room.icon,
        device_count=len(room.devices),
    )


@router.get("/", response_model=List[RoomResponse])
def list_rooms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returnează toate camerele user-ului curent cu numărul de dispozitive per cameră."""
    rooms = db.query(Room).filter(Room.owner_id == current_user.id).all()
    return [_room_to_response(r) for r in rooms]


@router.post("/", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
def create_room(
    date: RoomCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Creează o cameră nouă asociată user-ului curent."""
    camera = Room(
        name=date.name,
        icon=date.icon,
        owner_id=current_user.id,
    )
    db.add(camera)
    db.commit()
    db.refresh(camera)
    return _room_to_response(camera)


@router.put("/{room_id}", response_model=RoomResponse)
def update_room(
    room_id: int,
    date: RoomUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Actualizează numele sau iconița unei camere."""
    camera = _get_owned_room(room_id, current_user, db)
    campuri = date.model_dump(exclude_unset=True)
    for camp, val in campuri.items():
        setattr(camera, camp, val)
    db.commit()
    db.refresh(camera)
    return _room_to_response(camera)


@router.delete("/{room_id}")
def delete_room(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Șterge o cameră. Dispozitivele asociate NU se șterg —
    room_id-ul lor este setat la null (dezasociere, nu ștergere).
    """
    camera = _get_owned_room(room_id, current_user, db)

    # Dezasociați dispozitivele fără a le șterge
    db.query(Device).filter(Device.room_id == room_id).update(
        {Device.room_id: None}, synchronize_session="fetch"
    )
    db.delete(camera)
    db.commit()
    return {"message": "Camera a fost ștearsă"}
