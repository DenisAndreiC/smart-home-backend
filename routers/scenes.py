"""
Router pentru gestionarea scenelor Smart Home.

O scena este un grup de comenzi executate secvential, cu delay optional intre ele.
Exemple: "Mod Film" (dimmer redus + TV ON), "Buna dimineata" (lumini + jaluzele).

Toate endpoint-urile necesita autentificare JWT prin dependency-ul get_current_user.
Prefixul /scenes este inregistrat cu /api in main.py -> URL final: /api/scenes/...
"""

import asyncio          # asyncio pentru await asyncio.sleep (delay non-blocking intre actiuni)
from typing import List  # List pentru adnotarile de tip din response_model

from fastapi import APIRouter, Depends, HTTPException, status  # componente FastAPI
from sqlalchemy.orm import Session                              # tipul sesiunii SQLAlchemy

# Modele ORM necesare pentru interogari si insertii
from database.db import ActivityLog, Command, Device, Scene, SceneAction, User, get_db

# Scheme Pydantic pentru validarea datelor de intrare si serializarea raspunsurilor
from models.schemas import SceneCreate, SceneResponse, SceneActionResponse, SceneUpdate

# Dependency de autentificare — injecteaza utilizatorul curent din token JWT
from services.auth_service import get_current_user

# Serviciul MQTT — trimite comenzile catre dispozitive prin broker
from services.mqtt_service import mqtt_service

# Helper pentru notificarea utilizatorului dupa executarea scenei
from services.notification_service import notify_scene_executed

# Functia Wake-on-LAN pentru dispozitivele de tip wol
from services.wol_service import wake_device

# Router cu prefix /scenes — toate rutele devin /api/scenes/...
router = APIRouter(prefix="/scenes", tags=["Scene"])


# ---------------------------------------------------------------------------
# Helper functions — reutilizate in mai multe endpoint-uri
# ---------------------------------------------------------------------------


def _get_owned_scene(scene_id: int, current_user: User, db: Session) -> Scene:
    """
    Returneaza scena cu ID-ul dat daca apartine utilizatorului curent.

    Combina doua conditii intr-un singur query pentru securitate:
    - scene_id trebuie sa existe in tabelul scenes
    - scene.owner_id trebuie sa fie egal cu current_user.id
    Returnand 404 in ambele cazuri (nu 403), evitam enumerarea resurselor altor useri.

    Parametri:
        scene_id     : ID-ul scenei cautate
        current_user : utilizatorul autentificat (injectat din token JWT)
        db           : sesiunea SQLAlchemy activa

    Returneaza:
        Obiectul Scene ORM daca exista si apartine utilizatorului

    Arunca:
        HTTPException 404 daca scena nu exista sau nu apartine userului curent
    """
    # Filtram simultan dupa id si owner_id pentru a verifica si existenta si proprietatea
    scene = db.query(Scene).filter(
        Scene.id == scene_id,           # scena trebuie sa existe cu acest ID
        Scene.owner_id == current_user.id,  # scena trebuie sa apartina userului curent
    ).first()

    # Daca scena nu a fost gasita (inexistenta sau alt owner) returnam 404
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scena nu a fost gasita")

    # Returnam obiectul Scene ORM valid
    return scene


def _action_to_response(action: SceneAction) -> SceneActionResponse:
    """
    Converteste un obiect SceneAction ORM la schema de raspuns Pydantic.

    Include device_name extras din relatia ORM action.device.
    Daca dispozitivul a fost sters intre timp, folosim un placeholder.

    Parametri:
        action : obiectul SceneAction ORM cu relatia device incarcata

    Returneaza:
        SceneActionResponse cu toate campurile populate
    """
    # Extragem numele dispozitivului din relatia ORM, cu fallback daca device e None
    device_name = action.device.name if action.device else f"Device {action.device_id}"

    # Construim si returnam schema de raspuns
    return SceneActionResponse(
        id=action.id,                       # ID-ul actiunii
        device_id=action.device_id,         # ID-ul dispozitivului tinta
        device_name=device_name,            # numele dispozitivului (din relatia ORM)
        action=action.action,               # tipul actiunii (power, color, brightness etc.)
        value=action.value,                 # valoarea parametrului actiunii (ON, RED, 50 etc.)
        order=action.exec_order,            # ordinea de executie in cadrul scenei
        delay_seconds=action.delay_seconds, # delay in secunde inainte de aceasta actiune
    )


