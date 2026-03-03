import asyncio
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.db import ActivityLog, Command, Device, Scene, SceneAction, User, get_db
from models.schemas import SceneCreate, SceneResponse, SceneActionResponse, SceneUpdate
from services.auth_service import get_current_user
from services.mqtt_service import mqtt_service
from services.notification_service import notify_scene_executed
from services.wol_service import wake_device

router = APIRouter(prefix="/scenes", tags=["Scene"])


def _get_owned_scene(scene_id: int, current_user: User, db: Session) -> Scene:
    """Helper: returnează scena dacă aparține user-ului curent, altfel 404."""
    scene = db.query(Scene).filter(
        Scene.id == scene_id,
        Scene.owner_id == current_user.id,
    ).first()
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scena nu a fost găsită")
    return scene


def _action_to_response(action: SceneAction) -> SceneActionResponse:
    """Convertește o SceneAction ORM la schema de răspuns (include device_name)."""
    device_name = action.device.name if action.device else f"Device {action.device_id}"
    return SceneActionResponse(
        id=action.id,
        device_id=action.device_id,
        device_name=device_name,
        action=action.action,
        value=action.value,
        order=action.exec_order,
        delay_seconds=action.delay_seconds,
    )


def _scene_to_response(scene: Scene) -> SceneResponse:
    """Convertește o Scene ORM la schema de răspuns cu acțiunile sortate."""
    actions_sorted = sorted(scene.actions, key=lambda a: a.exec_order)
    return SceneResponse(
        id=scene.id,
        name=scene.name,
        icon=scene.icon,
        is_active=scene.is_active,
        created_at=scene.created_at,
        actions=[_action_to_response(a) for a in actions_sorted],
    )


@router.get("/", response_model=List[SceneResponse])
def list_scenes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returnează toate scenele user-ului curent cu acțiunile incluse."""
    scenes = db.query(Scene).filter(Scene.owner_id == current_user.id).all()
    return [_scene_to_response(s) for s in scenes]


@router.post("/", response_model=SceneResponse, status_code=status.HTTP_201_CREATED)
def create_scene(
    date: SceneCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Creează o scenă nouă cu acțiunile sale. Verifică ownership pe fiecare device."""
    # Validăm ownership pe toate dispozitivele din acțiuni
    for act in date.actions:
        device = db.query(Device).filter(
            Device.id == act.device_id,
            Device.owner_id == current_user.id,
        ).first()
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dispozitivul {act.device_id} nu a fost găsit sau nu îți aparține",
            )

    scena = Scene(
        name=date.name,
        icon=date.icon,
        owner_id=current_user.id,
        is_active=True,
    )
    db.add(scena)
    db.flush()  # obținem scena.id înainte de commit

    for act in date.actions:
        actiune = SceneAction(
            scene_id=scena.id,
            device_id=act.device_id,
            action=act.action,
            value=act.value,
            exec_order=act.order,
            delay_seconds=act.delay_seconds,
        )
        db.add(actiune)

    db.commit()
    db.refresh(scena)
    return _scene_to_response(scena)


@router.get("/{scene_id}", response_model=SceneResponse)
def get_scene(
    scene_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returnează detaliile unei scene cu toate acțiunile sale."""
    return _scene_to_response(_get_owned_scene(scene_id, current_user, db))


@router.post("/{scene_id}/execute")
async def execute_scene(
    scene_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Execută toate acțiunile scenei în ordine, respectând delay-urile.
    Salvează fiecare comandă în DB cu source='scene' pentru istoricul ML.
    """
    scene = _get_owned_scene(scene_id, current_user, db)
    actions = sorted(scene.actions, key=lambda a: a.exec_order)

    for act in actions:
        # Așteptăm delay-ul înainte de execuție (non-blocking)
        if act.delay_seconds > 0:
            await asyncio.sleep(act.delay_seconds)

        device = act.device
        if device.device_type == "wol":
            wake_device(device.mac_address)
        else:
            mqtt_service.publish_command(device.mqtt_topic, act.action, act.value)

        # Salvăm comanda în istoricul ML
        cmd = Command(
            device_id=device.id,
            user_id=current_user.id,
            action=act.action,
            value=act.value,
            source="scene",
        )
        db.add(cmd)

        # Logăm execuția în ActivityLog
        log = ActivityLog(
            user_id=current_user.id,
            action="scene.execute",
            entity_type="scene",
            entity_id=scene_id,
            details=f'{{"action": "{act.action}", "device": "{device.name}", "scene": "{scene.name}"}}',
        )
        db.add(log)

    # Notificare pentru utilizator
    notify_scene_executed(db, current_user.id, scene.name, len(actions))
    db.commit()

    return {"message": f"Scena '{scene.name}' executată", "actions_count": len(actions)}


@router.put("/{scene_id}", response_model=SceneResponse)
def update_scene(
    scene_id: int,
    date: SceneUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Actualizează o scenă. Dacă sunt trimise acțiuni noi,
    le înlocuiește complet pe cele vechi.
    """
    scene = _get_owned_scene(scene_id, current_user, db)

    if date.name is not None:
        scene.name = date.name
    if date.icon is not None:
        scene.icon = date.icon
    if date.is_active is not None:
        scene.is_active = date.is_active

    if date.actions is not None:
        # Validăm ownership pe noile dispozitive
        for act in date.actions:
            device = db.query(Device).filter(
                Device.id == act.device_id,
                Device.owner_id == current_user.id,
            ).first()
            if not device:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Dispozitivul {act.device_id} nu a fost găsit",
                )

        # Ștergem acțiunile vechi și creăm altele noi
        for old_action in list(scene.actions):
            db.delete(old_action)
        db.flush()

        for act in date.actions:
            actiune = SceneAction(
                scene_id=scene.id,
                device_id=act.device_id,
                action=act.action,
                value=act.value,
                exec_order=act.order,
                delay_seconds=act.delay_seconds,
            )
            db.add(actiune)

    db.commit()
    db.refresh(scene)
    return _scene_to_response(scene)


@router.delete("/{scene_id}")
def delete_scene(
    scene_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Șterge scena și toate acțiunile sale (cascade)."""
    scene = _get_owned_scene(scene_id, current_user, db)
    db.delete(scene)
    db.commit()
    return {"message": "Scena a fost ștearsă"}
