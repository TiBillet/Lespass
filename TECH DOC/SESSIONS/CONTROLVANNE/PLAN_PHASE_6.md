# Phase 6 — Client Pi controlvanne

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Le Raspberry Pi utilise les nouveaux endpoints DRF (Phases 2-3), s'appaire via discovery (PIN), et affiche le kiosk Django via Chromium. Le code legacy (Flask UI, X-API-Key, auto-register, copie Django locale) est supprime.

**Architecture:** Cote Django, ajout d'une vue kiosk (`GET /controlvanne/kiosk/<uuid>/`). Cote Pi, reecriture de `backend_client.py`, adaptation du controleur et de `main.py`, simplification de `config/settings.py`, reecriture de `install.sh` avec discovery, suppression de `ui/` et `controlvanne/` (copie locale).

**Tech Stack:** Python 3.11, requests, pigpio, mfrc522, python-dotenv, Django templates, Bootstrap 5.3, Django Channels (WebSocket)

**Spec de reference :** `TECH DOC/SESSIONS/CONTROLVANNE/SPEC_PHASE_6_CLIENT_PI.md`

**IMPORTANT :** Ne pas faire d'operations git. Le mainteneur gere git.

---

## Vue d'ensemble des fichiers

### Cote Django

| Fichier | Action | Role |
|---------|--------|------|
| `controlvanne/viewsets.py` | Modifier | +vue kiosk `kiosk_view()` |
| `controlvanne/urls.py` | Modifier | +path kiosk |

### Cote Pi

| Fichier | Action | Role |
|---------|--------|------|
| `controlvanne/Pi/network/backend_client.py` | Reecrit | Nouveaux endpoints DRF |
| `controlvanne/Pi/controllers/tibeer_controller.py` | Adapte | allowed_ml, plus de Flask |
| `controlvanne/Pi/main.py` | Simplifie | Plus de Flask, lancement Chromium |
| `controlvanne/Pi/config/settings.py` | Simplifie | SERVER_URL, API_KEY, TIREUSE_UUID |
| `controlvanne/Pi/.env.example` | Reecrit | Nouveau format |
| `controlvanne/Pi/install.sh` | Reecrit | Discovery PIN |
| `controlvanne/Pi/requirements.txt` | Cree (renomme) | Flask retire |
| `controlvanne/Pi/ui/` | Supprime | Remplace par kiosk Django |
| `controlvanne/Pi/controlvanne/` | Supprime | Copie locale inutile |
| `controlvanne/Pi/requierements.txt` | Supprime | Remplace par requirements.txt |

---

## Ordre des taches

1. Vue kiosk Django (prerequis pour le Pi)
2. config/settings.py Pi (prerequis pour backend_client)
3. backend_client.py Pi
4. tibeer_controller.py Pi
5. main.py Pi
6. .env.example + requirements.txt
7. install.sh
8. Suppression code legacy
9. Tests Django
10. Verification finale

---

### Tache 1 : Vue kiosk Django

**Fichiers :**
- Modifier : `controlvanne/viewsets.py`
- Modifier : `controlvanne/urls.py`

- [ ] **Step 1 : Ajouter la vue kiosk dans viewsets.py**

Apres la classe `AuthKioskView`, ajouter :

```python
from django.shortcuts import render, get_object_or_404


def kiosk_view(request, uuid):
    """
    GET /controlvanne/kiosk/<uuid>/
    Affiche le kiosk (panel_bootstrap.html) pour une tireuse.
    Protege par session cookie (obtenue via POST /controlvanne/auth-kiosk/).
    / Displays the kiosk (panel_bootstrap.html) for a tap.
    Protected by session cookie (obtained via POST /controlvanne/auth-kiosk/).

    LOCALISATION : controlvanne/viewsets.py
    """
    # Verifier que la session est authentifiee pour le kiosk
    # / Check that the session is authenticated for the kiosk
    if not request.session.get("controlvanne_authenticated"):
        # Fallback : admin tenant connecte via session navigateur
        # / Fallback: tenant admin logged in via browser session
        from django.db import connection
        utilisateur = request.user
        if not (utilisateur and utilisateur.is_authenticated
                and utilisateur.is_tenant_admin(connection.tenant)):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Not authenticated for kiosk.")

    tireuse = get_object_or_404(TireuseBec, uuid=uuid)

    # Toutes les tireuses du tenant (pour le mode multi-tireuses)
    # / All taps for this tenant (for multi-tap mode)
    becs = TireuseBec.objects.filter(enabled=True).order_by("nom_tireuse")

    # Configuration du tenant (nom du lieu pour le header)
    # / Tenant configuration (venue name for the header)
    from BaseBillet.models import Configuration
    config = Configuration.get_solo()

    context = {
        "becs": becs,
        "config": config,
        "slug_focus": str(uuid),
    }
    return render(request, "controlvanne/panel_bootstrap.html", context)
```