def _scene_to_response(scene: Scene) -> SceneResponse:
    """
    Converteste un obiect Scene ORM la schema de raspuns Pydantic.

    Sorteaza actiunile dupa exec_order pentru a garanta ordinea corecta
    indiferent de ordinea in care SQLAlchemy le incarca din DB.

    Parametri:
        scene : obiectul Scene ORM cu relatia actions incarcata

    Returneaza:
        SceneResponse cu actiunile sortate dupa exec_order
    """
    # Sortam actiunile dupa campul exec_order (ordinea de executie)
    actions_sorted = sorted(scene.actions, key=lambda a: a.exec_order)

    # Construim si returnam schema de raspuns cu actiunile convertite
    return SceneResponse(
        id=scene.id,                                            # ID-ul scenei
        name=scene.name,                                        # numele scenei
        icon=scene.icon,                                        # iconita (optional)
        is_active=scene.is_active,                              # flag activare
        created_at=scene.created_at,                            # data crearii
        actions=[_action_to_response(a) for a in actions_sorted],  # lista actiunilor sortate
    )


# ---------------------------------------------------------------------------
# Endpoint-uri CRUD pentru scene
# ---------------------------------------------------------------------------


@router.get("/", response_model=List[SceneResponse])
def list_scenes(
    db: Session = Depends(get_db),                          # sesiunea DB injectata
    current_user: User = Depends(get_current_user),         # userul curent din JWT
):
    """
    Returneaza toate scenele utilizatorului curent cu actiunile incluse.

    Filtram dupa owner_id pentru a returna doar scenele proprii.
    Fiecare scena include lista completa de actiuni, sortata dupa exec_order.
    """
    # Interogam DB pentru toate scenele apartinand utilizatorului curent
    scenes = db.query(Scene).filter(Scene.owner_id == current_user.id).all()

    # Convertim fiecare obiect ORM la schema de raspuns si returnam lista
    return [_scene_to_response(s) for s in scenes]


@router.post("/", response_model=SceneResponse, status_code=status.HTTP_201_CREATED)
def create_scene(
    date: SceneCreate,                                       # datele scenei din body (validate Pydantic)
    db: Session = Depends(get_db),                          # sesiunea DB injectata
    current_user: User = Depends(get_current_user),         # userul curent din JWT
):
    """
    Creeaza o scena noua cu actiunile sale.

    Valideaza ownership pe fiecare dispozitiv din lista de actiuni.
    Foloseste db.flush() pentru a obtine ID-ul scenei inainte de commit,
    necesar pentru a lega SceneAction.scene_id la ID-ul corect.

    Returneaza 404 daca orice dispozitiv din actiuni nu apartine userului.
    """
    # --- Pasul 1: Validam ownership pe toate dispozitivele din actiuni ---
    # Iteratia se face inainte de a crea scena pentru a evita rollback-ul partial
    for act in date.actions:
        # Verificam ca fiecare dispozitiv din actiuni apartine userului curent
        device = db.query(Device).filter(
            Device.id == act.device_id,                 # dispozitivul trebuie sa existe
            Device.owner_id == current_user.id,         # si sa apartina userului curent
        ).first()

        # Daca dispozitivul nu e gasit sau nu apartine userului, returnam 404
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dispozitivul {act.device_id} nu a fost gasit sau nu iti apartine",
            )

    # --- Pasul 2: Cream obiectul Scene si il adaugam in sesiune ---
    scena = Scene(
        name=date.name,                 # numele scenei (ex: "Mod Film")
        icon=date.icon,                 # iconita optionala (ex: "film", "sun")
        owner_id=current_user.id,       # proprietarul scenei
        is_active=True,                 # scena este activa implicit la creare
    )
    db.add(scena)  # adaugam scena in sesiune (nu e inca in DB)

    # flush() scrie scena in DB si genereaza scena.id, dar nu face commit
    # Avem nevoie de scena.id pentru a crea SceneAction cu scene_id corect
    db.flush()

    # --- Pasul 3: Cream actiunile scenei legate de ID-ul generat ---
    for act in date.actions:
        # Cream obiectul SceneAction pentru fiecare actiune din lista
        actiune = SceneAction(
            scene_id=scena.id,              # ID-ul scenei parinte (generat de flush)
            device_id=act.device_id,        # dispozitivul tinta al actiunii
            action=act.action,              # tipul actiunii (power, color, brightness etc.)
            value=act.value,                # valoarea actiunii (ON, RED, 75 etc.)
            exec_order=act.order,           # ordinea de executie (0, 1, 2...)
            delay_seconds=act.delay_seconds,# delay in secunde inainte de executie
        )
        db.add(actiune)  # adaugam actiunea in sesiune

    # Comitem toate modificarile (scena + actiunile) intr-o singura tranzactie
    db.commit()

    # Reincarcam obiectul pentru a obtine actiunile cu ID-urile generate
    db.refresh(scena)

    # Convertim si returnam scena cu toate actiunile
    return _scene_to_response(scena)


