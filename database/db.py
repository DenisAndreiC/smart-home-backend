"""
Modul: database/db.py
Responsabilitate: Definirea motorului SQLAlchemy, a sesiunii de baza de date
si a tuturor modelelor ORM folosite in aplicatia Smart Home.

Fiecare clasa mapeaza un tabel din baza de date SQLite.
Relatiile dintre modele sunt definite prin SQLAlchemy ORM relationships.
Tabelele sunt create automat la pornirea aplicatiei prin Base.metadata.create_all().
"""

# Importuri pentru lucrul cu date si ore in format UTC
from datetime import datetime, timezone

# Generator folosit ca tip de return pentru dependency-ul FastAPI get_db()
from typing import Generator

# Tipuri de coloane SQLAlchemy folosite in definitiile modelelor
from sqlalchemy import (
    Boolean,    # coloana de tip boolean (True/False)
    DateTime,   # coloana de tip data+ora
    Float,      # coloana de tip numar cu virgula mobila
    ForeignKey, # constrangere de cheie straina catre alt tabel
    Integer,    # coloana de tip intreg
    String,     # coloana de tip sir de caractere cu lungime maxima
    Text,       # coloana de tip text lung fara limita de lungime
    create_engine,  # functie pentru crearea motorului de conexiune la DB
)

# Utilitare ORM pentru definirea claselor model si a relatiilor
from sqlalchemy.orm import (
    DeclarativeBase,  # clasa de baza din care mostenesc toate modelele
    Mapped,           # adnotare de tip pentru campurile mapate
    mapped_column,    # functie pentru definirea coloanelor cu adnotari de tip
    relationship,     # functie pentru definirea relatiilor intre modele
    sessionmaker,     # fabrica de sesiuni SQLAlchemy
)

# Setarile globale ale aplicatiei (URL baza de date, chei secrete etc.)
from config import settings

# ---------------------------------------------------------------------------
# Motor si sesiune SQLAlchemy
# ---------------------------------------------------------------------------

# Motorul SQLAlchemy — obiectul central care gestioneaza conexiunile la baza de date.
# settings.database_url contine URL-ul complet al bazei SQLite (ex: "sqlite:///./smart_home.db").
# check_same_thread=False este necesar pentru SQLite deoarece FastAPI foloseste
# mai multe fire de executie (threads) si SQLite implicit permite acces doar din
# firul care a creat conexiunea.
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)

# Fabrica de sesiuni — fiecare apel la SessionLocal() creeaza o noua sesiune de DB.
# autocommit=False: tranzactiile nu se confirma automat, trebuie apelat explicit commit().
# autoflush=False: modificarile nu se trimit automat la DB inainte de fiecare query.
# bind=engine: leaga fabrica de motorul creat mai sus.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# Clasa de baza pentru toate modelele ORM
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """
    Clasa de baza din care mostenesc toate modelele ORM ale aplicatiei.
    SQLAlchemy foloseste aceasta clasa pentru a inregistra si gestiona
    toate tabelele definite in proiect.
    Nu contine campuri proprii — serveste doar ca punct comun de mostenire.
    """
    pass


# ---------------------------------------------------------------------------
# Modele ORM — fiecare clasa reprezinta un tabel in baza de date
# ---------------------------------------------------------------------------