- [ ] **Step 2 : Ajouter le path dans urls.py**

Dans `controlvanne/urls.py`, ajouter l'import et le path :

Apres `from controlvanne.viewsets import TireuseViewSet, AuthKioskView` :
```python
from controlvanne.viewsets import TireuseViewSet, AuthKioskView, kiosk_view
```

Dans `urlpatterns`, avant le path router :
```python
    # Kiosk : page web temps reel pour l'ecran du Pi
    # / Kiosk: real-time web page for the Pi screen
    path("kiosk/<uuid:uuid>/", kiosk_view, name="controlvanne-kiosk"),
```

- [ ] **Step 3 : Verifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

---

### Tache 2 : config/settings.py Pi

**Fichiers :**
- Reecrire : `controlvanne/Pi/config/settings.py`

- [ ] **Step 1 : Reecrire settings.py**

```python
"""
Configuration du client Pi — charge les variables depuis .env.
/ Pi client configuration — loads variables from .env.

LOCALISATION : controlvanne/Pi/config/settings.py

Variables recues de discovery (generees par install.sh) :
- SERVER_URL : URL du tenant Django (ex: https://lespass.mondomaine.tld)
- API_KEY : TireuseAPIKey unique (ex: xxxxxxx.yyyyyyy)
- TIREUSE_UUID : UUID de la TireuseBec (ex: abc123-...)

Variables hardware (configurees par install.sh) :
- RFID_TYPE, GPIO_VANNE, GPIO_FLOW_SENSOR, FLOW_CALIBRATION_FACTOR, etc.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Discovery (recus de POST /api/discovery/claim/) ---
SERVER_URL = os.getenv("SERVER_URL", "https://localhost")
API_KEY = os.getenv("API_KEY", "changeme")
TIREUSE_UUID = os.getenv("TIREUSE_UUID", "")

# --- RFID ---
RFID_TYPE = os.getenv("RFID_TYPE", "RC522")
RC522_SPI_DEVICE = int(os.getenv("RC522_SPI_DEVICE", "0"))
RC522_SPI_SPEED = int(os.getenv("RC522_SPI_SPEED", "1000000"))
RFID_SERIAL_PORT = os.getenv("RFID_SERIAL_PORT", "/dev/ttyUSB0")
RFID_BAUDRATE = int(os.getenv("RFID_BAUDRATE", "9600"))

# --- Hardware ---
GPIO_VANNE = int(os.getenv("GPIO_VANNE", "18"))
GPIO_FLOW_SENSOR = int(os.getenv("GPIO_FLOW_SENSOR", "23"))
FLOW_CALIBRATION_FACTOR = float(os.getenv("FLOW_CALIBRATION_FACTOR", "6.5"))
VALVE_ACTIVE_HIGH = os.getenv("VALVE_ACTIVE_HIGH", "False").lower() == "true"

# --- Logs ---
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = Path(os.getenv("LOG_DIR", "~/tibeer/logs")).expanduser()
LOG_DIR.mkdir(parents=True, exist_ok=True)

# --- Systemd ---
SYSTEMD_NOTIFY = os.getenv("SYSTEMD_NOTIFY", "False").lower() == "true"
```

---

### Tache 3 : backend_client.py Pi

**Fichiers :**
- Reecrire : `controlvanne/Pi/network/backend_client.py`

- [ ] **Step 1 : Reecrire backend_client.py**

