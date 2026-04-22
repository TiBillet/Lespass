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
from config.settings import SERVER_URL, API_KEY, TIREUSE_UUID, SSL_VERIFY
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
            response = requests.post(url, json=payload, headers=self.headers, timeout=5.0, verify=SSL_VERIFY)
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
            response = requests.post(url, json=payload, headers=self.headers, timeout=2.0, verify=SSL_VERIFY)
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
            response = requests.post(url, json=payload, headers=self.headers, timeout=timeout, verify=SSL_VERIFY)
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
        Obtient un token à usage unique pour l'auth kiosk.
        Le Pi ouvre Chromium sur /controlvanne/kiosk-token/<token>/?next=<kiosk_url>
        Django pose le cookie de session via HTTP et redirige vers le kiosk.
        / Gets a one-time token for kiosk auth.
        The Pi opens Chromium on /controlvanne/kiosk-token/<token>/?next=<kiosk_url>
        Django sets the session cookie via HTTP and redirects to the kiosk.

        :return: tuple (session_key, kiosk_token)
        :raises BackendError: si le serveur est injoignable
        """
        url = f"{self.server_url}/controlvanne/auth-kiosk/"

        try:
            response = requests.post(url, json={}, headers=self.headers, timeout=5.0, verify=SSL_VERIFY)
            if response.status_code == 200:
                data = response.json()
                session_key = data.get("session_key", "")
                kiosk_token = data.get("kiosk_token", "")
                logger.info(f"Auth kiosk OK — token obtenu")
                return session_key, kiosk_token
            else:
                logger.error(f"Auth kiosk: HTTP {response.status_code}")
                raise BackendError(f"Auth kiosk echoue: HTTP {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Auth kiosk impossible: {e}")
            raise BackendError(f"Auth kiosk impossible: {e}") from e