class User(Base):
    """
    Modelul utilizatorului aplicatiei Smart Home.
    Reprezinta tabelul 'users' din baza de date.
    Un utilizator detine camere, dispozitive, comenzi, rutine, scene,
    notificari, jurnale de activitate si preferinte personalizate.
    """

    # Numele tabelului in baza de date SQLite
    __tablename__ = "users"

    # Cheia primara a utilizatorului — numar intreg autoincrementat unic
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Adresa de email a utilizatorului — unica in sistem, folosita la autentificare
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Numele de utilizator (username) — unic in sistem, afisat in interfata
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    # Parola criptata (hash bcrypt) — nu se stocheaza niciodata parola in clar
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Timestamp-ul crearii contului — setat automat la momentul inregistrarii (UTC)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Numele de afisare optional (poate diferi de username)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Calea catre avatarul utilizatorului (relativa la /static/avatars/)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relatie one-to-many catre Device: un utilizator poate detine mai multe dispozitive.
    # back_populates="owner" leaga relatia cu campul 'owner' din clasa Device.
    # Fara cascade — stergerea utilizatorului NU sterge automat dispozitivele sale.
    devices: Mapped[list["Device"]] = relationship("Device", back_populates="owner")

    # Relatie one-to-many catre Command: istoricul tuturor comenzilor trimise de utilizator.
    # back_populates="user" leaga relatia cu campul 'user' din clasa Command.
    # Fara cascade — comenzile raman in baza de date chiar daca utilizatorul este sters.
    commands: Mapped[list["Command"]] = relationship("Command", back_populates="user")

    # Relatie one-to-many catre Routine: rutinele automate create sau sugerate pentru utilizator.
    # back_populates="user" leaga relatia cu campul 'user' din clasa Routine.
    # Fara cascade — rutinele nu se sterg automat la stergerea utilizatorului.
    routines: Mapped[list["Routine"]] = relationship("Routine", back_populates="user")

    # Relatie one-to-many catre Room cu cascade complet.
    # Daca utilizatorul este sters, toate camerele sale sunt sterse automat (delete-orphan).
    # back_populates="owner" leaga relatia cu campul 'owner' din clasa Room.
    rooms: Mapped[list["Room"]] = relationship("Room", back_populates="owner", cascade="all, delete-orphan")

    # Relatie one-to-many catre Scene cu cascade complet.
    # Daca utilizatorul este sters, toate scenele sale sunt sterse automat (delete-orphan).
    # back_populates="owner" leaga relatia cu campul 'owner' din clasa Scene.
    scenes: Mapped[list["Scene"]] = relationship("Scene", back_populates="owner", cascade="all, delete-orphan")

    # Relatie one-to-many catre Notification cu cascade complet.
    # Notificarile se sterg automat odata cu utilizatorul (delete-orphan).
    # back_populates="user" leaga relatia cu campul 'user' din clasa Notification.
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )

    # Relatie one-to-many catre ActivityLog fara cascade.
    # Jurnalele de activitate raman in baza de date chiar daca utilizatorul este sters
    # (user_id devine NULL — vezi campul nullable din ActivityLog).
    # back_populates="user" leaga relatia cu campul 'user' din clasa ActivityLog.
    activity_logs: Mapped[list["ActivityLog"]] = relationship("ActivityLog", back_populates="user")

    # Relatie one-to-one catre UserPreferences cu cascade complet.
    # uselist=False specifica faptul ca relatia este one-to-one, nu one-to-many.
    # Preferintele se sterg automat odata cu utilizatorul (delete-orphan).
    # back_populates="user" leaga relatia cu campul 'user' din clasa UserPreferences.
    preferences: Mapped["UserPreferences | None"] = relationship(
        "UserPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class Room(Base):
    """
    Camera fizica din locuinta — entitate optionala pentru organizarea dispozitivelor.
    Reprezinta tabelul 'rooms' din baza de date.
    Dispozitivele pot fi asociate unei camere prin campul room_id din tabelul devices.
    Fiecare camera apartine unui singur utilizator (owner).
    """

    # Numele tabelului in baza de date SQLite
    __tablename__ = "rooms"

    # Cheia primara a camerei — numar intreg autoincrementat unic
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Numele camerei afisat in interfata (ex: "Living", "Dormitor", "Bucatarie")
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Iconita asociata camerei in aplicatia frontend (ex: "sofa", "bed", "utensils").
    # Campul este optional (nullable) — o camera poate exista fara iconita definita.
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Cheia straina catre utilizatorul proprietar al camerei.
    # Valoarea nu poate fi NULL — fiecare camera trebuie sa apartina unui utilizator.
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    # Timestamp-ul crearii camerei — setat automat la momentul adaugarii (UTC)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relatie many-to-one catre User: fiecare camera are un singur proprietar.
    # back_populates="rooms" leaga relatia cu campul 'rooms' din clasa User.
    owner: Mapped["User"] = relationship("User", back_populates="rooms")

    # Relatie one-to-many catre Device: o camera poate contine mai multe dispozitive.
    # back_populates="room_ref" leaga relatia cu campul 'room_ref' din clasa Device.
    # Fara cascade — dispozitivele nu se sterg automat la stergerea camerei.
    devices: Mapped[list["Device"]] = relationship("Device", back_populates="room_ref")


class Device(Base):
    """
    Dispozitivul fizic gestionat de sistemul Smart Home.
    Reprezinta tabelul 'devices' din baza de date.
    Un dispozitiv poate fi controlat prin MQTT, IR sau Wake-on-LAN.
    Comenzile trimise catre dispozitiv sunt inregistrate in tabelul commands.
    """

    # Numele tabelului in baza de date SQLite
    __tablename__ = "devices"

    # Cheia primara a dispozitivului — numar intreg autoincrementat unic
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Numele dispozitivului afisat in interfata (ex: "Becul din living", "TV Samsung")
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Tipul dispozitivului (ex: "light", "tv", "ac", "plug", "sensor").
    # Folosit pentru a determina icoanele si actiunile disponibile in frontend.
    device_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Camp legacy — numele camerei ca sir de caractere simplu.
    # Pastrat pentru compatibilitate cu versiunile anterioare ale API-ului.
    # Noile inregistrari ar trebui sa foloseasca room_id in locul acestui camp.
    room: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Camp nou — cheia straina catre tabelul rooms pentru asocierea structurata.
    # Optional (nullable) — un dispozitiv poate exista fara o camera asociata.
    room_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("rooms.id"), nullable=True)

    # Topic-ul MQTT pe care dispozitivul asculta si trimite statusuri.
    # Format asteptat: "home/<camera>/<dispozitiv>/status" sau similar.
    mqtt_topic: Mapped[str] = mapped_column(String(255), nullable=False)

    # Indicatorul de conectivitate — True daca dispozitivul raspunde pe MQTT, False altfel.
    # Actualizat de mqtt_service la primirea mesajelor de status.
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)

    # Ultimul status cunoscut al dispozitivului (ex: "on", "off", "22", "75%").
    # Actualizat de mqtt_service la fiecare mesaj primit pe topic-ul dispozitivului.
    last_status: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Adresa MAC a dispozitivului in format "AA:BB:CC:DD:EE:FF" (17 caractere).
    # Folosita de wol_service pentru a trimite pachete Wake-on-LAN.
    # Optional (nullable) — nu toate dispozitivele suporta WoL.
    mac_address: Mapped[str | None] = mapped_column(String(17), nullable=True)

    # Codurile IR ale dispozitivului stocate ca JSON serialized (Text lung).
    # Folosite pentru controlul prin infrarosu al dispozitivelor (TV, AC etc.).
    # Optional (nullable) — nu toate dispozitivele suporta control IR.
    ir_codes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cheia straina catre utilizatorul proprietar al dispozitivului.
    # Valoarea nu poate fi NULL — fiecare dispozitiv trebuie sa apartina unui utilizator.
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    # Timestamp-ul adaugarii dispozitivului in sistem — setat automat la creare (UTC)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relatie many-to-one catre User: fiecare dispozitiv are un singur proprietar.
    # back_populates="devices" leaga relatia cu campul 'devices' din clasa User.
    owner: Mapped["User"] = relationship("User", back_populates="devices")

    # Relatie one-to-many catre Command cu cascade complet.
    # La stergerea dispozitivului, toate comenzile asociate sunt sterse automat (delete-orphan).
    # back_populates="device" leaga relatia cu campul 'device' din clasa Command.
    commands: Mapped[list["Command"]] = relationship(
        "Command", back_populates="device", cascade="all, delete-orphan"
    )

    # Relatie many-to-one catre Room: un dispozitiv poate fi asociat unei singure camere.
    # Relatia este optionala (Room | None) deoarece room_id poate fi NULL.
    # back_populates="devices" leaga relatia cu campul 'devices' din clasa Room.
    room_ref: Mapped["Room | None"] = relationship("Room", back_populates="devices")

    # Relatie one-to-many catre SceneAction: un dispozitiv poate aparea in actiunile mai multor scene.
    # Fara cascade — actiunile din scene nu se sterg automat la stergerea dispozitivului.
    # back_populates="device" leaga relatia cu campul 'device' din clasa SceneAction.
    scene_actions: Mapped[list["SceneAction"]] = relationship("SceneAction", back_populates="device")