```python
"""
Client HTTP vers le serveur Django Lespass.
/ HTTP client for the Django Lespass server.

LOCALISATION : controlvanne/Pi/network/backend_client.py

Endpoints appeles :
- POST /controlvanne/api/tireuse/ping/       → test connexion + config tireuse
- POST /controlvanne/api/tireuse/authorize/  → badge NFC → autorisation
- POST /controlvanne/api/tireuse/event/      → evenement temps reel
- POST /controlvanne/auth-kiosk/             → token API → cookie session
"""

import requests
from config.settings import SERVER_URL, API_KEY, TIREUSE_UUID
from utils.logger import logger
from utils.exceptions import BackendError


class BackendClient:
    """
    Client HTTP pour communiquer avec le ViewSet DRF de controlvanne.
    Auth : header Authorization: Api-Key <cle_unique> (TireuseAPIKey via discovery).
    / HTTP client for the controlvanne DRF ViewSet.
    Auth: Authorization: Api-Key <unique_key> (TireuseAPIKey via discovery).
    """

    def __init__(self):
        self.server_url = SERVER_URL.rstrip("/")
        self.tireuse_uuid = TIREUSE_UUID
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {API_KEY}",
        }

    def ping(self):
        """
        POST /controlvanne/api/tireuse/ping/
        Test de connectivite + recuperation de la config tireuse.
        / Connectivity test + tap config retrieval.

        :return: dict avec status, tireuse (nom, prix, calibration, reservoir)
        :raises BackendError: si le serveur est injoignable
        """
        url = f"{self.server_url}/controlvanne/api/tireuse/ping/"
        payload = {"tireuse_uuid": self.tireuse_uuid}

        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=5.0, verify=True)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Ping: HTTP {response.status_code} — {response.text[:200]}")
                return {"status": "error", "message": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"Ping impossible: {e}")
            raise BackendError(f"Serveur injoignable: {e}") from e

    def authorize(self, uid):
        """
        POST /controlvanne/api/tireuse/authorize/
        Badge NFC pose → verification solde wallet → autorisation.
        / NFC badge placed → wallet balance check → authorization.

        :param uid: str — UID hex de la carte NFC (ex: "741ECC2A")
        :return: dict avec authorized, session_id, allowed_ml, solde_centimes, etc.
        :raises BackendError: si le serveur est injoignable
        """
        url = f"{self.server_url}/controlvanne/api/tireuse/authorize/"
        payload = {
            "tireuse_uuid": self.tireuse_uuid,
            "uid": uid,
        }

        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=2.0, verify=True)
            data = response.json()

            if response.status_code == 200:
                return data
            else:
                # 403, 404, etc. — le serveur a repondu, on retourne les infos
                # / Server responded, return the info
                return data

        except Exception as e:
            logger.error(f"Authorize impossible: {e}")
            raise BackendError(f"Erreur reseau authorize: {e}") from e

    def send_event(self, event_type, uid, volume_ml=0):
        """
        POST /controlvanne/api/tireuse/event/
        Envoie un evenement temps reel (pour_start, pour_update, pour_end, card_removed).
        / Sends a real-time event.

        :param event_type: str — "pour_start", "pour_update", "pour_end", "card_removed"
        :param uid: str — UID hex de la carte NFC
        :param volume_ml: float — volume cumule depuis le debut de la session (ml)
        :return: dict avec status, event_type, session_id, volume_ml (+ montant_centimes pour pour_end)
        """
        url = f"{self.server_url}/controlvanne/api/tireuse/event/"
        payload = {
            "tireuse_uuid": self.tireuse_uuid,
            "uid": uid,
            "event_type": event_type,
            "volume_ml": str(round(volume_ml, 2)),
        }

        # Timeout court pour pour_update (non bloquant), plus long pour les autres
        # / Short timeout for pour_update (non-blocking), longer for others
        timeout = 1.0 if event_type == "pour_update" else 3.0

        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=timeout, verify=True)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Event {event_type}: HTTP {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Event {event_type} impossible: {e}")
            raise BackendError(f"Erreur reseau event: {e}") from e

    def auth_kiosk(self):
        """
        POST /controlvanne/auth-kiosk/
        Obtient un cookie session Django pour le kiosk Chromium.
        / Gets a Django session cookie for the Chromium kiosk.

        :return: str — session_key
        :raises BackendError: si le serveur est injoignable
        """
        url = f"{self.server_url}/controlvanne/auth-kiosk/"

        try:
            response = requests.post(url, json={}, headers=self.headers, timeout=5.0, verify=True)
            if response.status_code == 200:
                data = response.json()
                session_key = data.get("session_key", "")
                logger.info(f"Auth kiosk OK — session_key obtenue")
                return session_key
            else:
                logger.error(f"Auth kiosk: HTTP {response.status_code}")
                raise BackendError(f"Auth kiosk echoue: HTTP {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Auth kiosk impossible: {e}")
            raise BackendError(f"Auth kiosk impossible: {e}") from e
```

