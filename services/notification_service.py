"""
Serviciu helper pentru crearea notificarilor in-app.
Functiile primesc sesiunea DB si adauga notificarea - caller-ul face commit.
Aceasta separare permite gruparea mai multor notificari intr-un singur commit.
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
    """
    Creeaza o notificare si o adauga in sesiunea DB (fara commit).
    Caller-ul este responsabil pentru apelul db.commit() dupa aceasta functie.

    Args:
        db: sesiunea SQLAlchemy activa
        user_id: ID-ul utilizatorului care primeste notificarea
        title: titlul scurt al notificarii (afisat bold in UI)
        message: continutul detaliat al notificarii
        type: tipul notificarii ('info', 'success', 'warning', 'error')
    """
    # Construieste obiectul ORM Notification cu datele primite
    notificare = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=type,      # Determina culoarea si iconita in aplicatia mobila
    )

    # Adauga in sesiune (nu comite inca - caller-ul decide cand se comite)
    db.add(notificare)
    return notificare


def notify_device_command(
    db: Session,
    user_id: int,
    device_name: str,
    action: str,
    value: str | None,
) -> Notification:
    """
    Creeaza o notificare de succes dupa executarea unei comenzi manuale.
    Afisata utilizatorului ca confirmare ca dispozitivul a primit comanda.
    """
    # Construieste sufixul cu valoarea comenzii (gol daca value este None)
    value_str = f" {value}" if value else ""

    # Apeleaza create_notification cu tipul 'success' (verde in UI)
    return create_notification(
        db,
        user_id,
        title="Comanda trimisa",
        message=f"Comanda trimisa: {action}{value_str} -> {device_name}",
        type="success",
    )


def notify_routine_executed(
    db: Session,
    user_id: int,
    routine_name: str,
) -> Notification:
    """
    Creeaza o notificare informativa cand scheduler-ul executa o rutina activa.
    Permite utilizatorului sa vada ca automatizarea a functionat corect.
    """
    # Tipul 'info' = albastru in UI (informatie, nu actiune necesara)
    return create_notification(
        db,
        user_id,
        title="Rutina executata",
        message=f"Rutina '{routine_name}' a fost executata automat",
        type="info",
    )


def notify_scene_executed(
    db: Session,
    user_id: int,
    scene_name: str,
    actions_count: int,
) -> Notification:
    """
    Creeaza o notificare de succes dupa activarea unei scene.
    Include numarul de actiuni executate pentru transparenta.
    """
    # Tipul 'success' = verde in UI (operatie finalizata cu succes)
    return create_notification(
        db,
        user_id,
        title="Scena executata",
        # Numarul de actiuni ajuta utilizatorul sa confirme ca toate dispozitivele au raspuns
        message=f"Scena '{scene_name}' executata ({actions_count} actiuni)",
        type="success",
    )


def notify_ml_routines_detected(
    db: Session,
    user_id: int,
    count: int,
) -> Notification:
    """
    Creeaza o notificare informativa cand algoritmul ML detecteaza rutine noi.
    Invita utilizatorul sa revizuiasca si sa activeze rutinele sugerate.
    """
    # Tipul 'info' = albastru; utilizatorul nu trebuie sa actioneze urgent
    return create_notification(
        db,
        user_id,
        title="Rutine detectate de ML",
        # Mesajul include count-ul pentru a arata valoarea algoritmului
        message=f"ML a detectat {count} rutine noi! Verifica in sectiunea Rutine.",
        type="info",
    )
