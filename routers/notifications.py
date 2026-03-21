"""
Router pentru gestionarea notificarilor utilizatorilor in aplicatia Smart Home.

Expune urmatoarele endpoint-uri:
  - GET    /notifications/           : lista notificari (toate sau doar necitite)
  - GET    /notifications/count      : numarul de notificari necitite (pentru badge)
  - PUT    /notifications/{id}/read  : marcheaza o notificare ca citita
  - PUT    /notifications/read-all   : marcheaza toate notificarile ca citite
  - DELETE /notifications/{id}       : sterge o notificare

Toate operatiile sunt filtrate pe utilizatorul autentificat (current_user.id),
garantand ca un utilizator nu poate accesa sau modifica notificarile altui utilizator.
"""

# List - tip generic pentru adnotari de tip returnat (lista de obiecte)
from typing import List

# APIRouter  - clasa FastAPI pentru gruparea endpoint-urilor intr-un modul
# Depends    - mecanism de dependency injection FastAPI
# HTTPException - exceptie HTTP cu cod de status si mesaj
# status     - constante HTTP (404, 200 etc.)
from fastapi import APIRouter, Depends, HTTPException, status

# Session - tipul sesiunii de baza de date SQLAlchemy
from sqlalchemy.orm import Session

# Importam modelele ORM si functia de factory a sesiunii DB
from database.db import Notification, User, get_db

# Schema Pydantic pentru serializarea raspunsurilor cu notificari
from models.schemas import NotificationResponse

# Dependency FastAPI care extrage si valideaza utilizatorul din JWT
from services.auth_service import get_current_user

# Cream router-ul cu prefix si tag pentru documentatia Swagger
# prefix="/notifications" -> toate rutele vor fi /notifications/...
# tags=["Notificari"]     -> grupare vizuala in Swagger UI
router = APIRouter(prefix="/notifications", tags=["Notificari"])


def _get_owned_notification(notif_id: int, current_user: User, db: Session) -> Notification:
    """
    Functie helper interna: cauta o notificare dupa ID si verifica proprietatea.

    Returneaza obiectul Notification daca apartine utilizatorului curent.
    Arunca HTTPException 404 daca notificarea nu exista sau apartine altui utilizator.
    Acest comportament (404 in loc de 403) evita dezvaluirea existentei resursei.

    Parametri:
      notif_id     : ID-ul notificarii cautate (integer din URL path)
      current_user : utilizatorul autentificat (extras din JWT)
      db           : sesiunea activa de baza de date SQLAlchemy

    Returneaza:
      Obiectul Notification gasit si validat

    Arunca:
      HTTPException(404) daca notificarea nu exista sau nu apartine utilizatorului
    """
    # Cautam notificarea cu id-ul dat SI care apartine utilizatorului curent
    # Combinand ambele filtre intr-o singura interogare evitam doua query-uri
    notif = db.query(Notification).filter(
        Notification.id == notif_id,                   # filtram dupa ID-ul notificarii
        Notification.user_id == current_user.id,       # validam ca apartine userului curent
    ).first()  # returnam primul rezultat (sau None daca nu exista)

    # Daca notificarea nu a fost gasita (nu exista sau apartine altui user)
    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,     # codul HTTP 404 Not Found
            detail="Notificarea nu a fost gasita",     # mesajul de eroare returnat
        )

    # Notificarea exista si apartine utilizatorului curent -> o returnam
    return notif


@router.get("/", response_model=List[NotificationResponse])
def list_notifications(
    unread_only: bool = False,                          # parametru query: filtreaza doar necitite
    db: Session = Depends(get_db),                      # sesiunea activa de baza de date
    current_user: User = Depends(get_current_user),     # utilizatorul autentificat
):
    """
    Returneaza lista de notificari ale utilizatorului curent.

    Rezultatele sunt ordonate descrescator dupa data crearii (cele mai noi primele).
    Daca unread_only=True, sunt returnate doar notificarile necitite (is_read=False).

    Parametri:
      unread_only  : daca True, filtreaza doar notificarile necitite (default False)
      db           : sesiunea SQLAlchemy injectata de FastAPI
      current_user : utilizatorul extras si validat din token-ul JWT

    Returneaza:
      Lista de obiecte NotificationResponse, ordonate descrescator dupa created_at
    """
    # Construim query-ul de baza filtrat pe utilizatorul curent
    query = db.query(Notification).filter(Notification.user_id == current_user.id)

    # Aplicam filtrul suplimentar pentru necitite daca parametrul este True
    if unread_only:
        # Filtram doar notificarile cu is_read=False (necitite)
        query = query.filter(Notification.is_read == False)  # noqa: E712

    # Ordonam descrescator dupa data crearii si returnam toate rezultatele
    return query.order_by(Notification.created_at.desc()).all()