---

### Tache 4 : tibeer_controller.py Pi

**Fichiers :**
- Reecrire : `controlvanne/Pi/controllers/tibeer_controller.py`

- [ ] **Step 1 : Reecrire le controleur**

```python
"""
Controleur principal de la tireuse connectee.
/ Main controller for the connected beer tap.

LOCALISATION : controlvanne/Pi/controllers/tibeer_controller.py

Machine a etats :
1. Attente badge → rfid.read_uid()
2. Nouvelle carte → client.authorize(uid) → ouvrir vanne si autorise
3. Service en cours → client.send_event("pour_update") chaque seconde
4. Volume max atteint → fermer vanne, client.send_event("pour_end")
5. Carte retiree → fermer vanne, client.send_event("pour_end") puis "card_removed"
"""

import time
from hardware.rfid_reader import RFIDReader
from hardware.valve import Valve
from hardware.flow_meter import FlowMeter
from network.backend_client import BackendClient
from utils.logger import logger
from utils.exceptions import BackendError

# Anti-rebond : delai avant de considerer que la carte est partie (secondes)
# / Anti-bounce: delay before considering the card is gone (seconds)
CARD_GRACE_PERIOD_S = 1.0

# Frequence d'envoi des events pour_update (secondes)
# / Frequency of pour_update events (seconds)
UPDATE_INTERVAL_S = 1.0


class TibeerController:
    """
    Boucle principale : lecture RFID + controle vanne + communication serveur.
    / Main loop: RFID read + valve control + server communication.
    """

    def __init__(self, rfid, valve, flow_meter, client):
        self.rfid = rfid
        self.valve = valve
        self.flow_meter = flow_meter
        self.client = client

        # Etat du systeme / System state
        self.current_uid = None
        self.last_seen_ts = 0
        self.session_id = None
        self.is_serving = False
        self.session_start_vol = 0.0
        self.allowed_ml = 0.0
        self.last_update_ts = 0
        self.running = True

    def run(self):
        """Boucle principale — tourne toutes les 100ms.
        / Main loop — runs every 100ms."""
        logger.info("Controleur demarre. En attente de badge...")

        try:
            while self.running:
                uid = self.rfid.read_uid()
                now = time.time()

                # Mise a jour du debitmetre a chaque iteration
                # / Update flow meter every iteration
                self.flow_meter.update()

                if uid:
                    # --- Carte presente ---
                    self.last_seen_ts = now

                    if uid != self.current_uid:
                        # Nouvelle carte (ou retour apres micro-coupure)
                        # / New card (or return after micro-dropout)
                        logger.info(f"Nouveau badge detecte: {uid}")
                        if self.is_serving:
                            self._end_session_actions()
                        self.current_uid = uid
                        self._handle_new_session(uid)

                    elif self.is_serving:
                        # Meme carte, service en cours
                        # / Same card, serving
                        self._handle_pouring_loop(now)
                else:
                    # --- Pas de carte ---
                    if self.current_uid is not None:
                        if (now - self.last_seen_ts) > CARD_GRACE_PERIOD_S:
                            logger.info(f"Badge {self.current_uid} retire.")
                            self._handle_card_removal()

                time.sleep(0.1)

        except KeyboardInterrupt:
            logger.info("Arret manuel.")
        finally:
            self.cleanup()

    def _handle_new_session(self, uid):
        """Badge detecte → demande autorisation au serveur.
        / Badge detected → request authorization from server."""
        try:
            auth = self.client.authorize(uid)
        except BackendError as e:
            logger.error(f"Erreur backend authorize: {e}")
            self.is_serving = False
            self.session_id = None
            return

        if auth.get("authorized") is True:
            # --- Autorise ---
            self.session_id = auth.get("session_id")
            self.allowed_ml = float(auth.get("allowed_ml", 0))

            # Reset debitmetre (snapshot du volume actuel)
            # / Reset flow meter (snapshot of current volume)
            self.session_start_vol = self.flow_meter.volume_l() * 1000.0

            # Ouvrir la vanne / Open valve
            self.valve.open()
            self.is_serving = True

            solde = auth.get("solde_centimes", 0)
            logger.info(
                f"Autorise. Session {self.session_id}. "
                f"Solde {solde}cts. Max {self.allowed_ml:.0f}ml. Vanne ouverte."
            )

            # Informer le serveur (pour le push WebSocket vers le kiosk)
            # / Notify server (for WebSocket push to kiosk)
            self.client.send_event("pour_start", uid, 0)
            self.last_update_ts = time.time()

        else:
            # --- Refuse ---
            message = auth.get("message", "Non autorise")
            logger.warning(f"Badge {uid} refuse: {message}")
            self.is_serving = False
            self.session_id = None

    def _handle_pouring_loop(self, now):
        """Pendant le service : envoie les mises a jour de volume.
        / During service: send volume updates."""
        if (now - self.last_update_ts) < UPDATE_INTERVAL_S:
            return

        served_ml = (self.flow_meter.volume_l() * 1000.0) - self.session_start_vol

        # Verifier si le volume max est atteint / Check if max volume reached
        if self.allowed_ml > 0 and served_ml >= self.allowed_ml:
            logger.warning(f"Volume max atteint ({self.allowed_ml:.0f}ml). Fermeture vanne.")
            self.valve.close()
            self.client.send_event("pour_end", self.current_uid, served_ml)
            self.is_serving = False
            return

        # Envoyer pour_update (non bloquant en cas d'erreur)
        # / Send pour_update (non-blocking on error)
        try:
            self.client.send_event("pour_update", self.current_uid, served_ml)
        except BackendError as e:
            logger.warning(f"pour_update echoue (on continue): {e}")

        self.last_update_ts = now

    def _handle_card_removal(self):
        """Carte retiree → fermer la vanne, envoyer les events de fin.
        / Card removed → close valve, send end events."""
        if self.is_serving:
            self._end_session_actions()

        # Envoyer card_removed (declenche le popup kiosk via WebSocket)
        # / Send card_removed (triggers kiosk popup via WebSocket)
        try:
            self.client.send_event("card_removed", self.current_uid, 0)
        except BackendError:
            pass

        self.current_uid = None
        self.session_id = None
        self.allowed_ml = 0.0

    def _end_session_actions(self):
        """Ferme la vanne et envoie le bilan final.
        / Closes the valve and sends the final report."""
        self.valve.close()
        logger.info("Vanne fermee (fin session).")

        if self.current_uid:
            served_ml = (self.flow_meter.volume_l() * 1000.0) - self.session_start_vol
            logger.info(f"Volume final: {served_ml:.1f} ml")

            try:
                result = self.client.send_event("pour_end", self.current_uid, served_ml)
                if result:
                    montant = result.get("montant_centimes", 0)
                    tx_id = result.get("transaction_id", "?")
                    logger.info(f"Facture: {montant}cts, transaction #{tx_id}")
            except BackendError as e:
                logger.error(f"pour_end echoue: {e}")

        self.is_serving = False

    def cleanup(self):
        """Nettoyage des ressources GPIO.
        / Cleanup GPIO resources."""
        logger.info("Nettoyage des ressources...")
        try:
            self.valve.close()
        except Exception:
            pass
```

