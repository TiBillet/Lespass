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
CARD_GRACE_PERIOD_S = 1.5

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
        if self.session_id is not None:
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