class Scene(Base):
    """
    Scena — o grupare numita de actiuni executate simultan sau cu intarzieri definite.
    Reprezinta tabelul 'scenes' din baza de date.
    Exemple de scene: 'Mod Film' (dimmeaza lumina + porneste TV-ul),
    'Buna dimineata' (porneste cafeiera + ridica storele).
    Fiecare scena contine una sau mai multe actiuni (SceneAction).
    """

    # Numele tabelului in baza de date SQLite
    __tablename__ = "scenes"

    # Cheia primara a scenei — numar intreg autoincrementat unic
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Numele scenei afisat in interfata (ex: "Mod Film", "Buna Dimineata", "Plecat de acasa")
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Iconita asociata scenei in aplicatia frontend (ex: "movie", "sun", "home").
    # Optional (nullable) — o scena poate exista fara iconita definita.
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Cheia straina catre utilizatorul proprietar al scenei.
    # Valoarea nu poate fi NULL — fiecare scena trebuie sa apartina unui utilizator.
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    # Indicatorul de stare — True daca scena este activa si poate fi executata, False daca e dezactivata.
    # O scena dezactivata nu apare in lista de scene disponibile pentru executie.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamp-ul crearii scenei — setat automat la momentul adaugarii (UTC)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relatie many-to-one catre User: fiecare scena are un singur proprietar.
    # back_populates="scenes" leaga relatia cu campul 'scenes' din clasa User.
    owner: Mapped["User"] = relationship("User", back_populates="scenes")

    # Relatie one-to-many catre SceneAction cu cascade complet.
    # La stergerea scenei, toate actiunile componente sunt sterse automat (delete-orphan).
    # Aceasta pastreaza consistenta datelor — nu pot exista actiuni fara scena parinte.
    # back_populates="scene" leaga relatia cu campul 'scene' din clasa SceneAction.
    actions: Mapped[list["SceneAction"]] = relationship(
        "SceneAction", back_populates="scene", cascade="all, delete-orphan"
    )