---

### Tache 5 : main.py Pi

**Fichiers :**
- Reecrire : `controlvanne/Pi/main.py`

- [ ] **Step 1 : Reecrire main.py**

```python
#!/usr/bin/env python3
"""
Point d'entree du client Pi tireuse connectee.
/ Entry point for the connected tap Pi client.

LOCALISATION : controlvanne/Pi/main.py

Demarrage :
1. Init hardware (RFID, vanne, debitmetre)
2. Ping serveur (verif connectivite + config tireuse)
3. Auth kiosk (cookie session pour Chromium)
4. Lancer Chromium kiosk en arriere-plan
5. Boucle controleur (lecture RFID + controle vanne + API)
"""

import os
import sys
import subprocess
import time

from dotenv import load_dotenv
load_dotenv()

from utils.logger import logger
from config.settings import SERVER_URL, TIREUSE_UUID, SYSTEMD_NOTIFY
from hardware.rfid_reader import RFIDReader
from hardware.valve import Valve
from hardware.flow_meter import FlowMeter
from network.backend_client import BackendClient
from controllers.tibeer_controller import TibeerController


def launch_chromium_kiosk(kiosk_url):
    """
    Lance Chromium en mode kiosk sur l'ecran HDMI du Pi.
    / Launches Chromium in kiosk mode on the Pi's HDMI screen.

    Le cookie session est gere par Chromium — le Set-Cookie de auth-kiosk
    est stocke automatiquement pour le domaine du serveur.
    / The session cookie is managed by Chromium — the Set-Cookie from auth-kiosk
    is stored automatically for the server domain.
    """
    try:
        subprocess.Popen(
            [
                "chromium-browser",
                "--kiosk",
                "--noerrdialogs",
                "--disable-infobars",
                "--disable-translate",
                "--disable-features=TranslateUI",
                "--check-for-update-interval=31536000",
                f"--app={kiosk_url}",
            ],
            env={**os.environ, "DISPLAY": ":0"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info(f"Chromium kiosk lance sur {kiosk_url}")
    except FileNotFoundError:
        logger.warning("Chromium non trouve — kiosk non demarre (mode headless?)")
    except Exception as e:
        logger.warning(f"Erreur lancement Chromium: {e}")


def main():
    """Point d'entree du programme.
    / Program entry point."""
    logger.info("Demarrage TiBeer...")

    # 1. Init hardware / Init hardware
    logger.info("Init hardware...")
    rfid = RFIDReader()
    valve = Valve()
    flow_meter = FlowMeter()
    client = BackendClient()

    # 2. Ping serveur / Ping server
    logger.info("Ping serveur...")
    try:
        ping_result = client.ping()
        if ping_result.get("status") == "pong":
            tireuse_config = ping_result.get("tireuse", {})
            nom = tireuse_config.get("nom", "?")
            logger.info(f"Serveur OK. Tireuse: {nom}")

            # Mettre a jour le facteur de calibration depuis la config serveur
            # / Update calibration factor from server config
            calibration = tireuse_config.get("calibration_factor")
            if calibration:
                flow_meter.set_calibration_factor(calibration)
                logger.info(f"Facteur calibration mis a jour: {calibration}")
        else:
            logger.warning(f"Ping: {ping_result.get('message', 'erreur')}")
    except Exception as e:
        logger.warning(f"Ping echoue (on continue): {e}")

    # 3. Auth kiosk / Auth kiosk
    logger.info("Auth kiosk...")
    try:
        session_key = client.auth_kiosk()
        logger.info("Session kiosk obtenue.")
    except Exception as e:
        logger.warning(f"Auth kiosk echoue (kiosk indisponible): {e}")
        session_key = None

    # 4. Lancer Chromium kiosk / Launch Chromium kiosk
    kiosk_url = f"{SERVER_URL}/controlvanne/kiosk/{TIREUSE_UUID}/"
    launch_chromium_kiosk(kiosk_url)

    # 5. Notification systemd / Systemd notification
    if SYSTEMD_NOTIFY:
        try:
            import systemd.daemon
            systemd.daemon.notify("READY=1")
        except ImportError:
            logger.warning("Module python-systemd manquant.")

    # 6. Boucle controleur / Controller loop
    controller = TibeerController(rfid, valve, flow_meter, client)
    try:
        controller.run()
    except KeyboardInterrupt:
        logger.info("Arret signal (CTRL+C).")
    except Exception as e:
        logger.error(f"Erreur fatale: {e}", exc_info=True)
        sys.exit(1)
    finally:
        controller.cleanup()
        logger.info("Processus termine.")


if __name__ == "__main__":
    main()
```

