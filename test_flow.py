"""Script de testare end-to-end pentru Smart Home Backend."""
import sys
import json
import urllib.request
import urllib.error

BASE = "http://localhost:8000"
OK = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
errors = []

def req(method, path, body=None, token=None, expected=200):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(r) as resp:
            status = resp.status
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read().strip()
        try:
            result = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            result = {"raw": raw.decode("utf-8", errors="replace")}
    except Exception as e:
        print(f"  {FAIL} {method} {path} — EROARE: {e}")
        errors.append(f"{method} {path}: {e}")
        return None, {}

    icon = OK if status == expected else FAIL
    print(f"  {icon} {method} {path} [{status}]")
    if status != expected:
        print(f"     Body: {json.dumps(result, ensure_ascii=False)[:200]}")
        errors.append(f"{method} {path}: așteptat {expected}, primit {status} → {result}")
    return status, result


print("\n=== AUTH ===")
_, user = req("POST", "/api/auth/register",
    {"email": "test@test.com", "username": "test", "password": "parola123"},
    expected=201)

_, login = req("POST", "/api/auth/login",
    {"email": "test@test.com", "password": "parola123"})
token = login.get("access_token") if login else None
print(f"     Token: {token[:30]}..." if token else "     Token: LIPSĂ")

_, me = req("GET", "/api/auth/me", token=token)
print(f"     User: {me.get('username') if me else 'N/A'}")

# Auth edge cases
print("\n=== AUTH — EDGE CASES ===")
req("POST", "/api/auth/register",
    {"email": "test@test.com", "username": "alt", "password": "parola123"},
    expected=400)  # email duplicat
req("POST", "/api/auth/register",
    {"email": "alt@test.com", "username": "test", "password": "parola123"},
    expected=400)  # username duplicat
req("POST", "/api/auth/login",
    {"email": "test@test.com", "password": "gresita"},
    expected=401)  # parolă greșită
req("GET", "/api/auth/me", expected=401)  # fără token

print("\n=== DEVICES ===")
_, bec = req("POST", "/api/devices/",
    {"name": "Bec Living", "device_type": "ir_rgb", "room": "Living",
     "mqtt_topic": "home/living/bec"},
    token=token, expected=201)
bec_id = bec.get("id") if bec else None
print(f"     Device ID: {bec_id}")

_, pc = req("POST", "/api/devices/",
    {"name": "PC Gaming", "device_type": "wol", "room": "Birou",
     "mqtt_topic": "home/birou/pc", "mac_address": "AA:BB:CC:DD:EE:FF"},
    token=token, expected=201)
pc_id = pc.get("id") if pc else None
print(f"     WoL Device ID: {pc_id}")

# WoL fără MAC — trebuie 400
req("POST", "/api/devices/",
    {"name": "PC fără MAC", "device_type": "wol",
     "mqtt_topic": "home/birou/pc2"},
    token=token, expected=400)

_, devs = req("GET", "/api/devices/", token=token)
print(f"     Total devices: {len(devs) if isinstance(devs, list) else 'N/A'}")

_, dev = req("GET", f"/api/devices/{bec_id}", token=token)

req("PUT", f"/api/devices/{bec_id}",
    {"room": "Living Redenumit"},
    token=token)

req("GET", "/api/devices/", expected=401)  # fără token — 401

print("\n=== COMMANDS ===")
_, c1 = req("POST", "/api/commands/send",
    {"device_id": bec_id, "action": "color", "value": "RED"},
    token=token)

for action, value in [("power", "ON"), ("power", "OFF"),
                      ("color", "BLUE"), ("color", "GREEN"),
                      ("brightness", "50"), ("power", "ON"),
                      ("power", "OFF"), ("color", "RED")]:
    req("POST", "/api/commands/send",
        {"device_id": bec_id, "action": action, "value": value},
        token=token)

_, hist = req("GET", "/api/commands/history", token=token)
print(f"     Comenzi în istoric: {len(hist) if isinstance(hist, list) else 'N/A'}")

_, hist_dev = req("GET", f"/api/commands/history?device_id={bec_id}&limit=5", token=token)
print(f"     Comenzi filtrate (limit=5): {len(hist_dev) if isinstance(hist_dev, list) else 'N/A'}")

print("\n=== WOL ===")
req("POST", "/api/commands/wol", {"device_id": pc_id}, token=token)
req("POST", "/api/commands/wol", {"device_id": bec_id},
    token=token, expected=400)  # bec nu e WoL

print("\n=== ROUTINES — ML ===")
_, gen = req("POST", f"/api/routines/generate-test-data?device_id={bec_id}", token=token)
print(f"     Comenzi generate: {gen.get('count') if gen else 'N/A'}")

_, det = req("GET", "/api/routines/detect", token=token)
if det:
    print(f"     Rutine detectate: {det.get('routines_detected')}, salvate: {det.get('routines_saved')}")
    for r in (det.get("data") or []):
        print(f"       - [{r['confidence']:.2f}] {r['name']}")

_, ruts = req("GET", "/api/routines/", token=token)
print(f"     Total rutine în DB: {len(ruts) if isinstance(ruts, list) else 'N/A'}")

# Activăm prima rutină ML
if isinstance(ruts, list) and ruts:
    first_id = ruts[0]["id"]
    req("PUT", f"/api/routines/{first_id}/toggle",
        {"is_active": True}, token=token)
    print(f"     Rutina {first_id} activată")

print("\n=== ROUTINES — MANUAL ===")
_, rut = req("POST", "/api/routines/",
    {"name": "Aprinde seara", "device_id": bec_id, "action": "power",
     "value": "ON", "trigger_time": "18:00", "days_of_week": "1,2,3,4,5"},
    token=token, expected=201)
if rut:
    req("DELETE", f"/api/routines/{rut['id']}", token=token)
    print(f"     Rutina manuală {rut['id']} creată și ștearsă")

print("\n=== DEVICES — DELETE ===")
req("DELETE", f"/api/devices/{pc_id}", token=token)
_, devs2 = req("GET", "/api/devices/", token=token)
print(f"     Devices după delete: {len(devs2) if isinstance(devs2, list) else 'N/A'}")

# Sumar
print("\n" + "="*50)
if errors:
    print(f"\033[91mERRORI ({len(errors)}):\033[0m")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print(f"\033[92mTOT OK — 0 erori\033[0m")