class SceneAction(Base):
    """
    O actiune individuala dintr-o scena — comanda trimisa unui dispozitiv specific.
    Reprezinta tabelul 'scene_actions' din baza de date.
    O scena este compusa din una sau mai multe SceneAction executate in ordine,
    fiecare putand avea un delay configurabil inainte de executie.
    """

    # Numele tabelului in baza de date SQLite
    __tablename__ = "scene_actions"

    # Cheia primara a actiunii — numar intreg autoincrementat unic
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Cheia straina catre scena parinte cu stergere in cascada la nivel de baza de date.
    # ondelete="CASCADE" asigura ca actiunile sunt sterse de DB direct, nu doar prin ORM.
    # Valoarea nu poate fi NULL — fiecare actiune trebuie sa apartina unei scene.
    scene_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False
    )

    # Cheia straina catre dispozitivul tinta al acestei actiuni.
    # Valoarea nu poate fi NULL — fiecare actiune vizeaza un dispozitiv specific.
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id"), nullable=False)

    # Actiunea de executat pe dispozitiv (ex: "turn_on", "turn_off", "set_temperature", "set_volume")
    action: Mapped[str] = mapped_column(String(100), nullable=False)

    # Valoarea parametrului actiunii (ex: "22" pentru temperatura, "75" pentru volum).
    # Optional (nullable) — unele actiuni nu necesita un parametru (ex: "turn_on").
    value: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Ordinea de executie a acestei actiuni in cadrul scenei.
    # Actiunile sunt sortate dupa exec_order crescator inainte de executie.
    # Valoarea implicita 0 plaseaza actiunea la inceputul scenei.
    exec_order: Mapped[int] = mapped_column(Integer, default=0)

    # Intarzierea in secunde inainte de executia acestei actiuni.
    # Permite crearea de secvente temporale in cadrul scenei (ex: aprinde lumina dupa 5 secunde).
    # Valoarea implicita 0 inseamna executie imediata (fara intarziere).
    delay_seconds: Mapped[int] = mapped_column(Integer, default=0)

    # Relatie many-to-one catre Scene: fiecare actiune apartine unei singure scene.
    # back_populates="actions" leaga relatia cu campul 'actions' din clasa Scene.
    scene: Mapped["Scene"] = relationship("Scene", back_populates="actions")

    # Relatie many-to-one catre Device: fiecare actiune vizeaza un singur dispozitiv.
    # back_populates="scene_actions" leaga relatia cu campul 'scene_actions' din clasa Device.
    device: Mapped["Device"] = relationship("Device", back_populates="scene_actions")