---

### Tache 6 : .env.example + requirements.txt

**Fichiers :**
- Reecrire : `controlvanne/Pi/.env.example`
- Creer : `controlvanne/Pi/requirements.txt`
- Supprimer : `controlvanne/Pi/requierements.txt`

- [ ] **Step 1 : Reecrire .env.example**

```env
# --- Genere par install.sh via discovery (PIN → claim) ---
SERVER_URL=https://lespass.mondomaine.tld
API_KEY=xxxxxxx.yyyyyyy
TIREUSE_UUID=abc123-def456-...

# --- Lecteur RFID ---
RFID_TYPE=RC522
# RFID_TYPE=VMA405
# RFID_TYPE=ACR122U
# Pour VMA405 uniquement :
# RFID_SERIAL_PORT=/dev/ttyUSB0
# RFID_BAUDRATE=9600
# Pour RC522 uniquement :
# RC522_SPI_DEVICE=0
# RC522_SPI_SPEED=1000000

# --- Vanne ---
GPIO_VANNE=18
VALVE_ACTIVE_HIGH=False

# --- Debitmetre ---
GPIO_FLOW_SENSOR=23
FLOW_CALIBRATION_FACTOR=6.5

# --- Systemd ---
SYSTEMD_NOTIFY=True
```

- [ ] **Step 2 : Creer requirements.txt**

