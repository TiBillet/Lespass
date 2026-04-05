# Spec — Phase 6 : Client Pi controlvanne

Date : 2026-04-05
Statut : VALIDE

---

## 1. Objectif

Adapter le code Python du Raspberry Pi aux nouveaux endpoints DRF de Lespass (Phases 2-3). Supprimer tout le code legacy (Flask UI, auth X-API-Key, auto-register, copie locale Django). Ajouter l'appairage via discovery (PIN) et le lancement du kiosk Django via Chromium.

---

## 2. Perimetre

### Cote Django (1 ajout)

Ajouter une vue kiosk qui sert `panel_bootstrap.html` avec le contexte tireuse.

```
GET /controlvanne/kiosk/<uuid>/
```

- Protegee par session cookie (obtenue via POST /controlvanne/auth-kiosk/)
- Contexte : tireuse (TireuseBec), becs (queryset TireuseBec du tenant), config (Configuration BaseBillet), slug_focus (uuid)
- Si la tireuse n'existe pas ou n'appartient pas au tenant : 404

### Cote Pi (reecriture)

| Fichier | Action | Detail |
|---------|--------|--------|
| `network/backend_client.py` | Reecrit | Nouveaux endpoints DRF, header `Authorization: Api-Key` |
| `controllers/tibeer_controller.py` | Adapte | Nouvelles reponses API, plus de update_display() |
| `main.py` | Simplifie | Plus de Flask, lancement Chromium kiosk |
| `config/settings.py` | Simplifie | SERVER_URL, API_KEY, TIREUSE_UUID |
| `install.sh` | Reecrit | Discovery PIN, plus de cle partagee |
| `.env.example` | Reecrit | Nouveau format |
| `ui/ui_server.py` | Supprime | Remplace par kiosk Django via Chromium |
| `ui/` | Supprime | Dossier entier |
| `controlvanne/` (copie Django) | Supprime | Reference inutile dans le mono-repo |
| `requierements.txt` | Renomme + nettoye | Typo corrigee, Flask retire |

### Hardware (inchange)

| Fichier | Action |
|---------|--------|
| `hardware/rfid_reader.py` | Inchange |
| `hardware/valve.py` | Inchange |
| `hardware/flow_meter.py` | Inchange |

---

## 3. Nouveau format .env

```env
# Genere par install.sh via discovery (PIN → claim)
SERVER_URL=https://lespass.mondomaine.tld
API_KEY=xxxxxxx.yyyyyyy
TIREUSE_UUID=abc123-def456-...

# Hardware
RFID_TYPE=RC522
GPIO_VANNE=18
GPIO_FLOW_SENSOR=23
FLOW_CALIBRATION_FACTOR=6.5

# Options
VALVE_ACTIVE_HIGH=False
SYSTEMD_NOTIFY=False
```

Variables supprimees : `BACKEND_HOST`, `BACKEND_PORT`, `BACKEND_API_KEY`, `NOM_TIREUSE`, `TIREUSE_BEC`.

`SERVER_URL` est l'URL du tenant (recue de discovery). `API_KEY` est la TireuseAPIKey unique (recue de discovery). `TIREUSE_UUID` est l'UUID de la TireuseBec (recu de discovery).

---

## 4. Mapping ancien → nouveau API

### Auth

| Ancien | Nouveau |
|--------|---------|
| Header `X-API-Key: <cle_partagee>` | Header `Authorization: Api-Key <cle_unique>` |
| Cle partagee `AGENT_SHARED_KEY` | TireuseAPIKey unique par Pi (via discovery) |

### Endpoints

| Ancien endpoint | Nouveau endpoint | Changements |
|----------------|-----------------|-------------|
| `POST /api/rfid/register/` | `POST /controlvanne/api/tireuse/ping/` | Plus d'auto-creation. Ping verifie connectivite + retourne config tireuse. |
| `POST /api/rfid/authorize` | `POST /controlvanne/api/tireuse/authorize/` | Body : `{tireuse_uuid, uid}`. Reponse : `{authorized, session_id, allowed_ml, solde_centimes, liquid_label, is_maintenance}`. Plus de `balance`, `unit_ml`, `unit_label`. |
| `POST /api/rfid/event/` | `POST /controlvanne/api/tireuse/event/` | Body : `{tireuse_uuid, uid, event_type, volume_ml}`. Reponse pour_end : `{status, montant_centimes, transaction_id}`. Plus de `data` wrapper. |
| — | `POST /controlvanne/auth-kiosk/` | Nouveau. Token API → cookie session Django. |
| — | `GET /controlvanne/kiosk/<uuid>/` | Nouveau. Vue kiosk (panel_bootstrap.html). |

### Reponse authorize — mapping champs

