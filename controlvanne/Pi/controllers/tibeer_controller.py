import time
import sys
import threading
import os
from hardware.rfid_reader import RFIDReader
from hardware.valve import Valve
from hardware.flow_meter import FlowMeter
from network.backend_client import BackendClient
from ui.ui_server import update_display
from utils.logger import logger
from utils.exceptions import BackendError, RFIDReadError

# Paramètres
CARD_GRACE_PERIOD_S = (
    1.0  # Temps avant de considérer que la carte est partie (Anti-rebond)
)
UPDATE_INTERVAL_S = 1.0  # Fréquence d'envoi des infos de débit


class TibeerController:
    def __init__(self):
        logger.info("Initialisation TiBeer Controller (Mode Session Django)...")
        self.rfid = RFIDReader()
        self.valve = Valve()
        self.flow_meter = FlowMeter()
        self.client = BackendClient()
        # État du système
        self.current_uid = None
        self.last_seen_ts = 0
        self.session_id = None
        self.is_serving = False
        self.session_start_vol = 0.0
        self.last_update_ts = 0

        self.running = True

    def run(self):
        logger.info("Service TiBeer démarré. En attente de badge...")
        update_display("Scannez votre badge", color="blue")

        try:
            while self.running:
                uid = self.rfid.read_uid()
                now = time.time()

                # Mise à jour du débitmètre à chaque itération pour avoir
                # current_flow_rate et volume_total_ml à jour en continu
                self.flow_meter.update()

                if uid:
                    # --- UNE CARTE EST PRÉSENTE ---
                    self.last_seen_ts = now

                    # NOUVELLE CARTE (ou retour après micro-coupure)
                    if uid != self.current_uid:
                        logger.info(f"Nouveau badge détecté: {uid}")
                        # Sécurité: fermer l'ancienne session si elle existait
                        if self.is_serving:
                            self._end_session_actions()

                        self.current_uid = uid
                        self._handle_new_session(uid)

                    # MÊME CARTE (Boucle de service)
                    elif self.is_serving:
                        self._handle_pouring_loop(now)

                else:
                    # --- PAS DE CARTE ---
                    if self.current_uid is not None:
                        # Anti-rebond (Grace period)
                        if (now - self.last_seen_ts) > CARD_GRACE_PERIOD_S:
                            logger.info(f"Badge {self.current_uid} retiré.")
                            self._handle_card_removal()

                time.sleep(0.1)

        except KeyboardInterrupt:
            logger.info("Arrêt manuel.")
        finally:
            self.cleanup()

    def _handle_new_session(self, uid):
        """Vérifie le badge et décide de l'ouvrir ou de rejeter"""
        # 1. Demande au backend
        try:
            auth_response = self.client.authorize(uid)
        except BackendError as e:
            logger.error(f"Erreur backend lors de l'autorisation : {e}")
            update_display("Erreur réseau", color="red")
            self.is_serving = False
            self.session_id = None
            return

        if auth_response.get("authorized") is True:
            # --- CAS 1 : AUTORISÉ (VERT) ---
            self.session_id = auth_response.get("session_id")
            balance = auth_response.get("balance", "--")

            # Mise à jour du facteur de calibration depuis la config Django
            flow_factor = auth_response.get("flow_calibration_factor")
            if flow_factor is not None:
                self.flow_meter.set_calibration_factor(flow_factor)

            # Reset débitmètre (snapshot)
            self.session_start_vol = self.flow_meter.volume_l() * 1000.0

            # Action Physique
            self.valve.open()
            self.is_serving = True

            logger.info(f"Autorisation OK. Session {self.session_id}. Vanne ouverte.")

            # Affichage VERT (kiosk Flask local)
            update_display(
                f"Servez-vous ! Solde: {balance}", color="green", balance=balance
            )

            # Affichage VERT (dashboard Django WebSocket)
            self.client.send_event("pour_start", self.current_uid, self.session_id)
            self.last_update_ts = time.time()

        else:
            # --- CAS 2 : REFUSÉ (ROUGE) ---
            error_msg = auth_response.get("error", "Non autorisé")
            logger.warning(f"Badge {uid} refusé: {error_msg}")

            self.is_serving = False
            self.session_id = None

            # Affichage ROUGE (kiosk Flask local)
            update_display(error_msg, color="red")

            self.client.send_event(
                "auth_fail", self.current_uid, None, {"message": error_msg}
            )

    def _handle_pouring_loop(self, now):
        # Gestion du débit pendant le service
        if (now - self.last_update_ts) > UPDATE_INTERVAL_S:
            current_total_vol = self.flow_meter.volume_l() * 1000.0
            served_vol = current_total_vol - self.session_start_vol
            flow_rate_cl = self.flow_meter.get_flow_rate_cl()

            # Envoyer l'event et vérifier la réponse
            try:
                response = self.client.send_event(
                    "pour_update",
                    self.current_uid,
                    self.session_id,
                    {"volume_ml": served_vol, "debit_cl_min": flow_rate_cl},
                )
            except BackendError as e:
                logger.warning(
                    f"Erreur backend lors de pour_update (on continue) : {e}"
                )
                self.last_update_ts = now
                return

            # Vérifier si fermeture forcée demandée par le serveur
            if response and response.get("force_close"):
                logger.warning("⚠️ SOLDE ÉPUISÉ - Fermeture vanne")
                self._end_session_actions()
                # Envoyer l'event de fin
                self.client.send_event(
                    "pour_end",
                    self.current_uid,
                    self.session_id,
                    {"volume_ml": served_vol, "debit_cl_min": flow_rate_cl},
                )
                self.is_serving = False
                return

            self.last_update_ts = now

    def _handle_card_removal(self):
        """Gère le retrait du badge"""
        if self.is_serving:
            # Fin de service normale (BLEU)
            self._end_session_actions()

        # Envoyer card_removed pour déclencher le popup (toujours)
        self.client.send_event("card_removed", self.current_uid, None)

        # Retour en attente (kiosk Flask local)
        update_display("Scannez votre badge", color="blue")

        self.current_uid = None
        self.session_id = None

    def _end_session_actions(self):
        """Ferme la vanne et envoie le bilan"""
        self.valve.close()
        logger.info("Vanne fermée (Fin session).")

        if self.current_uid and self.session_id:
            final_total_vol = self.flow_meter.volume_l() * 1000.0
            served_vol = final_total_vol - self.session_start_vol

            logger.info(f"Envoi rapport fin. Volume: {served_vol:.1f} ml")
            self.client.send_event(
                "pour_end",
                self.current_uid,
                self.session_id,
                {"volume_ml": served_vol, "debit_cl_min": 0.0},
            )

        self.is_serving = False

    def cleanup(self):
        logger.info("Nettoyage des ressources...")
        try:
            self.valve.close()
        except:
            pass