```
pyserial>=3.5
requests>=2.31.0
python-dotenv>=1.0.0
systemd-python>=234
mfrc522-python>=0.0.7
pigpio>=1.78
```

Note : `flask` supprime, `pyscard` installe conditionnellement par install.sh.

- [ ] **Step 3 : Supprimer l'ancien fichier**

```bash
rm /home/jonas/TiBillet/dev/Lespass/controlvanne/Pi/requierements.txt
```

---

### Tache 7 : install.sh

**Fichiers :**
- Reecrire : `controlvanne/Pi/install.sh`

- [ ] **Step 1 : Reecrire install.sh**

Le script garde la meme structure (setup OS, Python, systemd, kiosk) mais remplace l'auth par discovery.

Changements cles :
1. Demande URL publique TiBillet (au lieu de host:port)
2. Demande PIN 6 chiffres (au lieu de cle API partagee)
3. Appelle `POST {url_publique}/api/discovery/claim/` avec le PIN
4. Recoit `server_url`, `api_key`, `tireuse_uuid`
5. Genere `.env` avec le nouveau format
6. Kiosk Chromium pointe sur `{server_url}/controlvanne/kiosk/{tireuse_uuid}/`
7. Plus de Flask dans le service tibeer

Le script complet est trop long pour etre inclus integralement ici. Les sections a modifier :

**Section "Questions utilisateur"** — remplacer :
```bash
# Ancien
read -p "Adresse du serveur Django (ex: http://192.168.1.10:8000) : " DJANGO_URL
read -p "Cle API partagee : " API_KEY_INPUT
```
par :
```bash
# Nouveau
read -p "URL publique TiBillet (ex: https://tibillet.mondomaine.tld) : " PUBLIC_URL
read -p "PIN 6 chiffres (affiche dans l'admin Unfold) : " PIN_CODE

# Appel discovery
echo "Appairage en cours..."
CLAIM_RESPONSE=$(curl -s -X POST "${PUBLIC_URL}/api/discovery/claim/" \
  -H "Content-Type: application/json" \
  -d "{\"pin_code\": \"${PIN_CODE}\"}")

SERVER_URL=$(echo "$CLAIM_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['server_url'])")
API_KEY=$(echo "$CLAIM_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['api_key'])")
TIREUSE_UUID=$(echo "$CLAIM_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['tireuse_uuid'])")

if [ -z "$SERVER_URL" ] || [ -z "$API_KEY" ]; then
  echo "ERREUR: Appairage echoue. Verifiez le PIN et l'URL."
  exit 1
fi
echo "Appairage reussi ! Tenant: $SERVER_URL, Tireuse: $TIREUSE_UUID"
```

**Section "Generation .env"** — utiliser le nouveau format (voir tache 6).

**Section "Service tibeer"** — supprimer la reference Flask.

**Section "Kiosk"** — remplacer `localhost:5000` par `${SERVER_URL}/controlvanne/kiosk/${TIREUSE_UUID}/`.

---

### Tache 8 : Suppression code legacy

**Fichiers :**
- Supprimer : `controlvanne/Pi/ui/` (dossier entier)
- Supprimer : `controlvanne/Pi/controlvanne/` (copie locale Django)

- [ ] **Step 1 : Supprimer les dossiers**

```bash
rm -rf /home/jonas/TiBillet/dev/Lespass/controlvanne/Pi/ui
rm -rf /home/jonas/TiBillet/dev/Lespass/controlvanne/Pi/controlvanne
```

- [ ] **Step 2 : Verifier qu'aucun import ne reference les fichiers supprimes**

```bash
grep -rn "from ui\.\|import ui\.\|from controlvanne\." /home/jonas/TiBillet/dev/Lespass/controlvanne/Pi/ --include="*.py" | grep -v "__pycache__"
```

Attendu : aucun resultat.

---

### Tache 9 : Tests Django (vue kiosk)

**Fichiers :**
- Modifier : `tests/pytest/test_controlvanne_api.py`