class Command(Base):
    """
    Tabel CRITIC pentru algoritmul ML de detectare a rutinelor.
    Reprezinta tabelul 'commands' din baza de date.
    Fiecare comanda trimisa de utilizator (manual din aplicatie) sau generata
    automat de o rutina sau scena este salvata aici cu timestamp precis.
    Algoritmul DBSCAN din ml_service analizeaza acest istoric pentru
    a detecta tipare de comportament si a sugera rutine automate.
    """

    # Numele tabelului in baza de date SQLite
    __tablename__ = "commands"

    # Cheia primara a comenzii — numar intreg autoincrementat unic
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Cheia straina catre dispozitivul caruia i-a fost trimisa comanda.
    # Valoarea nu poate fi NULL — fiecare comanda vizeaza un dispozitiv specific.
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id"), nullable=False)

    # Cheia straina catre utilizatorul care a trimis comanda.
    # Valoarea nu poate fi NULL — fiecare comanda este asociata unui utilizator.
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    # Actiunea executata (ex: "turn_on", "turn_off", "set_temperature", "set_channel")
    action: Mapped[str] = mapped_column(String(100), nullable=False)

    # Valoarea parametrului comenzii (ex: "22" pentru temperatura, "75" pentru volum).
    # Optional (nullable) — unele actiuni nu necesita un parametru suplimentar.
    value: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Sursa comenzii — indica de unde a provenit comanda:
    # "app" = trimisa manual de utilizator din aplicatie,
    # "routine" = generata automat de o rutina programata,
    # "scene" = generata automat la activarea unei scene,
    # "ml" = generata de algoritmul ML.
    source: Mapped[str] = mapped_column(String(50), default="app")

    # Timestamp-ul exact al trimiterii comenzii (UTC) — esential pentru analiza ML.
    # Algoritmul ML foloseste ora si ziua saptamanii din acest timestamp
    # pentru a identifica tipare repetitive de comportament.
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relatie many-to-one catre Device: fiecare comanda vizeaza un singur dispozitiv.
    # back_populates="commands" leaga relatia cu campul 'commands' din clasa Device.
    device: Mapped["Device"] = relationship("Device", back_populates="commands")

    # Relatie many-to-one catre User: fiecare comanda apartine unui singur utilizator.
    # back_populates="commands" leaga relatia cu campul 'commands' din clasa User.
    user: Mapped["User"] = relationship("User", back_populates="commands")


