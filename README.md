# 🏠 Smart Home IoT Backend

> **Sistem IoT pentru automatizarea dispozitivelor non-smart din locuință**

[![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-red)](https://sqlalchemy.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue?logo=docker)](https://docker.com)
[![Tests](https://img.shields.io/badge/Tests-37%20passed-brightgreen?logo=pytest)](tests/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 📋 Despre Proiect

**Smart Home IoT Backend** este un sistem backend complet pentru transformarea dispozitivelor electronice obișnuite (non-smart) în dispozitive inteligente, controlabile de la distanță. Utilizatorul poate controla becuri, televizoare, aparate de aer condiționat și calculatoare prin intermediul unei aplicații mobile, fără a înlocui aparatele existente — ci adăugând module IR/relay/WoL.

Sistemul include un **modul de Machine Learning** (DBSCAN clustering) care analizează istoricul comenzilor și detectează automat rutine repetitive ale utilizatorului, sugerând automatizări personalizate (ex: "Aprinzi becul în fiecare seară la 18:30 — vrei o rutină?").

> 🎓 **Lucrare de licență** — ASE București, Facultatea CSIE, 2026
> *"Sistem IoT pentru automatizarea dispozitivelor non-smart din locuință"*

---

## 🏗️ Arhitectura Sistemului

```
┌─────────────────────────────────────────────────────────────────┐
│                        UTILIZATOR                               │
└─────────────────────────┬───────────────────────────────────────┘
                          │ REST API (JSON)
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                   APLICAȚIE ANDROID                             │
│              (Kotlin + Retrofit + MVVM)                         │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTTP/HTTPS :8000
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │   Auth   │  │ Devices  │  │  Scenes  │  │   ML/DBSCAN  │   │
│  │   JWT    │  │  CRUD    │  │ Execute  │  │   Routines   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              SQLAlchemy 2.0 ORM + SQLite                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              APScheduler (rutine automate)               │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────┬───────────────────────────────────────┘
                          │ MQTT (paho-mqtt)
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│               MOSQUITTO MQTT BROKER :1883                       │
│                  Topics: home/{room}/{device}                   │
└──────────┬──────────────────────────────────────┬───────────────┘
           │ Subscribe/Publish                    │ Subscribe/Publish
           ▼                                      ▼
┌──────────────────────┐              ┌───────────────────────────┐
│     ESP32 #1         │              │        ESP32 #2            │
│  Modul IR Blaster    │              │    Modul Relay 4-canale    │
│  (TV, AC, LED RGB)   │              │    (prize, becuri 220V)    │
└──────────┬───────────┘              └─────────────┬─────────────┘
           │ IR signal                              │ relay switch
           ▼                                        ▼
┌──────────────────┐              ┌─────────────────────────────────┐
│   TV / AC / LED  │              │     Prize / Becuri / Aparate    │
│  (dispozitive    │              │     (dispozitive non-smart)     │
│   non-smart)     │              └─────────────────────────────────┘
└──────────────────┘
```

| Strat | Tehnologie | Rol |
|-------|-----------|-----|
| **Frontend** | Android (Kotlin) | Interfață utilizator, control dispozitive |
| **Backend** | FastAPI + Python 3.13 | API REST, logică business, ML |
| **Baza de date** | SQLite + SQLAlchemy 2.0 | Persistența datelor |
| **Protocol IoT** | MQTT via Mosquitto | Comunicare cu modulele hardware |
| **Hardware** | ESP32 | Modul IR / relay / WoL pe rețeaua locală |
| **ML** | scikit-learn DBSCAN | Detectare automată rutine |
| **Automatizare** | APScheduler | Execuție rutine programate |
| **Containerizare** | Docker + docker-compose | Deploy consistent pe orice mașină |

---

## 🛠️ Tehnologii Utilizate

| Tehnologie | Rol | Versiune |
|-----------|-----|---------|
| **Python** | Limbajul principal al backend-ului | 3.13 |
| **FastAPI** | Framework REST API (async, auto-docs) | 0.115.0 |
| **SQLAlchemy** | ORM — modele DB și relații | 2.0.x |
| **SQLite** | Baza de date (fișier local, zero config) | built-in |
| **pydantic-settings** | Configurare din fișier `.env` | 2.5.2 |
| **python-jose** | Generare și validare JWT | 3.3.0 |
| **bcrypt** | Hash parole (rezistent la brute-force) | 5.0.0 |
| **paho-mqtt** | Client MQTT pentru comunicare ESP32 | 2.1.0 |
| **scikit-learn** | DBSCAN clustering pentru ML | 1.5.2 |
| **APScheduler** | Scheduler pentru rutine automate | 3.10.4 |
| **wakeonlan** | Trimitere magic packet Wake-on-LAN | 3.1.0 |
| **Mosquitto** | MQTT broker open-source | 2.x (Docker) |
| **Docker** | Containerizare backend + broker | latest |
| **pytest** | Framework de testare automată | 8.3.3 |
| **httpx** | Client HTTP pentru TestClient FastAPI | 0.27.2 |

---

## 📡 Endpoint-uri API

API-ul este documentat automat la `http://localhost:8000/docs` (Swagger UI) și `http://localhost:8000/redoc`.

### 🔐 Autentificare

| Method | Path | Descriere | Auth |
|--------|------|-----------|------|
| `POST` | `/api/auth/register` | Înregistrare utilizator nou | ❌ |
| `POST` | `/api/auth/login` | Login, returnează JWT Bearer token | ❌ |
| `GET` | `/api/auth/me` | Datele utilizatorului autentificat | ✅ |
| `GET` | `/api/auth/preferences` | Preferințele utilizatorului | ✅ |
| `PUT` | `/api/auth/preferences` | Actualizare preferințe (timezone, theme, limbă) | ✅ |

### 🏠 Camere

| Method | Path | Descriere | Auth |
|--------|------|-----------|------|
| `GET` | `/api/rooms/` | Lista camerelor cu numărul de dispozitive | ✅ |
| `POST` | `/api/rooms/` | Adaugă cameră nouă | ✅ |
| `PUT` | `/api/rooms/{id}` | Actualizează cameră (nume, icon) | ✅ |
| `DELETE` | `/api/rooms/{id}` | Șterge cameră (dispozitivele rămân) | ✅ |

### 📱 Dispozitive

| Method | Path | Descriere | Auth |
|--------|------|-----------|------|
| `GET` | `/api/devices/` | Lista dispozitivelor, filtru opțional `?room=` | ✅ |
| `POST` | `/api/devices/` | Adaugă dispozitiv (IR/relay/WoL) | ✅ |
| `GET` | `/api/devices/supported-actions` | Acțiuni suportate per tip de dispozitiv | ✅ |
| `GET` | `/api/devices/{id}` | Detalii dispozitiv | ✅ |
| `PUT` | `/api/devices/{id}` | Actualizează dispozitiv | ✅ |
| `DELETE` | `/api/devices/{id}` | Șterge dispozitiv + istoricul comenzilor | ✅ |

### ⚡ Comenzi

| Method | Path | Descriere | Auth |
|--------|------|-----------|------|
| `POST` | `/api/commands/send` | Trimite comandă MQTT la dispozitiv | ✅ |
| `GET` | `/api/commands/history` | Istoricul comenzilor, filtru `?device_id=` | ✅ |
| `POST` | `/api/commands/wol` | Trimite magic packet Wake-on-LAN | ✅ |

### 🎬 Scene

| Method | Path | Descriere | Auth |
|--------|------|-----------|------|
| `GET` | `/api/scenes/` | Lista scenelor cu acțiunile lor | ✅ |
| `POST` | `/api/scenes/` | Creează scenă cu acțiuni multiple și delay-uri | ✅ |
| `GET` | `/api/scenes/{id}` | Detalii scenă completă | ✅ |
| `POST` | `/api/scenes/{id}/execute` | Execută scena (async, respectă delay-urile) | ✅ |
| `PUT` | `/api/scenes/{id}` | Actualizează scenă și acțiunile ei | ✅ |
| `DELETE` | `/api/scenes/{id}` | Șterge scenă și acțiunile (cascade) | ✅ |

### 🔄 Rutine Automate

| Method | Path | Descriere | Auth |
|--------|------|-----------|------|
| `GET` | `/api/routines/` | Lista rutinelor (manuale + sugerate de ML) | ✅ |
| `POST` | `/api/routines/` | Creează rutină manuală | ✅ |
| `GET` | `/api/routines/detect` | Rulează ML DBSCAN, salvează rutine noi | ✅ |
| `PUT` | `/api/routines/{id}/toggle` | Activează / dezactivează rutină | ✅ |
| `DELETE` | `/api/routines/{id}` | Șterge rutină | ✅ |
| `POST` | `/api/routines/generate-test-data` | Generează date sintetice pentru demo ML | ✅ |

### 📊 Dashboard

| Method | Path | Descriere | Auth |
|--------|------|-----------|------|
| `GET` | `/api/dashboard/stats` | Statistici agregate (dispozitive, comenzi, top device, ore de vârf) | ✅ |
| `GET` | `/api/dashboard/activity` | Ultimele 50 activități ale utilizatorului | ✅ |

### 🔔 Notificări

| Method | Path | Descriere | Auth |
|--------|------|-----------|------|
| `GET` | `/api/notifications/` | Lista notificărilor, filtru `?unread_only=true` | ✅ |
| `GET` | `/api/notifications/count` | Numărul notificărilor necitite (pentru badge) | ✅ |
| `PUT` | `/api/notifications/{id}/read` | Marchează notificare ca citită | ✅ |
| `PUT` | `/api/notifications/read-all` | Marchează toate ca citite | ✅ |
| `DELETE` | `/api/notifications/{id}` | Șterge notificare | ✅ |

### ⚙️ Sistem

| Method | Path | Descriere | Auth |
|--------|------|-----------|------|
| `GET` | `/` | Health check — verifică starea serviciului | ❌ |

> **Total: 38 endpoint-uri** pe 8 routere + root

---

## 🧠 Machine Learning — Detectarea Rutinelor

Sistemul analizează istoricul comenzilor și identifică automat tiparele de comportament ale utilizatorului folosind **DBSCAN (Density-Based Spatial Clustering of Applications with Noise)**.

### Cum funcționează

```
Istoric comenzi (30 zile)
        │
        ▼
Grupare pe (device, action, value)
        │
        ▼
Extragere ore zi → vector 1D [18.5, 18.3, 18.7, 18.4, ...]
        │
        ▼
DBSCAN clustering (eps=15 min, min_samples=5)
        │
        ▼
Cluster identificat → calcul ora medie + zile active
        │
        ▼
Rutină sugerată cu confidence score [0.0 – 1.0]
```

### Parametri algoritm

| Parametru | Valoare | Semnificație |
|-----------|---------|-------------|
| `days_back` | 30 zile | Perioada de analiză a istoricului |
| `eps` | 15 minute | Distanța maximă între două comenzi din același cluster |
| `min_samples` | 5 | Numărul minim de ocurențe pentru a forma un tipar |

### Exemplu real

```
Comenzi detectate:
  18:28 - Bec Living - power - on  (Luni)
  18:31 - Bec Living - power - on  (Marți)
  18:27 - Bec Living - power - on  (Miercuri)
  18:33 - Bec Living - power - on  (Joi)
  18:29 - Bec Living - power - on  (Vineri)
           │
           ▼
  ✅ Rutină detectată:
     Nume:       "Bec Living - power (18:29)"
     Trigger:    18:29
     Zile:       1,2,3,4,5 (Luni–Vineri)
     Confidence: 0.87
```

---

## 🗄️ Schema Bazei de Date

**10 tabele SQLite** gestionate cu SQLAlchemy 2.0 (Declarative Base + Mapped[]):

```
┌──────────┐         ┌──────────────────┐
│  users   │────────▶│ user_preferences  │  (one-to-one)
│──────────│         │──────────────────│
│ id       │         │ id               │
│ email    │         │ user_id (FK)     │
│ username │         │ timezone         │
│ password │         │ language         │
│ created  │         │ theme            │
└────┬─────┘         └──────────────────┘
     │
     ├──────────────────────────────────────────┐
     │                                          │
     ▼                                          ▼
┌──────────┐   room_id   ┌──────────┐    ┌──────────┐
│  rooms   │◀────────────│ devices  │───▶│ routines │
│──────────│             │──────────│    │──────────│
│ id       │             │ id       │    │ id       │
│ name     │             │ name     │    │ name     │
│ icon     │             │ type     │    │ device_id│
│ owner_id │             │ room     │    │ action   │
└──────────┘             │ room_id  │    │ trigger  │
                         │ topic    │    │ days     │
                         │ mac_addr │    │ is_active│
                         │ is_online│    │ ml_flag  │
                         └────┬─────┘    └──────────┘
                              │
                    ┌─────────┼──────────────┐
                    │         │              │
                    ▼         ▼              ▼
             ┌──────────┐ ┌──────────┐ ┌──────────────┐
             │ commands │ │  scenes  │ │notifications │
             │──────────│ │──────────│ │──────────────│
             │ id       │ │ id       │ │ id           │
             │ device_id│ │ name     │ │ user_id      │
             │ user_id  │ │ icon     │ │ title        │
             │ action   │ │ owner_id │ │ message      │
             │ value    │ │ is_active│ │ type         │
             │ source   │ └────┬─────┘ │ is_read      │
             │ timestamp│      │       └──────────────┘
             └──────────┘      │
                               ▼
                        ┌──────────────┐   ┌──────────────┐
                        │ scene_actions│   │ activity_logs│
                        │──────────────│   │──────────────│
                        │ id           │   │ id           │
                        │ scene_id (FK)│   │ user_id      │
                        │ device_id(FK)│   │ action       │
                        │ action       │   │ entity_type  │
                        │ value        │   │ entity_id    │
                        │ exec_order   │   │ details      │
                        │ delay_sec    │   │ ip_address   │
                        └──────────────┘   └──────────────┘
```

| Tabel | Descriere |
|-------|-----------|
| `users` | Conturi utilizatori cu credențiale bcrypt |
| `user_preferences` | Preferințe one-to-one (timezone, theme, limbă) |
| `rooms` | Camere fizice din locuință |
| `devices` | Dispozitive IoT (IR, relay, WoL) |
| `commands` | **Tabel critic ML** — fiecare comandă trimisă vreodată |
| `routines` | Rutine automate (manuale + sugerate de ML) |
| `scenes` | Grupuri de acțiuni executate împreună |
| `scene_actions` | Acțiunile individuale dintr-o scenă |
| `notifications` | Notificări in-app generate automat |
| `activity_logs` | Jurnal complet al acțiunilor (audit trail) |

---

## 🚀 Instalare și Rulare

### Varianta 1: Local (development)

```bash
# 1. Clonare repository
git clone https://github.com/DenisAndreiC/smart-home-backend.git
cd smart-home-backend

# 2. Creare și activare virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

# 3. Instalare dependențe
pip install -r requirements.txt

# 4. Configurare variabile de mediu
cp .env.example .env             # sau editează .env direct

# 5. Rulare server
python3 main.py
# → API disponibil la: http://localhost:8000
# → Documentație:      http://localhost:8000/docs
```

> **Notă:** MQTT broker-ul (Mosquitto) trebuie să ruleze separat pe `localhost:1883` pentru funcționalitatea completă. Fără el, comenzile eșuează silențios (excepție prinsă la startup).

### Varianta 2: Docker (recomandat)

```bash
# 1. Clonare repository
git clone https://github.com/DenisAndreiC/smart-home-backend.git
cd smart-home-backend

# 2. Pornire servicii (backend + mosquitto)
docker-compose up -d

# 3. Verificare status
docker-compose ps
docker-compose logs -f backend

# → Backend:      http://localhost:8000/docs
# → MQTT Broker:  localhost:1883
# → MQTT WS:      localhost:9001

# Oprire
docker-compose down
```

Baza de date SQLite este persistată în `./smart_home.db` pe host (volum montat).

---

## 🧪 Teste

Suite completă de teste pytest — **37 teste, toate trec** pe un DB SQLite in-memory izolat per test.

```bash
# Activare virtual environment (dacă nu e activ)
source .venv/bin/activate

# Rulare toate testele cu output verbose
python3 -m pytest tests/ -v

# Rulare un singur modul
python3 -m pytest tests/test_auth.py -v

# Rulare cu raport scurt
python3 -m pytest tests/ --tb=short
```

| Modul de test | Teste | Ce acoperă |
|--------------|-------|-----------|
| `test_auth.py` | 9 | Register, login, JWT, /me, token invalid |
| `test_devices.py` | 8 | CRUD dispozitive, filtrare, validare WoL |
| `test_commands.py` | 6 | Trimitere comenzi, istoric, filtrare, WoL |
| `test_routines.py` | 6 | CRUD rutine, generare date ML, DBSCAN detect |
| `test_scenes.py` | 5 | Creare scenă, execuție async, CRUD |
| `test_dashboard.py` | 3 | Statistici, activity log, notificări |
| **Total** | **37** | **100% passed** |

**Tehnică cheie:** `StaticPool` pentru SQLite in-memory — garantează că toate operațiile testului folosesc aceeași conexiune, prevenind baze de date goale pe conexiuni secundare.

---

## 📁 Structura Proiectului

```
smart-home-backend/
│
├── main.py                     # Entry point — FastAPI app, lifespan, routere
├── config.py                   # Settings din .env via pydantic-settings
├── requirements.txt            # Toate dependențele Python (pinned)
├── Dockerfile                  # Container backend (python:3.13-slim)
├── docker-compose.yml          # Orchestrare backend + mosquitto
├── .dockerignore               # Fișiere excluse din imagine Docker
├── .env                        # Variabile de mediu (NU se commitează)
├── .gitignore                  # Fișiere excluse din git
│
├── database/
│   ├── __init__.py             # Export modele și get_db
│   └── db.py                   # 10 modele SQLAlchemy 2.0 + engine + get_db
│
├── models/
│   ├── __init__.py             # Export schemas și enums
│   ├── enums.py                # DeviceType, CommandSource, NotificationType etc.
│   └── schemas.py              # 30+ Pydantic v2 schemas pentru request/response
│
├── routers/
│   ├── __init__.py
│   ├── auth.py                 # Register, login, /me, preferințe
│   ├── devices.py              # CRUD dispozitive + supported-actions
│   ├── rooms.py                # CRUD camere
│   ├── commands.py             # Trimite comandă, istoric, Wake-on-LAN
│   ├── scenes.py               # CRUD scene + execuție async cu delay-uri
│   ├── routines.py             # CRUD rutine + detectare ML + date test
│   ├── dashboard.py            # Statistici agregate + activity log
│   └── notifications.py       # CRUD notificări + read-all + count
│
├── services/
│   ├── __init__.py
│   ├── auth_service.py         # bcrypt hash/verify + JWT create/decode
│   ├── mqtt_service.py         # Singleton paho-mqtt, publish_command
│   ├── wol_service.py          # Trimitere magic packet Wake-on-LAN
│   ├── ml_service.py           # DBSCAN clustering pe istoricul comenzilor
│   ├── scheduler_service.py    # APScheduler — verificare rutine la fiecare minut
│   └── notification_service.py # Helper-e creare notificări automate
│
├── utils/
│   ├── __init__.py
│   ├── constants.py            # ML params, SUPPORTED_IR_ACTIONS, limite
│   ├── exceptions.py           # Excepții HTTP personalizate (404, 400, 401, 503)
│   ├── helpers.py              # validate_mac, validate_time, generate_mqtt_topic
│   └── middleware.py           # ActivityMiddleware — logare automată acțiuni
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Fixtures: test_db (StaticPool), test_client, test_user
│   ├── test_auth.py            # 9 teste autentificare
│   ├── test_devices.py         # 8 teste dispozitive
│   ├── test_commands.py        # 6 teste comenzi
│   ├── test_routines.py        # 6 teste rutine + ML
│   ├── test_scenes.py          # 5 teste scene
│   └── test_dashboard.py       # 3 teste dashboard + notificări
│
└── mosquitto/
    ├── config/
    │   └── mosquitto.conf      # Configurare broker MQTT
    ├── data/                   # Persistența mesajelor MQTT (volum Docker)
    └── log/                    # Log-uri Mosquitto (volum Docker)
```

---

## 🔧 Configurare `.env`

| Variabilă | Exemplu | Descriere |
|-----------|---------|-----------|
| `DATABASE_URL` | `sqlite:///./smart_home.db` | URL conexiune SQLAlchemy |
| `MQTT_BROKER` | `localhost` | IP/hostname broker MQTT (în Docker: `mosquitto`) |
| `MQTT_PORT` | `1883` | Portul brokerului MQTT |
| `MQTT_USERNAME` | *(gol)* | Username broker (opțional, gol pentru dev) |
| `MQTT_PASSWORD` | *(gol)* | Parolă broker (opțional, gol pentru dev) |
| `JWT_SECRET` | `super-secret-key` | **Schimbă în producție!** Cheie semnare JWT |
| `JWT_ALGORITHM` | `HS256` | Algoritmul JWT (HS256 recomandat) |
| `JWT_EXPIRATION_MINUTES` | `1440` | Durata token-ului (1440 = 24 ore) |

> ⚠️ **Securitate:** Nu commitați niciodată fișierul `.env` cu credențiale reale. Fișierul `.gitignore` îl exclude automat.

---

## 📱 Integrare cu App Android

Aplicația Android comunică exclusiv cu backend-ul prin **REST API** (JSON over HTTP). Nu are nevoie de acces direct la MQTT sau baza de date.

**Flow tipic:**
```
Login → JWT token → stocat în SharedPreferences
→ toate request-urile includ: Authorization: Bearer <token>
→ trimite comandă → POST /api/commands/send
→ primește status dispozitiv → GET /api/devices/{id}
```

🔗 **Repository Android:** _[work in progress — coming soon]_

---

## 🔌 Integrare cu Firmware ESP32

Modulele ESP32 subscriu la topic-uri MQTT și execută comenzile primite de la backend.

### Format topic MQTT
```
home/{camera}/{dispozitiv}/command   ← backend publică
home/{camera}/{dispozitiv}/status    ← ESP32 publică (feedback)
```

### Format mesaj (JSON)
```json
{
  "action": "power",
  "value": "on"
}
```

### Tipuri de acțiuni suportate

| Tip dispozitiv | Acțiuni |
|----------------|---------|
| `ir_rgb` | `power`, `brightness`, `color`, `mode` |
| `ir_tv` | `power`, `volume_up`, `volume_down`, `mute`, `channel_up`, `channel_down` |
| `ir_ac` | `power`, `temperature`, `mode`, `fan_speed` |
| `relay` | `on`, `off`, `toggle` |
| `wol` | Magic packet UDP (Wake-on-LAN) |

🔗 **Repository Firmware ESP32:** _[work in progress — coming soon]_

---

## 📊 Screenshots

> Swagger UI — documentație interactivă automată generată de FastAPI

_Screenshots disponibile după pornirea aplicației la `http://localhost:8000/docs`_

---

## 🗺️ Roadmap

- [x] Backend API complet (38 endpoint-uri)
- [x] Autentificare JWT + bcrypt
- [x] Sistem MQTT cu singleton paho-mqtt
- [x] Machine Learning DBSCAN pentru detecție rutine
- [x] Scene multi-device cu execuție async și delay-uri
- [x] Dashboard cu statistici agregate
- [x] Notificări in-app automate
- [x] ActivityLog middleware (audit trail)
- [x] APScheduler pentru rutine automate
- [x] Docker support (Dockerfile + docker-compose + Mosquitto)
- [x] Suite de teste pytest (37 teste, 100% pass)
- [ ] Aplicație Android (Kotlin + Retrofit + MVVM)
- [ ] Firmware ESP32 (Arduino/IDF + MQTT)
- [ ] Integrare end-to-end (backend ↔ ESP32 ↔ dispozitive reale)
- [ ] Autentificare MQTT (username/parolă per dispozitiv)
- [ ] HTTPS + certificate SSL în producție

---

## 👤 Autor

**Denis Andrei Cucu**
Student — Facultatea de Cibernetică, Statistică și Informatică Economică (CSIE)
Academia de Studii Economice din București (ASE), 2026

📧 Contact: _via GitHub_
🔗 GitHub: [@DenisAndreiC](https://github.com/DenisAndreiC)

> 🎓 Acest proiect reprezintă **lucrarea de licență**:
> *"Sistem IoT pentru automatizarea dispozitivelor non-smart din locuință"*

---

## 📄 Licență

Distribuit sub licența **MIT**. Poți folosi, modifica și distribui liber codul, cu menționarea autorului original.

```
MIT License — Copyright (c) 2026 Denis Andrei Cucu
```

---

<div align="center">

**⭐ Dacă ți-a fost util acest proiect, lasă un star pe GitHub! ⭐**

*Construit cu ❤️ pentru lucrarea de licență ASE CSIE 2026*

</div>