- [ ] **Step 1 : Ajouter des tests pour la vue kiosk**

Ajouter a la fin de `test_controlvanne_api.py` :

```python
# ──────────────────────────────────────────────────────────────────────
# Tests : Vue kiosk
# ──────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestKioskView:
    """Tests de la vue kiosk (GET /controlvanne/kiosk/<uuid>/).
    / Tests for the kiosk view."""

    def test_14_kiosk_sans_auth(self, tireuse_client, test_tireuse):
        """Kiosk sans session → 403.
        / Kiosk without session → 403."""
        response = tireuse_client.get(
            f"/controlvanne/kiosk/{test_tireuse.uuid}/",
        )
        assert response.status_code == 403

    def test_15_kiosk_avec_admin_session(self, admin_client, test_tireuse):
        """Kiosk avec admin session → 200.
        / Kiosk with admin session → 200."""
        response = admin_client.get(
            f"/controlvanne/kiosk/{test_tireuse.uuid}/",
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert 'data-testid="kiosk-cards-grid"' in content

    def test_16_kiosk_uuid_inexistant(self, admin_client):
        """Kiosk avec UUID inexistant → 404.
        / Kiosk with nonexistent UUID → 404."""
        import uuid as uuid_module
        response = admin_client.get(
            f"/controlvanne/kiosk/{uuid_module.uuid4()}/",
        )
        assert response.status_code == 404

    def test_17_kiosk_avec_session_auth_kiosk(self, tireuse_client, tireuse_headers, test_tireuse):
        """Auth kiosk puis kiosk → 200.
        / Auth kiosk then kiosk → 200."""
        # D'abord auth-kiosk pour obtenir le cookie
        # / First auth-kiosk to get the cookie
        tireuse_client.post(
            "/controlvanne/auth-kiosk/",
            content_type="application/json",
            data="{}",
            **tireuse_headers,
        )
        # Puis kiosk (meme client = meme cookie)
        # / Then kiosk (same client = same cookie)
        response = tireuse_client.get(
            f"/controlvanne/kiosk/{test_tireuse.uuid}/",
        )
        assert response.status_code == 200
```

- [ ] **Step 2 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_controlvanne_api.py -v
```

---

### Tache 10 : Verification finale

- [ ] **Step 1 : Django check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Step 2 : Verifier les URLs Django**

```bash
docker exec lespass_django poetry run python -c "
from django.urls import reverse
print(reverse('controlvanne-kiosk', kwargs={'uuid': '00000000-0000-0000-0000-000000000000'}))
print('OK')
"
```

- [ ] **Step 3 : Non-regression complete**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

- [ ] **Step 4 : Verifier la structure Pi**

```bash
ls -la /home/jonas/TiBillet/dev/Lespass/controlvanne/Pi/
ls /home/jonas/TiBillet/dev/Lespass/controlvanne/Pi/network/
ls /home/jonas/TiBillet/dev/Lespass/controlvanne/Pi/controllers/
ls /home/jonas/TiBillet/dev/Lespass/controlvanne/Pi/hardware/
ls /home/jonas/TiBillet/dev/Lespass/controlvanne/Pi/config/
```

---

## Resume des fichiers

| Fichier | Changement |
|---------|------------|
| **Django** | |
| `controlvanne/viewsets.py` | +`kiosk_view()` |
| `controlvanne/urls.py` | +path kiosk |
| `tests/pytest/test_controlvanne_api.py` | +4 tests kiosk |
| **Pi** | |
| `controlvanne/Pi/network/backend_client.py` | REECRIT — 4 methodes DRF |
| `controlvanne/Pi/controllers/tibeer_controller.py` | REECRIT — allowed_ml, plus de Flask |
| `controlvanne/Pi/main.py` | REECRIT — ping, auth-kiosk, Chromium, controleur |
| `controlvanne/Pi/config/settings.py` | REECRIT — SERVER_URL, API_KEY, TIREUSE_UUID |
| `controlvanne/Pi/.env.example` | REECRIT — nouveau format discovery |
| `controlvanne/Pi/requirements.txt` | CREE (Flask retire) |
| `controlvanne/Pi/install.sh` | MODIFIE — discovery PIN |
| `controlvanne/Pi/requierements.txt` | SUPPRIME |
| `controlvanne/Pi/ui/` | SUPPRIME |
| `controlvanne/Pi/controlvanne/` | SUPPRIME |