class Routine(Base):
    """
    Rutina automata — o actiune programata sa se execute la o ora fixa in anumite zile.
    Reprezinta tabelul 'routines' din baza de date.
    Rutinele pot fi create manual de utilizator sau sugerate de algoritmul ML
    pe baza tiparelor detectate in istoricul comenzilor (tabelul commands).
    APScheduler verifica periodic rutinele active si le executa conform programului.
    """

    # Numele tabelului in baza de date SQLite
    __tablename__ = "routines"

    # Cheia primara a rutinei — numar intreg autoincrementat unic
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Cheia straina catre utilizatorul caruia ii apartine rutina.
    # Valoarea nu poate fi NULL — fiecare rutina apartine unui utilizator.
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    # Numele descriptiv al rutinei (ex: "Stinge lumina seara", "Porneste cafeiera dimineata")
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Cheia straina catre dispozitivul pe care rutina il controleaza.
    # Valoarea nu poate fi NULL — fiecare rutina actioneaza pe un dispozitiv specific.
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id"), nullable=False)

    # Actiunea de executat la declansarea rutinei (ex: "turn_on", "turn_off", "set_temperature")
    action: Mapped[str] = mapped_column(String(100), nullable=False)

    # Valoarea parametrului actiunii (ex: "22" pentru temperatura, "0" pentru stingere).
    # Optional (nullable) — unele actiuni nu necesita un parametru suplimentar.
    value: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Ora de declansare a rutinei in format "HH:MM" (ex: "07:30", "22:00").
    # APScheduler parseaza acest string pentru a programa executia.
    trigger_time: Mapped[str] = mapped_column(String(5), nullable=False)

    # Zilele saptamanii in care se executa rutina, stocate ca sir de cifre separate prin virgula.
    # Conventie: "0,1,2,3,4" = luni-vineri, "5,6" = sambata-duminica, "0,1,2,3,4,5,6" = zilnic.
    days_of_week: Mapped[str] = mapped_column(String(20), nullable=False)

    # Indicatorul de stare — True daca rutina este activa si se executa, False daca e dezactivata.
    # Rutinele sugerate de ML sunt inactive (False) pana cand utilizatorul le aproba explicit.
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    # Indica daca rutina a fost sugerata automat de algoritmul ML (True) sau creata manual (False).
    # Rutinele ML sunt marcate vizual diferit in interfata si necesita aprobare utilizator.
    is_ml_suggested: Mapped[bool] = mapped_column(Boolean, default=False)

    # Nivelul de incredere al algoritmului ML in aceasta suggestie (valoare intre 0.0 si 1.0).
    # Relevant doar pentru rutinele cu is_ml_suggested=True, NULL pentru cele create manual.
    # Valori mai mari indica tipare mai clare si repetitive in istoricul comenzilor.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Timestamp-ul crearii rutinei — setat automat la momentul adaugarii (UTC)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relatie many-to-one catre User: fiecare rutina apartine unui singur utilizator.
    # back_populates="routines" leaga relatia cu campul 'routines' din clasa User.
    user: Mapped["User"] = relationship("User", back_populates="routines")

    # Relatie many-to-one catre Device: fiecare rutina actioneaza pe un singur dispozitiv.
    # Fara back_populates — accesul invers (de la Device la Routine) nu este necesar in aplicatie.
    device: Mapped["Device"] = relationship("Device")