| Ancien champ | Nouveau champ | Notes |
|-------------|--------------|-------|
| `authorized` | `authorized` | Inchange |
| `session_id` | `session_id` | Inchange |
| `balance` (str, ex: "12.50") | `solde_centimes` (int, ex: 1250) | Centimes au lieu d'euros |
| `flow_calibration_factor` | Via `ping` response `tireuse.calibration_factor` | Plus dans authorize, dans ping |
| `liquid_label` | `liquid_label` | Inchange |
| `unit_label` (ex: "patate") | Supprime | Toujours "€" |
| `unit_ml` | Supprime | Remplace par `allowed_ml` |
| — | `allowed_ml` (float) | Volume max autorise en ml |
| — | `is_maintenance` (bool) | Carte maintenance detectee |

### Reponse event — mapping champs

| Ancien champ | Nouveau champ | Notes |
|-------------|--------------|-------|
| `status` | `status` | Inchange |
| `force_close` | Supprime | Le Pi gere le volume max localement via `allowed_ml` |
| — | `montant_centimes` (int) | Uniquement sur pour_end |
| — | `transaction_id` (int) | Uniquement sur pour_end |

### Suppression de force_close

L'ancien systeme envoyait `force_close=True` dans la reponse `pour_update` quand le solde etait epuise. Le nouveau systeme calcule `allowed_ml` a l'authorize — le Pi ferme la vanne localement quand le volume atteint `allowed_ml`. Plus besoin de round-trip serveur pour forcer la fermeture.

Le controleur doit donc :
1. Stocker `allowed_ml` recu a l'authorize
2. A chaque `pour_update`, comparer `volume_servi >= allowed_ml`
3. Si depasse → fermer la vanne, envoyer `pour_end`

---

## 5. Nouveau backend_client.py

### Classe BackendClient

```python
class BackendClient:
    def __init__(self):
        self.server_url = SERVER_URL        # ex: "https://lespass.mondomaine.tld"
        self.tireuse_uuid = TIREUSE_UUID    # ex: "abc123-..."
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {API_KEY}",
        }

    def ping(self) -> dict:
        """POST /controlvanne/api/tireuse/ping/
        Retourne la config tireuse (nom, prix, calibration, reservoir)."""

    def authorize(self, uid: str) -> dict:
        """POST /controlvanne/api/tireuse/authorize/
        Retourne authorized, session_id, allowed_ml, solde_centimes, etc."""

    def send_event(self, event_type: str, uid: str, volume_ml: float = 0) -> dict:
        """POST /controlvanne/api/tireuse/event/
        Envoie pour_start, pour_update, pour_end, card_removed."""

    def auth_kiosk(self) -> str:
        """POST /controlvanne/auth-kiosk/
        Retourne le session_key pour le cookie Chromium."""
```

Plus de methode `register()`.

---

## 6. Nouveau controleur

### Changements dans TibeerController

| Ancien comportement | Nouveau comportement |
|---------------------|----------------------|
| `update_display(msg, color, balance)` | Supprime (kiosk Django via WebSocket) |
| `client.register()` au demarrage | `client.ping()` au demarrage |
| `response["balance"]` pour affichage | `response["solde_centimes"]` (pas affiche, juste log) |
| `response["flow_calibration_factor"]` dans authorize | Lu dans `ping()` au demarrage |
| `response["force_close"]` dans pour_update | Comparaison locale `volume >= allowed_ml` |
| Session start vol = `flow_meter.volume_l() * 1000` | Inchange |
| Grace period 1s pour retrait carte | Inchange |
| Boucle 100ms | Inchange |

### Nouveau champ : allowed_ml

Le controleur stocke `self.allowed_ml` recu de l'authorize. A chaque pour_update :

```python
served_ml = (self.flow_meter.volume_l() * 1000) - self.session_start_vol
if served_ml >= self.allowed_ml:
    self.valve.close()
    self.client.send_event("pour_end", self.current_uid, served_ml)
    self._reset_session()
```

---

## 7. Nouveau main.py

### Flow de demarrage

```python
def main():
    # 1. Init hardware
    rfid = RFIDReader()
    valve = Valve()
    flow_meter = FlowMeter()
    client = BackendClient()

    # 2. Ping serveur (verif connectivite + config)
    config = client.ping()
    if config.get("tireuse", {}).get("calibration_factor"):
        flow_meter.set_calibration_factor(config["tireuse"]["calibration_factor"])

    # 3. Auth kiosk → cookie session
    session_key = client.auth_kiosk()

    # 4. Lancer Chromium kiosk en background
    kiosk_url = f"{SERVER_URL}/controlvanne/kiosk/{TIREUSE_UUID}/"
    launch_chromium_kiosk(kiosk_url, session_key)

    # 5. Boucle controleur
    controller = TibeerController(rfid, valve, flow_meter, client)
    controller.run()
```

### Lancement Chromium