@router.get("/{scene_id}", response_model=SceneResponse)
def get_scene(
    scene_id: int,                                           # ID-ul scenei din URL path
    db: Session = Depends(get_db),                          # sesiunea DB injectata
    current_user: User = Depends(get_current_user),         # userul curent din JWT
):
    """
    Returneaza detaliile unei scene cu toate actiunile sale.

    Foloseste _get_owned_scene pentru a verifica existenta si ownership.
    Actiunile sunt returnate sortate dupa exec_order.
    """
    # Obtinem scena verificand si ownership-ul; _get_owned_scene arunca 404 daca nu e gasita
    return _scene_to_response(_get_owned_scene(scene_id, current_user, db))


@router.post("/{scene_id}/execute")
async def execute_scene(
    scene_id: int,                                           # ID-ul scenei de executat
    db: Session = Depends(get_db),                          # sesiunea DB injectata
    current_user: User = Depends(get_current_user),         # userul curent din JWT
):
    """
    Executa toate actiunile scenei in ordine, respectand delay-urile.

    Fluxul de executie pentru fiecare actiune:
      1. Asteptam delay_seconds (non-blocking cu asyncio.sleep)
      2. Trimitem comanda MQTT sau pachetul WoL
      3. Salvam comanda in DB cu source='scene' (pentru istoricul ML)
      4. Logam executia in ActivityLog

    La final se trimite o notificare utilizatorului si se face un singur db.commit().

    Returneaza numarul de actiuni executate pentru confirmare.
    """
    # Obtinem scena cu verificarea ownership-ului
    scene = _get_owned_scene(scene_id, current_user, db)

    # Sortam actiunile dupa exec_order pentru a le executa in ordinea corecta
    actions = sorted(scene.actions, key=lambda a: a.exec_order)

    # Iteram fiecare actiune si o executam in ordine
    for i, act in enumerate(actions):
        # --- Pasul 1: Asteptam delay-ul inainte de executie (non-blocking) ---
        # delay_seconds din scena + 0.5s intre comenzi consecutive
        if act.delay_seconds > 0:
            await asyncio.sleep(act.delay_seconds)
        elif i > 0:
            # 0.5s intre comenzi consecutive pentru a nu satura ESP32-ul
            await asyncio.sleep(0.5)

        # Obtinem dispozitivul tinta al actiunii din relatia ORM
        device = act.device

        # --- Pasul 2: Trimitem comanda catre dispozitiv prin canalul corespunzator ---
        if device.device_type == "wol":
            # Dispozitiv WoL: trimitem magic packet prin UDP (nu MQTT)
            wake_device(device.mac_address)
        elif device.device_type in ("ir_tv", "ir_ac", "ir_rgb"):
            # Dispozitive IR — trimitem pe topic-ul ESP32 IR Controller
            mqtt_service.publish_ir_command(device.name, device.device_type, act.action, act.value)
        elif device.device_type == "relay":
            # Dispozitive Relay — trimitem pe topic-ul specific relay-ului
            mqtt_service.publish_relay_command(device.mqtt_topic, act.action, act.value)
        else:
            # Fallback pentru tipuri necunoscute
            mqtt_service.publish_command(device.mqtt_topic, act.action, act.value)

        # Actualizam last_status al dispozitivului cu valoarea trimisa
        device.last_status = act.value

        # --- Pasul 3: Salvam comanda in istoricul ML cu source='scene' ---
        # source='scene' permite filtrarea comenzilor automate vs manuale in analiza ML
        cmd = Command(
            device_id=device.id,        # ID-ul dispozitivului tinta
            user_id=current_user.id,    # ID-ul utilizatorului care a executat scena
            action=act.action,          # tipul actiunii executate
            value=act.value,            # valoarea actiunii executate
            source="scene",             # sursa: 'scene' (nu 'app' sau 'routine')
        )
        db.add(cmd)  # adaugam comanda in sesiune (commit la final)

        # --- Pasul 4: Logam executia in ActivityLog ---
        log = ActivityLog(
            user_id=current_user.id,        # utilizatorul care a declansat executia
            action="scene.execute",         # tipul actiunii din jurnal
            entity_type="scene",            # tipul entitatii afectate
            entity_id=scene_id,             # ID-ul scenei executate
            # Detalii JSON cu actiunea, dispozitivul si scena (pentru audit)
            details=f'{{"action": "{act.action}", "device": "{device.name}", "scene": "{scene.name}"}}',
        )
        db.add(log)  # adaugam log-ul in sesiune

    # --- Pasul 5: Notificam utilizatorul despre executia scenei ---
    # Notificarea include numele scenei si numarul de actiuni executate
    notify_scene_executed(db, current_user.id, scene.name, len(actions))

    # Comitem toate comenzile, log-urile si notificarea intr-o singura tranzactie
    db.commit()

    # Returnam confirmarea cu numele scenei si numarul de actiuni executate
    return {"message": f"Scena '{scene.name}' executata", "actions_count": len(actions)}