class Notification(Base):
    """
    Notificare pentru utilizator generata de diverse actiuni din sistem.
    Reprezinta tabelul 'notifications' din baza de date.
    Notificarile pot fi generate de: comenzi executate, rutine activate,
    sugestii ML, activari de scene sau erori din sistem.
    """

    # Numele tabelului in baza de date SQLite
    __tablename__ = "notifications"

    # Cheia primara a notificarii — numar intreg autoincrementat unic
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Cheia straina catre utilizatorul destinatar al notificarii.
    # Valoarea nu poate fi NULL — fiecare notificare are un destinatar.
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    # Titlul scurt al notificarii (ex: "Rutina activata", "Dispozitiv offline")
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # Continutul complet al notificarii cu detalii despre eveniment
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Tipul notificarii — determina culoarea si iconita in interfata:
    # "info" = informatie generala (albastru),
    # "warning" = atentionare (portocaliu),
    # "error" = eroare critica (rosu),
    # "success" = actiune reusita (verde).
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="info")

    # Indicatorul de citire — False daca notificarea nu a fost vazuta de utilizator, True dupa citire.
    # Folosit pentru a afisa contorul de notificari necitite in interfata.
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamp-ul crearii notificarii — setat automat la momentul generarii (UTC)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relatie many-to-one catre User: fiecare notificare apartine unui singur utilizator.
    # back_populates="notifications" leaga relatia cu campul 'notifications' din clasa User.
    user: Mapped["User"] = relationship("User", back_populates="notifications")


class ActivityLog(Base):
    """
    Jurnal de activitate — inregistreaza toate actiunile importante din sistem.
    Reprezinta tabelul 'activity_logs' din baza de date.
    Spre deosebire de tabelul commands, activity_logs include si actiunile
    administrative si sistemice (autentificari, modificari de setari, erori etc.).
    user_id este optional pentru a permite inregistrarea actiunilor de sistem
    care nu sunt asociate unui utilizator specific.
    """

    # Numele tabelului in baza de date SQLite
    __tablename__ = "activity_logs"

    # Cheia primara a inregistrarii din jurnal — numar intreg autoincrementat unic
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Cheia straina catre utilizatorul care a efectuat actiunea.
    # NULLABLE — valoarea poate fi NULL pentru actiunile generate de sistem fara initiator uman
    # (ex: verificari automate, actiuni APScheduler, mesaje MQTT procesate in background).
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    # Codul actiunii efectuate (ex: "login", "device_command", "routine_triggered", "scene_activated")
    action: Mapped[str] = mapped_column(String(100), nullable=False)

    # Tipul entitatii asupra careia s-a efectuat actiunea (ex: "device", "routine", "scene", "user").
    # Optional (nullable) — unele actiuni nu vizeaza o entitate specifica.
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ID-ul entitatii vizate — corespunde id-ului din tabelul indicat de entity_type.
    # Optional (nullable) — poate fi NULL daca actiunea nu vizeaza o entitate specifica.
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Detalii suplimentare despre actiune in format text liber sau JSON serialized.
    # Optional (nullable) — folosit pentru informatii de debug sau audit detaliat.
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Adresa IP a clientului care a initiat actiunea (suporta IPv4 si IPv6, max 45 caractere).
    # Optional (nullable) — poate lipsi pentru actiunile generate intern de sistem.
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # Timestamp-ul exact al actiunii — setat automat la momentul inregistrarii (UTC)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relatie many-to-one catre User: fiecare inregistrare poate apartine unui utilizator sau poate fi NULL.
    # Tipul "User | None" reflecta faptul ca user_id este nullable.
    # back_populates="activity_logs" leaga relatia cu campul 'activity_logs' din clasa User.
    user: Mapped["User | None"] = relationship("User", back_populates="activity_logs")