@router.get("/count")
def unread_count(
    db: Session = Depends(get_db),                      # sesiunea activa de baza de date
    current_user: User = Depends(get_current_user),     # utilizatorul autentificat
):
    """
    Returneaza numarul de notificari necitite ale utilizatorului curent.

    Folosit de interfata pentru afisarea badge-ului cu numarul de notificari noi
    (exemplu: iconita de clopot cu un numar rosu).

    Parametri:
      db           : sesiunea SQLAlchemy injectata de FastAPI
      current_user : utilizatorul extras si validat din token-ul JWT

    Returneaza:
      Dictionar cu cheia "unread_count" si valoarea numerica (integer)
    """
    # Numaram direct in SQL notificarile necitite ale utilizatorului curent
    # .count() executa SELECT COUNT(*) eficient la nivel de baza de date
    count = (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.id,   # doar notificarile proprii
            Notification.is_read == False               # noqa: E712  # doar cele necitite
        )
        .count()  # returneaza un intreg (numarul de randuri care satisfac filtrele)
    )

    # Returnam dictionarul cu numarul de notificari necitite
    return {"unread_count": count}


@router.put("/{notification_id}/read", response_model=NotificationResponse)
def mark_as_read(
    notification_id: int,                               # ID-ul notificarii din URL path
    db: Session = Depends(get_db),                      # sesiunea activa de baza de date
    current_user: User = Depends(get_current_user),     # utilizatorul autentificat
):
    """
    Marcheaza o notificare specifica ca citita (is_read=True).

    Verifica mai intai ca notificarea exista si apartine utilizatorului curent
    (prin helper-ul _get_owned_notification care arunca 404 in caz contrar).

    Parametri:
      notification_id : ID-ul notificarii de marcat ca citita (din URL path)
      db              : sesiunea SQLAlchemy injectata de FastAPI
      current_user    : utilizatorul extras si validat din token-ul JWT

    Returneaza:
      Obiectul NotificationResponse actualizat (cu is_read=True)

    Arunca:
      HTTPException(404) daca notificarea nu exista sau nu apartine utilizatorului
    """
    # Obtinem notificarea si validam proprietatea (arunca 404 daca nu e gasita)
    notif = _get_owned_notification(notification_id, current_user, db)

    # Setam campul is_read la True pentru a marca notificarea ca citita
    notif.is_read = True

    # Salvam modificarea in baza de date
    db.commit()

    # Reincarcam obiectul din DB pentru a reflecta starea actualizata
    db.refresh(notif)

    # Returnam obiectul actualizat (serializat prin schema NotificationResponse)
    return notif


@router.put("/read-all")
def mark_all_as_read(
    db: Session = Depends(get_db),                      # sesiunea activa de baza de date
    current_user: User = Depends(get_current_user),     # utilizatorul autentificat
):
    """
    Marcheaza toate notificarile necitite ale utilizatorului curent ca citite.

    Foloseste un UPDATE in masa (bulk update) la nivel de baza de date,
    mult mai eficient decat a incarca fiecare obiect si a-l modifica individual.

    Parametri:
      db           : sesiunea SQLAlchemy injectata de FastAPI
      current_user : utilizatorul extras si validat din token-ul JWT

    Returneaza:
      Dictionar cu mesaj si numarul de notificari actualizate
    """
    # Executam un UPDATE in masa pe toate notificarile necitite ale utilizatorului
    # .update() returneaza numarul de randuri afectate de operatia UPDATE
    # synchronize_session="fetch" asigura ca obiectele din sesiune sunt actualizate corect
    actualizate = (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.id,   # doar notificarile proprii
            Notification.is_read == False               # noqa: E712  # doar cele necitite
        )
        .update({"is_read": True}, synchronize_session="fetch")  # setam is_read=True pentru toate
    )

    # Salvam toate modificarile intr-o singura tranzactie
    db.commit()

    # Returnam mesajul cu numarul de notificari actualizate
    return {"message": f"{actualizate} notificari marcate ca citite"}


@router.delete("/{notification_id}")
def delete_notification(
    notification_id: int,                               # ID-ul notificarii din URL path
    db: Session = Depends(get_db),                      # sesiunea activa de baza de date
    current_user: User = Depends(get_current_user),     # utilizatorul autentificat
):
    """
    Sterge definitiv o notificare din baza de date.

    Verifica mai intai ca notificarea exista si apartine utilizatorului curent
    (prin helper-ul _get_owned_notification care arunca 404 in caz contrar).

    Parametri:
      notification_id : ID-ul notificarii de sters (din URL path)
      db              : sesiunea SQLAlchemy injectata de FastAPI
      current_user    : utilizatorul extras si validat din token-ul JWT

    Returneaza:
      Dictionar cu mesaj de confirmare a stergerii

    Arunca:
      HTTPException(404) daca notificarea nu exista sau nu apartine utilizatorului
    """
    # Obtinem notificarea si validam proprietatea (arunca 404 daca nu e gasita)
    notif = _get_owned_notification(notification_id, current_user, db)

    # Stergem obiectul din sesiunea SQLAlchemy
    db.delete(notif)

    # Salvam stergerea in baza de date (commit finalizeaza tranzactia)
    db.commit()

    # Returnam mesajul de confirmare
    return {"message": "Notificarea a fost stearsa"}