@router.put("/{scene_id}", response_model=SceneResponse)
def update_scene(
    scene_id: int,                                           # ID-ul scenei de actualizat
    date: SceneUpdate,                                       # campurile de actualizat (partial update)
    db: Session = Depends(get_db),                          # sesiunea DB injectata
    current_user: User = Depends(get_current_user),         # userul curent din JWT
):
    """
    Actualizeaza o scena. Suporta actualizare partiala (PATCH-like).

    Daca sunt trimise actiuni noi, le inlocuieste complet pe cele vechi
    (delete-all + insert-new). Aceasta abordare evita logica complexa de merge.

    Valideaza ownership pe noile dispozitive inainte de stergerea actiunilor vechi.

    Parametri JSON optionali:
        name      : noul nume al scenei
        icon      : noua iconita
        is_active : flag activare/dezactivare
        actions   : lista completa noua de actiuni (inlocuieste toate cele existente)
    """
    # Obtinem scena cu verificarea ownership-ului
    scene = _get_owned_scene(scene_id, current_user, db)

    # --- Actualizam campurile simple daca sunt trimise (partial update) ---
    if date.name is not None:
        scene.name = date.name          # actualizam numele scenei

    if date.icon is not None:
        scene.icon = date.icon          # actualizam iconita scenei

    if date.is_active is not None:
        scene.is_active = date.is_active  # activam sau dezactivam scena

    # --- Actualizam actiunile daca sunt trimise (inlocuire completa) ---
    if date.actions is not None:
        # Validam ownership pe noile dispozitive inainte de orice modificare
        for act in date.actions:
            device = db.query(Device).filter(
                Device.id == act.device_id,             # dispozitivul trebuie sa existe
                Device.owner_id == current_user.id,     # si sa apartina userului curent
            ).first()

            # Returnam 404 daca dispozitivul nu e gasit sau nu apartine userului
            if not device:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Dispozitivul {act.device_id} nu a fost gasit",
                )

        # Stergem toate actiunile vechi (list() pentru a evita modificarea in timpul iteratiei)
        for old_action in list(scene.actions):
            db.delete(old_action)  # marcare pentru stergere

        # flush() executa DELETE-urile inainte de INSERT-urile noi
        # Necesar pentru a evita conflicte de cheie primara sau ordering issues
        db.flush()

        # Cream actiunile noi cu datele primite
        for act in date.actions:
            actiune = SceneAction(
                scene_id=scene.id,              # ID-ul scenei parinte
                device_id=act.device_id,        # dispozitivul tinta
                action=act.action,              # tipul actiunii
                value=act.value,                # valoarea actiunii
                exec_order=act.order,           # ordinea de executie
                delay_seconds=act.delay_seconds,# delay in secunde
            )
            db.add(actiune)  # adaugam actiunea noua in sesiune

    # Comitem toate modificarile intr-o singura tranzactie
    db.commit()

    # Reincarcam obiectul pentru a reflecta noile actiuni generate de DB
    db.refresh(scene)

    # Convertim si returnam scena actualizata
    return _scene_to_response(scene)


@router.delete("/{scene_id}")
def delete_scene(
    scene_id: int,                                           # ID-ul scenei de sters
    db: Session = Depends(get_db),                          # sesiunea DB injectata
    current_user: User = Depends(get_current_user),         # userul curent din JWT
):
    """
    Sterge scena si toate actiunile sale (cascade delete).

    Cascade-ul este definit la nivel ORM in Scene.actions (cascade='all, delete-orphan')
    si la nivel DB in SceneAction.scene_id (ondelete='CASCADE').
    """
    # Obtinem scena cu verificarea ownership-ului
    scene = _get_owned_scene(scene_id, current_user, db)

    # Stergem scena — actiunile se sterg automat prin cascade
    db.delete(scene)

    # Confirmam stergerea in DB
    db.commit()

    # Returnam confirmarea stergerii
    return {"message": "Scena a fost stearsa"}