class UserPreferences(Base):
    """
    Preferintele personalizate ale unui utilizator — relatie one-to-one cu User.
    Reprezinta tabelul 'user_preferences' din baza de date.
    Stocheaza setarile de interfata si comportament specifice fiecarui utilizator:
    fus orar, limba, tema vizuala, preferinte notificari si detectie ML.
    """

    # Numele tabelului in baza de date SQLite
    __tablename__ = "user_preferences"

    # Cheia primara a preferintelor — numar intreg autoincrementat unic
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Cheia straina catre utilizatorul proprietar al acestor preferinte.
    # unique=True garanteaza relatia one-to-one — fiecare utilizator are exact un set de preferinte.
    # Valoarea nu poate fi NULL — preferintele trebuie asociate unui utilizator.
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    # Fusul orar al utilizatorului in format IANA (ex: "Europe/Bucharest", "UTC", "America/New_York").
    # Folosit pentru afisarea orelor in interfata in fusul orar local al utilizatorului.
    # Coloana din DB se numeste "timezone" (alias prin primul argument al mapped_column).
    # Atributul Python se numeste "tz" pentru a evita conflictul cu cuvantul rezervat din alte contexte.
    tz: Mapped[str] = mapped_column("timezone", String(50), default="Europe/Bucharest")

    # Limba preferata a interfetei in format ISO 639-1 (ex: "ro" = romana, "en" = engleza).
    # Folosita de frontend pentru localizarea textelor si mesajelor.
    language: Mapped[str] = mapped_column(String(10), default="ro")

    # Tema vizuala preferata a interfetei (ex: "dark" = intuneric, "light" = deschis).
    # Folosita de frontend pentru aplicarea schemei de culori corecte.
    theme: Mapped[str] = mapped_column(String(20), default="dark")

    # Indica daca utilizatorul doreste sa primeasca notificari din sistem.
    # True = notificarile sunt activate, False = notificarile sunt dezactivate global.
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Indica daca algoritmul ML poate analiza istoricul comenzilor utilizatorului
    # pentru a detecta rutine automate si a face sugestii.
    # True = detectia automata este activata, False = algoritmul ML nu analizeaza datele acestui utilizator.
    auto_detect_routines: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relatie many-to-one catre User: preferintele apartin unui singur utilizator.
    # back_populates="preferences" leaga relatia cu campul 'preferences' din clasa User.
    user: Mapped["User"] = relationship("User", back_populates="preferences")


# ---------------------------------------------------------------------------
# Dependency FastAPI — sesiune de baza de date per request HTTP
# ---------------------------------------------------------------------------


def get_db() -> Generator:
    """
    Generator FastAPI dependency pentru gestionarea sesiunii de baza de date.

    Aceasta functie este injectata in routere prin mecanismul Depends() al FastAPI.
    La fiecare request HTTP care o foloseste, se creeaza o sesiune noua de DB,
    se executa logica endpoint-ului, iar la final sesiunea este inchisa automat —
    indiferent daca requestul s-a terminat cu succes sau cu o exceptie.

    Utilizare in routere:
        @router.get("/example")
        def example_endpoint(db: Session = Depends(get_db)):
            ...

    Flux de executie:
        1. SessionLocal() — se creeaza o sesiune noua (conexiune la SQLite)
        2. yield db — se pune sesiunea la dispozitia endpoint-ului
        3. finally: db.close() — sesiunea se inchide intotdeauna la final,
           eliberand conexiunea inapoi in pool-ul SQLAlchemy.

    Returns:
        Generator care produce un obiect Session SQLAlchemy.
    """
    # Cream o noua sesiune de baza de date folosind fabrica SessionLocal
    db = SessionLocal()
    try:
        # Punem sesiunea la dispozitia endpoint-ului prin yield (pattern generator)
        yield db
    finally:
        # Inchidem sesiunea intotdeauna la final, chiar daca a aparut o exceptie.
        # Acest bloc finally garanteaza ca resursele sunt eliberate corect.
        db.close()


# Creare automata a tuturor tabelelor definite mai sus la pornirea aplicatiei.
# SQLAlchemy compara schema existenta din fisierul SQLite cu modelele definite
# si creeaza tabelele lipsa. Tabelele existente nu sunt modificate sau sterse.
# Aceasta instructiune ruleaza o singura data, la importul modulului database/db.py.
Base.metadata.create_all(bind=engine)