```python
def launch_chromium_kiosk(url, session_key):
    """Lance Chromium en mode kiosk avec le cookie de session."""
    import subprocess
    # Chromium en mode kiosk, pas de barre d'adresse, plein ecran
    subprocess.Popen([
        "chromium-browser",
        "--kiosk",
        "--noerrdialogs",
        "--disable-infobars",
        "--disable-translate",
        f"--app={url}",
    ], env={**os.environ, "DISPLAY": ":0"})
```

Note : le cookie session est gere par Chromium via le Set-Cookie de la reponse auth-kiosk. Le Pi fait d'abord un GET sur l'URL kiosk avec le cookie pour l'injecter dans le profil Chromium. Alternative : utiliser `--user-data-dir` avec un profil pre-configure.

---

## 8. Nouveau install.sh

### Flow interactif

```
1. Setup OS (apt, pigpio, chromium, python3-venv)
2. Clone repo → /home/sysop/tibeer/
3. Creer venv + installer deps
4. Demander : URL publique du serveur TiBillet
5. Demander : PIN 6 chiffres (affiche dans l'admin Unfold)
6. Appeler POST {url_publique}/api/discovery/claim/ avec le PIN
7. Recevoir : server_url, api_key, tireuse_uuid
8. Demander : type de lecteur RFID (RC522/VMA405/ACR122U)
9. Generer .env avec toutes les valeurs
10. Configurer systemd (tibeer.service + kiosk.service)
11. Redemarrer
```

### Changements vs ancien install.sh

| Ancien | Nouveau |
|--------|---------|
| Demande URL serveur Django (host:port) | Demande URL publique TiBillet |
| Demande cle API partagee | Demande PIN 6 chiffres |
| Genere UUID depuis MAC address | UUID recu de discovery |
| Kiosk pointe sur localhost:5000 | Kiosk pointe sur {server_url}/controlvanne/kiosk/{uuid}/ |
| Flask dans tibeer.service | Plus de Flask |

---

## 9. Fichiers supprimes

| Fichier/Dossier | Raison |
|-----------------|--------|
| `ui/ui_server.py` | Remplace par kiosk Django |
| `ui/` (dossier entier) | Vide apres suppression |
| `controlvanne/` (copie Django) | Reference inutile, le vrai code est dans le mono-repo |
| `first/` | Scripts de premier demarrage legacy |
| `requierements.txt` | Renomme en `requirements.txt` (typo) |

---

## 10. Fichiers crees/modifies — resume

| Fichier | Action |
|---------|--------|
| **Django** | |
| `controlvanne/viewsets.py` | +vue kiosk `GET /controlvanne/kiosk/<uuid>/` |
| `controlvanne/urls.py` | +path kiosk |
| **Pi** | |
| `network/backend_client.py` | Reecrit (4 methodes, nouveaux endpoints) |
| `controllers/tibeer_controller.py` | Adapte (allowed_ml, plus de Flask, plus de force_close) |
| `main.py` | Simplifie (plus de Flask, lancement Chromium, ping au demarrage) |
| `config/settings.py` | Simplifie (SERVER_URL, API_KEY, TIREUSE_UUID) |
| `install.sh` | Reecrit (discovery PIN) |
| `.env.example` | Reecrit (nouveau format) |
| `requirements.txt` | Renomme + Flask retire |

---

## 11. Tests

### Cote Django
- pytest : test de la vue kiosk (200 avec session, 403 sans session, 404 uuid inexistant)
- Les tests API existants (32) couvrent deja les endpoints que le Pi appelle

### Cote Pi
- Les tests hardware existants (`tests/test_rfid_*.py`, `tests/check_hardware.py`) restent inchanges
- Tests unitaires `BackendClient` : mocker les endpoints, verifier les payloads envoyes
- Test d'integration : simuler le flow complet ping → authorize → pour_update → pour_end (mock hardware)

---

## 12. Risques

1. **Cookie kiosk** : Chromium en mode `--app` gere les cookies normalement. Le Set-Cookie de auth-kiosk sera stocke. Mais si le cookie expire, le kiosk perdra la session. Prevoir une reconnexion periodique (cron ou watchdog dans main.py).

2. **Pi hors-ligne** : si le Pi perd le reseau, les API calls echouent. Le controleur doit gerer ca gracieusement (fermer la vanne, afficher "hors-ligne" sur le kiosk via un mecanisme local). Le WebSocket du kiosk a deja un reconnect automatique (`onclose → setTimeout(connect, 1000)`).

3. **Chromium et cookie injection** : le Pi doit d'abord obtenir le cookie via auth-kiosk, puis lancer Chromium. Si Chromium est lance avant d'avoir le cookie, la page kiosk sera refusee (403). L'ordre dans main.py est : ping → auth-kiosk → lancer Chromium → boucle controleur.

4. **Volume max local** : le Pi ferme la vanne quand `volume >= allowed_ml`. Si le debitmetre est imprecis, le client peut recevoir un peu plus ou moins que prevu. La calibration (Phase 4) minimise cet ecart. Le pour_end envoie le volume reel — Django facture le volume reel, pas le volume autorise.
