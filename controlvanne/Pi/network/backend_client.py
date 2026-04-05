import requests
import json
import socket
from config.settings import BACKEND_HOST, BACKEND_PORT, BACKEND_API_KEY, NOM_TIREUSE, TIREUSE_BEC
from utils.logger import logger
from utils.exceptions import BackendError

# --- CONFIGURATION ---
API_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
TIMEOUT = 2.0


class BackendClient:
    def __init__(self, tireuse_id=TIREUSE_BEC):
        self.headers = {
            "Content-Type": "application/json",
            "X-API-Key": BACKEND_API_KEY,
        }
        self.base_url = API_URL.rstrip("/") + "/api/rfid"
        self.tireuse_id = tireuse_id

    def register(self) -> dict:
        """
        Auto-enregistre cette tireuse sur Django au démarrage.
        Django crée la TireuseBec si elle n'existe pas (enabled=False).
        Nécessite que 'allow_self_register' soit activé dans l'admin Django.
        Silencieux si le serveur refuse (mode désactivé) : on continue quand même.
        """
        url = f"{self.base_url}/register/"
        payload = {
            "uuid": self.tireuse_id,
            "nom_tireuse": NOM_TIREUSE,
            "hostname": socket.gethostname(),
        }
        try:
            r = requests.post(url, json=payload, headers=self.headers, timeout=5.0)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 403:
                # Mode désactivé côté Django — pas bloquant
                logger.info("Auto-enregistrement désactivé sur le serveur (normal en prod).")
                return {"error": "disabled"}
            else:
                logger.warning(f"Réponse inattendue lors du register : {r.status_code}")
                return {"error": f"HTTP {r.status_code}"}
        except Exception as e:
            # Erreur réseau non bloquante — le Pi peut fonctionner s'il est déjà connu
            logger.warning(f"Auto-enregistrement impossible (réseau?) : {e}")
            return {"error": str(e)}

    def authorize(self, uid: str) -> dict:
        """
        Interroge Django.
        Renvoie un dictionnaire avec 'authorized': True/False et le reste des infos.
        """
        url = f"{self.base_url}/authorize"
        payload = {"uid": uid, "tireuse_bec": self.tireuse_id}

        try:
            logger.debug(f"Demande autorisation pour {uid}...")
            r = requests.post(url, json=payload, headers=self.headers, timeout=TIMEOUT)

            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict):
                    # Si le serveur dit OK ou renvoie une session
                    if "session_id" in data or data.get("authorized") is True:
                        data["authorized"] = True
                        return data
                return {"authorized": False, "error": "Pas de session_id"}

            elif r.status_code == 403:
                # On retourne juste l'info, c'est le Controller qui décidera de l'affichage
                return {
                    "authorized": False,
                    "error": "Badge refusé ou solde insuffisant",
                }

            else:
                return {"authorized": False, "error": f"Erreur HTTP {r.status_code}"}

        except Exception as e:
            logger.error(f"Erreur réseau authorize: {e}")
            raise BackendError(
                f"Impossible de joindre le backend pour l'autorisation : {e}"
            ) from e

    def send_event(self, event_type, uid, session_id=None, data=None):
        """
        Envoie un événement (start, update, end, auth_fail).
        Retourne la réponse du serveur (dict) ou None en cas d'erreur.
        """
        # 1. Préparation des données data/inner
        inner_data = {}

        if session_id:
            inner_data["session_id"] = session_id

        if data is not None:
            if isinstance(data, dict):
                inner_data.update(data)
            else:
                inner_data["volume_ml"] = data

        # 2. Payload complet
        payload = {
            "event_type": event_type,
            "uid": uid,
            "tireuse_bec": self.tireuse_id,
            "data": inner_data,
        }

        try:
            # Timeout court pour le débit, un peu plus long pour les autres events
            to = 1.0 if event_type == "pour_update" else 3.0

            url = f"{self.base_url}/event/"
            res = requests.post(url, json=payload, headers=self.headers, timeout=to)

            if res.status_code == 200:
                return res.json()
            else:
                logger.error(f"Erreur API Event ({res.status_code}): {res.text}")
                return None

        except Exception as e:
            logger.error(f"Echec envoi event {event_type}: {e}")
            raise BackendError(
                f"Impossible d'envoyer l'event '{event_type}' : {e}"
            ) from e
