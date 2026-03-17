"""
schemas.py — Definitiile Pydantic pentru validarea datelor de intrare si iesire.

Fiecare clasa reprezinta un contract de date (schema) folosit intre:
  - clientul HTTP (frontend / Postman) si endpoint-urile FastAPI (schema de INPUT)
  - endpoint-urile FastAPI si clientul HTTP (schema de OUTPUT / Response)

Pydantic valideaza automat tipurile si constrangerile la fiecare request,
ridicand HTTP 422 Unprocessable Entity daca datele nu respecta schema.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

# BaseModel   — clasa de baza Pydantic; toate schemele mostenesc de la ea
# ConfigDict  — obiect de configurare pentru comportamentul modelului Pydantic
# Field       — permite adaugarea de constrangeri suplimentare pe un camp (min_length, pattern etc.)
# field_validator — decorator pentru validatoare personalizate la nivel de camp
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Auth schemas — inregistrare, autentificare, token JWT, profil utilizator
# ---------------------------------------------------------------------------


# Schema folosita la POST /api/auth/register
# Primeste datele brute de la utilizator pentru crearea unui cont nou
class UserRegister(BaseModel):
    # Adresa de email — folosita ca identificator unic in baza de date
    email: str

    # Numele de afisare ales de utilizator
    username: str

    # Parola in text clar — va fi hash-uita de auth_service inainte de stocare
    # Field(min_length=6) impune ca parola sa aiba cel putin 6 caractere
    password: str = Field(min_length=6)


# Schema folosita la POST /api/auth/login
# Contine doar campurile necesare pentru autentificare
class UserLogin(BaseModel):
    # Emailul cu care utilizatorul s-a inregistrat
    email: str

    # Parola in text clar — va fi comparata cu hash-ul din baza de date
    password: str


# Schema returnata dupa un login reusit
# Contine token-ul JWT pe care clientul trebuie sa-l trimita in header-ul Authorization
class Token(BaseModel):
    # Token-ul JWT semnat, cu durata de viata configurata in config.py
    access_token: str

    # Tipul de autentificare — intotdeauna "bearer" pentru JWT
    # Valoarea implicita este setata direct in schema, nu trebuie trimisa de client
    token_type: str = "bearer"


# Schema returnata la GET /api/auth/me sau dupa register
# Expune doar datele publice ale utilizatorului — NU include parola sau hash-ul
class UserResponse(BaseModel):
    # ID-ul numeric generat de baza de date (autoincrement)
    id: int

    # Adresa de email a utilizatorului
    email: str

    # Numele de afisare
    username: str

    # Numele de afisare optional (poate diferi de username)
    display_name: Optional[str] = None

    # URL-ul avatarului utilizatorului
    avatar_url: Optional[str] = None

    # Momentul crearii contului, setat automat de ORM
    created_at: datetime

    # from_attributes=True permite Pydantic sa construiasca schema direct
    # dintr-un obiect SQLAlchemy ORM (adica din randul din baza de date),
    # nu doar dintr-un dict — necesar pentru response_model in FastAPI
    model_config = ConfigDict(from_attributes=True)


# Schema folosita la PUT /api/users/me — actualizare profil
class UserUpdate(BaseModel):
    # Noul username — None inseamna fara modificare
    username: Optional[str] = None

    # Noul display_name — None inseamna fara modificare
    display_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Device schemas — creare, actualizare, raspuns pentru dispozitive
# ---------------------------------------------------------------------------

# Tip literal care restrictioneaza valorile acceptate pentru tipul dispozitivului:
#   ir_rgb  — bec RGB controlat prin infrarosu
#   ir_tv   — televizor controlat prin infrarosu
#   ir_ac   — aer conditionat controlat prin infrarosu
#   relay   — priza / intrerupator controlat prin releu MQTT
#   wol     — calculator trezit prin Wake-on-LAN
DeviceType = Literal["ir_rgb", "ir_tv", "ir_ac", "relay", "wol"]


# Schema folosita la POST /api/devices/
# Contine campurile obligatorii si optionale pentru adaugarea unui dispozitiv nou
class DeviceCreate(BaseModel):
    # Numele afisabil al dispozitivului (ex: "Bec Living")
    name: str

    # Tipul dispozitivului — restrictionat la valorile din DeviceType
    # Pydantic va refuza orice valoare care nu se afla in lista Literal
    device_type: DeviceType

    # Numele camerei ca text liber — camp legacy, preferat room_id
    # Optional deoarece un dispozitiv poate fi nealocat unei camere
    room: Optional[str] = None

    # ID-ul camerei din tabelul rooms — referinta la obiectul Room din baza de date
    # Optional deoarece dispozitivul poate exista fara camera asociata
    room_id: Optional[int] = None

    # Topic-ul MQTT pe care dispozitivul asculta comenzi
    # Exemplu: "home/living/bec1/command"
    mqtt_topic: str

    # Adresa MAC a dispozitivului — necesara doar pentru tipul "wol" (Wake-on-LAN)
    # Formatul asteptat: "AA:BB:CC:DD:EE:FF"
    mac_address: Optional[str] = None

    # Dictonarul cu coduri IR — relevant doar pentru tipurile "ir_rgb", "ir_tv", "ir_ac"
    # Structura: {"on": "0xABCD", "off": "0xEFGH", "red": "0x1234", ...}
    ir_codes: Optional[dict] = None


# Schema folosita la PATCH/PUT /api/devices/{id}
# Toate campurile sunt Optional pentru a permite actualizari partiale (PATCH semantic)
class DeviceUpdate(BaseModel):
    # Noul nume al dispozitivului — None inseamna ca nu se schimba
    name: Optional[str] = None

    # Noul nume de camera (text liber) — None inseamna fara modificare
    room: Optional[str] = None

    # Noul ID de camera — None inseamna fara modificare
    room_id: Optional[int] = None

    # Noul topic MQTT — util daca dispozitivul a fost reconfigurat
    mqtt_topic: Optional[str] = None

    # Starea de conectivitate — actualizata de MQTT service cand dispozitivul
    # publica pe topicul de status
    is_online: Optional[bool] = None

    # Ultimul status raportat de dispozitiv (ex: "on", "off", "25°C")
    last_status: Optional[str] = None

    # Noua adresa MAC — None inseamna fara modificare
    mac_address: Optional[str] = None

    # Noul dictionar de coduri IR serializat — None inseamna fara modificare
    ir_codes: Optional[dict] = None


# Schema returnata in raspunsurile ce contin informatii despre un dispozitiv
# Reflecta structura completa a randului din tabelul devices
class DeviceResponse(BaseModel):
    # ID-ul unic generat de baza de date
    id: int

    # Numele afisabil al dispozitivului
    name: str

    # Tipul dispozitivului stocat ca string simplu (nu mai e Literal in response)
    device_type: str

    # Numele camerei — None daca dispozitivul nu e alocat unei camere
    room: Optional[str] = None

    # ID-ul camerei asociate — None daca nu exista asociere
    room_id: Optional[int] = None

    # Topic-ul MQTT al dispozitivului
    mqtt_topic: str

    # True daca dispozitivul a trimis un mesaj de status in fereastra de timp configurata
    is_online: bool

    # Ultimul payload primit pe topicul de status MQTT
    last_status: Optional[str] = None

    # Adresa MAC — prezenta doar pentru dispozitivele de tip "wol"
    mac_address: Optional[str] = None

    # Codurile IR serializate ca string JSON — prezente doar pentru tipurile IR
    ir_codes: Optional[str] = None

    # ID-ul utilizatorului care detine dispozitivul (owner)
    owner_id: int

    # Momentul in care dispozitivul a fost adaugat in sistem
    created_at: datetime

    # from_attributes=True necesar pentru a converti obiectul ORM Device
    # in aceasta schema Pydantic direct in response_model
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Room schemas — creare, actualizare, raspuns pentru camere
# ---------------------------------------------------------------------------


# Schema folosita la POST /api/rooms/
class RoomCreate(BaseModel):
    # Numele camerei (ex: "Living", "Dormitor", "Bucatarie")
    name: str

    # Iconita asociata camerei — string cu numele iconului din libraria UI
    # Optional deoarece nu toate camerele au o iconita setata
    icon: Optional[str] = None


# Schema folosita la PATCH/PUT /api/rooms/{id}
# Toate campurile sunt Optional pentru actualizari partiale
class RoomUpdate(BaseModel):
    # Noul nume al camerei — None inseamna fara modificare
    name: Optional[str] = None

    # Noua iconita — None inseamna fara modificare
    icon: Optional[str] = None


# Schema returnata in raspunsurile ce contin informatii despre o camera
class RoomResponse(BaseModel):
    # ID-ul unic al camerei generat de baza de date
    id: int

    # Numele camerei
    name: str

    # Iconita asociata — None daca nu a fost setata
    icon: Optional[str] = None

    # Numarul de dispozitive alocate acestei camere
    # Calculat la query time prin COUNT sau proprietate hibrida ORM
    device_count: int

    # from_attributes=True pentru conversia din obiect ORM Room
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Scene schemas — scene compuse din mai multe actiuni pe dispozitive diferite
# ---------------------------------------------------------------------------


# Schema pentru o singura actiune in cadrul unei scene
# O scena contine o lista ordonata de astfel de actiuni
class SceneActionCreate(BaseModel):
    # ID-ul dispozitivului pe care se executa actiunea
    device_id: int

    # Actiunea de executat (ex: "on", "off", "set_color", "set_temperature")
    action: str

    # Valoarea asociata actiunii — relevanta pentru actiuni cu parametru
    # Exemplu: pentru "set_color" -> "255,0,0" (rosu)
    value: Optional[str] = None

    # Ordinea de executie a actiunii in cadrul scenei
    # Implicit 0; actiunile sunt sortate ascendent dupa acest camp
    order: int = 0

    # Intarzierea in secunde fata de actiunea anterioara inainte de executie
    # Implicit 0 inseamna executie imediata dupa actiunea precedenta
    delay_seconds: int = 0


# Schema folosita la POST /api/scenes/
class SceneCreate(BaseModel):
    # Numele scenei (ex: "Film", "Trezire", "Plecare acasa")
    name: str

    # Iconita scenei — string cu numele iconului din libraria UI
    icon: Optional[str] = None

    # Lista de actiuni care alcatuiesc scena — cel putin una este necesara in practica
    actions: List[SceneActionCreate]


# Schema folosita la PATCH/PUT /api/scenes/{id}
# Toate campurile sunt Optional pentru actualizari partiale
class SceneUpdate(BaseModel):
    # Noul nume al scenei — None inseamna fara modificare
    name: Optional[str] = None

    # Noua iconita — None inseamna fara modificare
    icon: Optional[str] = None

    # Activeaza sau dezactiveaza scena — None inseamna fara modificare
    is_active: Optional[bool] = None

    # Lista noua de actiuni — inlocuieste complet lista existenta daca e furnizata
    # None inseamna ca lista de actiuni ramane nemodificata
    actions: Optional[List[SceneActionCreate]] = None


# Schema returnata pentru o actiune din cadrul unei scene
class SceneActionResponse(BaseModel):
    # ID-ul unic al actiunii generat de baza de date
    id: int

    # ID-ul dispozitivului pe care se executa actiunea
    device_id: int

    # Numele dispozitivului — populat prin JOIN SQL la query time,
    # nu vine direct din relatia ORM pentru a evita N+1 queries
    device_name: str

    # Tipul actiunii executate
    action: str

    # Valoarea parametrului actiunii — None daca actiunea nu are parametru
    value: Optional[str] = None

    # Pozitia actiunii in secventa de executie a scenei
    order: int

    # Numarul de secunde de asteptare inaintea executiei acestei actiuni
    delay_seconds: int


# Schema returnata in raspunsurile ce contin informatii despre o scena
class SceneResponse(BaseModel):
    # ID-ul unic al scenei generat de baza de date
    id: int

    # Numele scenei
    name: str

    # Iconita asociata scenei — None daca nu a fost setata
    icon: Optional[str] = None

    # True daca scena poate fi activata; False daca e dezactivata de utilizator
    is_active: bool

    # Lista completa de actiuni in ordinea de executie
    actions: List[SceneActionResponse]

    # Momentul in care scena a fost creata
    created_at: datetime


# ---------------------------------------------------------------------------
# Command schemas — trimiterea si jurnalizarea comenzilor catre dispozitive
# ---------------------------------------------------------------------------


# Schema folosita la POST /api/commands/send
# Reprezinta o comanda trimisa manual de utilizator catre un dispozitiv
class CommandSend(BaseModel):
    # ID-ul dispozitivului destinatar al comenzii
    device_id: int

    # Actiunea de executat pe dispozitiv (ex: "on", "off", "toggle", "set_color")
    action: str

    # Valoarea optionala a comenzii — necesara pentru actiuni cu parametru
    # Exemplu: pentru "set_color" -> "128,0,255" (violet)
    value: Optional[str] = None


# Schema returnata dupa executia sau interogarea unei comenzi
# Reflecta structura randului din tabelul commands_log
class CommandResponse(BaseModel):
    # ID-ul unic al comenzii generat de baza de date
    id: int

    # ID-ul dispozitivului care a primit comanda
    device_id: int

    # Actiunea executata
    action: str

    # Valoarea cu care a fost executata actiunea — None daca nu a avut parametru
    value: Optional[str] = None

    # Sursa comenzii: "manual" (utilizator), "routine" (rutina automata),
    # "scene" (scena), "ml" (sugerat de ML)
    source: str

    # Momentul exact al executiei comenzii
    timestamp: datetime

    # Numele dispozitivului — populat prin JOIN SQL, nu direct din ORM
    device_name: str


# ---------------------------------------------------------------------------
# Routine schemas — rutine automate (manuale si sugerate de ML)
# ---------------------------------------------------------------------------


# Schema folosita la POST /api/routines/
# Contine toate datele necesare pentru definirea unei rutine automate
class RoutineCreate(BaseModel):
    # Numele descriptiv al rutinei (ex: "Aprinde becul dimineata")
    name: str

    # ID-ul dispozitivului pe care rutina va executa actiunea
    device_id: int

    # Actiunea care va fi executata automat la ora si zilele specificate
    action: str

    # Valoarea optionala a actiunii — None pentru actiuni fara parametru
    value: Optional[str] = None

    # Ora de declansare in format HH:MM (24h)
    # Field(pattern=...) impune regex strict: exact doua cifre, doua puncte, doua cifre
    # Exemplu valid: "07:30", "22:00"
    trigger_time: str = Field(pattern=r"^\d{2}:\d{2}$")

    # Zilele saptamanii in care se declanseaza rutina, ca sir de cifre separate prin virgula
    # Conventia: 1=Luni, 2=Marti, ..., 7=Duminica
    # Exemplu: "1,2,3,4,5" = zilele lucratoare; "6,7" = weekend
    days_of_week: str

    # Validator personalizat aplicat campului days_of_week dupa parsarea valorii
    # @classmethod necesar pentru validatorii de camp in Pydantic v2
    @field_validator("days_of_week")
    @classmethod
    def validate_days(cls, v: str) -> str:
        # Imparte sirul primit dupa virgula pentru a obtine zilele individuale
        days = v.split(",")
        for day in days:
            # Verifica ca fiecare token este o cifra si se afla in intervalul [1, 7]
            # day.strip() elimina spatiile accidentale ("1, 2" -> ["1", " 2"])
            if not day.strip().isdigit() or int(day.strip()) not in range(1, 8):
                # Arunca ValueError — Pydantic il converteste automat in HTTP 422
                raise ValueError("Zilele trebuie sa fie numere intre 1 si 7, separate prin virgula")
        # Returneaza valoarea originala validata — Pydantic o va stoca pe camp
        return v


# Schema folosita la PUT /api/routines/{id}/toggle
# Permite activarea sau dezactivarea unei rutine fara a modifica celelalte campuri
class RoutineToggle(BaseModel):
    # Noua stare dorita: True = activa (programatorul o va executa), False = inactiva
    is_active: bool


# Schema returnata in raspunsurile ce contin informatii despre o rutina
class RoutineResponse(BaseModel):
    # ID-ul unic al rutinei generat de baza de date
    id: int

    # ID-ul utilizatorului caruia ii apartine rutina
    user_id: int

    # Numele descriptiv al rutinei
    name: str

    # ID-ul dispozitivului pe care rutina actioneaza
    device_id: int

    # Actiunea executata automat
    action: str

    # Valoarea parametrului actiunii — None daca actiunea nu are parametru
    value: Optional[str] = None

    # Ora de declansare stocata ca string in format "HH:MM"
    trigger_time: str

    # Zilele de declansare stocate ca string "1,2,3" etc.
    days_of_week: str

    # True daca rutina este activa si va fi executata de APScheduler
    is_active: bool

    # True daca rutina a fost generata automat de algoritmul ML (DBSCAN)
    # False daca a fost creata manual de utilizator
    is_ml_suggested: bool

    # Scorul de incredere returnat de ML — prezent doar pentru rutinele ML
    # Valori intre 0.0 si 1.0; cu cat e mai aproape de 1.0, cu atat tiparul e mai clar
    confidence: Optional[float] = None

    # Momentul in care rutina a fost adaugata in sistem
    created_at: datetime

    # from_attributes=True pentru conversia din obiectul ORM Routine
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Wake-on-LAN schemas — trezirea calculatoarelor prin pachet magic
# ---------------------------------------------------------------------------


# Schema folosita la POST /api/commands/wol
# Contine ID-ul dispozitivului de tip "wol" care trebuie trezit
class WolRequest(BaseModel):
    # ID-ul dispozitivului din baza de date — din el se extrage adresa MAC
    device_id: int


# ---------------------------------------------------------------------------
# Notification schemas — notificari generate de sistem catre utilizator
# ---------------------------------------------------------------------------


# Schema returnata la GET /api/notifications/
# Reflecta structura randului din tabelul notifications
class NotificationResponse(BaseModel):
    # ID-ul unic al notificarii
    id: int

    # Titlul scurt al notificarii (ex: "Rutine noi detectate")
    title: str

    # Mesajul detaliat al notificarii
    message: str

    # Tipul notificarii — folosit de frontend pentru culoare / iconita
    # Valori posibile: "info", "warning", "error", "success"
    type: str

    # False daca notificarea nu a fost inca citita de utilizator
    is_read: bool

    # Momentul in care notificarea a fost generata
    created_at: datetime

    # from_attributes=True pentru conversia din obiectul ORM Notification
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# ActivityLog schemas — jurnalul de activitate al utilizatorilor
# ---------------------------------------------------------------------------


# Schema returnata la GET /api/activity/
# Reflecta structura randului din tabelul activity_logs
class ActivityLogResponse(BaseModel):
    # ID-ul unic al inregistrarii din jurnal
    id: int

    # ID-ul utilizatorului care a efectuat actiunea
    # Optional deoarece unele actiuni pot fi generate de sistem (fara user autentificat)
    user_id: Optional[int] = None

    # Descrierea actiunii efectuate (ex: "create_device", "send_command", "login")
    action: str

    # Tipul entitatii afectate (ex: "device", "routine", "scene")
    # None daca actiunea nu se refera la o entitate anume
    entity_type: Optional[str] = None

    # ID-ul entitatii afectate — corelat cu entity_type pentru a identifica obiectul
    # None daca actiunea nu se refera la o entitate concreta
    entity_id: Optional[int] = None

    # Informatii suplimentare despre actiune serializate ca JSON sau text liber
    details: Optional[str] = None

    # Adresa IP a clientului care a generat actiunea — utila pentru audit
    ip_address: Optional[str] = None

    # Momentul exact al actiunii
    created_at: datetime

    # from_attributes=True pentru conversia din obiectul ORM ActivityLog
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# UserPreferences schemas — preferintele personale ale utilizatorului
# ---------------------------------------------------------------------------


# Schema folosita la PATCH /api/preferences/
# Toate campurile sunt Optional pentru actualizari partiale
class UserPreferencesUpdate(BaseModel):
    # Fusul orar al utilizatorului in format IANA (ex: "Europe/Bucharest")
    # Folosit de APScheduler pentru a declanosa rutinele la ora locala corecta
    timezone: Optional[str] = None

    # Codul de limba al interfetei (ex: "ro", "en")
    language: Optional[str] = None

    # Tema vizuala a aplicatiei (ex: "light", "dark", "system")
    theme: Optional[str] = None

    # True daca utilizatorul doreste sa primeasca notificari push/in-app
    notifications_enabled: Optional[bool] = None

    # True daca sistemul ML poate analiza activitatea si sugera rutine automat
    auto_detect_routines: Optional[bool] = None


# Schema returnata la GET /api/preferences/
# Reflecta structura completa a randului din tabelul user_preferences
class UserPreferencesResponse(BaseModel):
    # ID-ul unic al randului de preferinte
    id: int

    # ID-ul utilizatorului caruia ii apartin preferintele (relatia one-to-one)
    user_id: int

    # Fusul orar curent al utilizatorului
    timezone: str

    # Codul de limba selectat
    language: str

    # Tema vizuala selectata
    theme: str

    # True daca notificarile sunt activate
    notifications_enabled: bool

    # True daca detectia automata de rutine prin ML este activata
    auto_detect_routines: bool

    # from_attributes=True pentru conversia din obiectul ORM UserPreferences
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Dashboard schemas — statistici agregate pentru pagina principala
# ---------------------------------------------------------------------------


# Schema returnata la GET /api/dashboard/stats
# Contine toate metricile necesare pentru afisarea dashboard-ului aplicatiei
class DashboardStats(BaseModel):
    # Numarul total de dispozitive inregistrate de utilizatorul curent
    total_devices: int

    # Numarul de comenzi trimise in ziua curenta (de la miezul noptii)
    total_commands_today: int

    # Numarul de rutine care au is_active=True in momentul interogarii
    total_routines_active: int

    # Numarul total de scene definite de utilizator
    total_scenes: int

    # Numele dispozitivului cu cele mai multe comenzi trimise — None daca nu exista date
    most_used_device: Optional[str] = None

    # Ora din zi (0-23) cu cele mai multe comenzi trimise — None daca nu exista date
    peak_hour: Optional[int] = None

    # Comenzi grupate pe zi — ultimele 7 zile
    # Fiecare element: {"date": "2026-03-01", "count": 42}
    # Util pentru graficul de activitate din dashboard
    commands_by_day: List[Dict[str, Any]]

    # Top 5 dispozitive dupa numarul de comenzi primite
    # Fiecare element: {"device_name": "Bec Living", "count": 120}
    # Util pentru graficul cu bara a celor mai folosite dispozitive
    commands_by_device: List[Dict[str, Any]]

    # Distributia dispozitivelor dupa tip
    # Fiecare element: {"type": "ir_rgb", "count": 3}
    # Util pentru graficul de tip pie/donut cu tipurile de dispozitive
    device_type_distribution: List[Dict[str, Any]]
