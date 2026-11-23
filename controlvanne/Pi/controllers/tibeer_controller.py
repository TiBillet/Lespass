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

# Le lecteur NFC, la vanne, le débitmètre et le client du serveur ne sont PAS
# importés ici : main.py les crée et les passe au constructeur. Les importer
# chargerait pigpio et mfrc522, et le contrôleur ne pourrait plus être testé
# sans Raspberry Pi (voir tests/pytest/test_controlvanne_pi_controleur.py).
# / Hardware and client are NOT imported here: main.py builds them and passes
# them to the constructor. Importing them would load pigpio and mfrc522.
from utils.logger import logger
from utils.exceptions import BackendError

# Anti-rebond : delai avant de considerer que la carte est partie (secondes)
# / Anti-bounce: delay before considering the card is gone (seconds)
CARD_GRACE_PERIOD_S = 3.0

# Frequence d'envoi des events pour_update (secondes)
# / Frequency of pour_update events (seconds)
UPDATE_INTERVAL_S = 1.0

# Pause avant un nouvel essai de authorize() apres une erreur reseau (secondes).
# 2,5 s => au plus ~21 essais/min, sous le plafond serveur de 30 authorize/min
# par cle (AuthorizeTireuseThrottle) : au-dela, le serveur repondrait 429 et
# la carte resterait bloquee.
# / Pause before retrying authorize() after a network error (seconds).
# 2.5 s => at most ~21 tries/min, below the server cap of 30 authorize/min.
AUTHORIZE_RETRY_DELAY_S = 2.5


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

        # Vrai quand le dernier authorize a échoué sur une erreur réseau.
        # La carte reste la carte courante (current_uid) : son retrait envoie
        # donc bien card_removed. Tant que c'est vrai, la boucle relance authorize.
        # / True when the last authorize failed on a network error: the loop retries it.
        self.authorize_a_refaire = False

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

                # Plafond contrôlé à CHAQUE tour (toutes les 100 ms), carte présente
                # ou pendant la période de grâce. Le débordement au-delà du plafond
                # n'est pas facturé : c'est une perte pour le lieu.
                # / Cap checked on EVERY turn, card present or during the grace period.
                # Overflow beyond the cap is not billed: a loss for the venue.
                if self.is_serving:
                    self._fermer_si_plafond_atteint()

                if uid:
                    # --- Carte presente ---
                    self.last_seen_ts = now

                    if uid != self.current_uid or self.authorize_a_refaire:
                        # Nouvelle carte, retour après une micro-coupure,
                        # ou nouvel essai d'un authorize en erreur réseau.
                        # / New card, return after a micro-dropout, or authorize retry.
                        logger.info(f"Nouveau badge detecte: {uid}")
                        if self.is_serving:
                            self._end_session_actions()
                        self.current_uid = uid
                        self._handle_new_session(uid)

                        # Remettre le timer a jour apres authorize() + send_event("pour_start") qui
                        # bloquent plusieurs secondes. Sans ce reset, last_seen_ts date de la
                        # premiere detection et CARD_GRACE_PERIOD_S expire pendant les appels reseau.
                        # / Reset timer after the blocking network calls (authorize + pour_start).
                        # Without this, last_seen_ts is from first detection and CARD_GRACE_PERIOD_S
                        # expires during the network calls, closing the valve immediately.
                        self.last_seen_ts = time.time()
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
        self.authorize_a_refaire = False
        try:
            auth = self.client.authorize(uid)
        except BackendError as e:
            logger.error(f"Erreur backend authorize: {e} — nouvel essai a la prochaine lecture.")
            self.is_serving = False
            self.session_id = None
            # La carte reste la carte courante. Si elle est retirée, card_removed
            # part et l'écran revient à « En attente ». Si elle reste posée, la
            # boucle relance authorize à la lecture suivante. Le serveur clôt
            # lui-même la session orpheline au prochain authorize.
            # La pause garde les essais sous la limite du serveur
            # (voir AUTHORIZE_RETRY_DELAY_S).
            # / The card stays current: its removal sends card_removed; while it stays,
            # the loop retries authorize after a pause.
            self.authorize_a_refaire = True
            time.sleep(AUTHORIZE_RETRY_DELAY_S)
            return

        if auth.get("authorized") is True:
            # --- Autorise ---
            self.session_id = auth.get("session_id")
            self.allowed_ml = float(auth.get("allowed_ml", 0))

            # Appliquer le facteur de calibration envoyé par le serveur.
            # Une calibration faite dans l'admin compte ainsi dès ce badge.
            # À faire AVANT la photo du volume de départ (juste en dessous) :
            # volume_l() recalcule tout le compteur avec le facteur courant.
            # Changer le facteur après la photo fausserait le volume servi.
            # / Apply the calibration factor sent by the server, BEFORE the start
            # snapshot below: volume_l() recomputes the whole counter with it.
            facteur_de_calibration = auth.get("calibration_factor")
            if facteur_de_calibration:
                self.flow_meter.set_calibration_factor(facteur_de_calibration)

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

            # Informer le serveur (pour le push WebSocket vers le kiosk).
            # Une erreur réseau ici ne doit pas arrêter le service : pour_start ne
            # sert qu'à l'écran, la vanne est déjà ouverte et le volume se mesure.
            # / Notify server (kiosk WebSocket push). A network error must not stop
            # the pour: pour_start only feeds the screen.
            try:
                self.client.send_event("pour_start", uid, 0)
            except BackendError as e:
                logger.warning(f"pour_start echoue (on continue): {e}")
            self.last_update_ts = time.time()

        else:
            # --- Refuse ---
            message = auth.get("message", "Non autorise")
            logger.warning(f"Badge {uid} refuse: {message}")
            self.is_serving = False
            self.session_id = None

    def _fermer_si_plafond_atteint(self):
        """Ferme la vanne et envoie pour_end si le volume autorisé est atteint.
        / Closes the valve and sends pour_end if the allowed volume is reached.

        Appelée à chaque tour de boucle pendant un service (voir run()).
        La vanne est fermée AVANT l'appel au serveur : une erreur réseau sur
        pour_end ne doit ni laisser couler la bière, ni arrêter le programme.
        Sans pour_end, le serveur clôt la session au retrait de la carte
        (card_removed) ou au badge suivant, avec le dernier volume reçu.
        / Called on every loop turn while serving. The valve closes BEFORE the
        server call: a network error on pour_end must not crash the program.
        """
        served_ml = (self.flow_meter.volume_l() * 1000.0) - self.session_start_vol
        plafond_atteint = self.allowed_ml > 0 and served_ml >= self.allowed_ml
        if not plafond_atteint:
            return

        logger.warning(f"Volume max atteint ({self.allowed_ml:.0f}ml). Fermeture vanne.")
        self.valve.close()
        self.is_serving = False
        try:
            self.client.send_event("pour_end", self.current_uid, served_ml)
        except BackendError as e:
            logger.error(f"pour_end au plafond echoue: {e}")

    def _handle_pouring_loop(self, now):
        """Pendant le service : envoie le volume au serveur, au plus une fois par seconde.
        Le plafond, lui, est contrôlé à chaque tour par _fermer_si_plafond_atteint().
        / During service: sends the volume to the server, at most once per second.
        The cap is checked on every turn by _fermer_si_plafond_atteint()."""
        if (now - self.last_update_ts) < UPDATE_INTERVAL_S:
            return

        served_ml = (self.flow_meter.volume_l() * 1000.0) - self.session_start_vol

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

        # Envoyer card_removed dans tous les cas : avec ou sans session.
        # Sans session (carte refusee) : permet au kiosk de revenir a "En attente".
        # / Send card_removed in all cases: with or without session.
        # Without session (refused card): lets the kiosk go back to "Waiting".
        if self.current_uid is not None:
            try:
                self.client.send_event("card_removed", self.current_uid, 0)
            except BackendError:
                pass

        self.current_uid = None
        self.session_id = None
        self.allowed_ml = 0.0
        self.authorize_a_refaire = False

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
        """Arret propre : clore la session en cours cote serveur, puis fermer la vanne.
        Sans cela, un arret (systemctl stop, reboot) pendant un service laisse la
        session « en cours » sur le serveur : jamais facturee, et le kiosk reste
        fige sur la derniere carte.
        / Clean shutdown: end the current session server-side, then close the valve.
        Otherwise a stop/reboot during a pour leaves the session open on the server:
        never billed, and the kiosk stays stuck on the last card."""
        logger.info("Nettoyage des ressources...")
        if self.current_uid is not None:
            try:
                logger.info(f"Session en cours (badge {self.current_uid}) : cloture avant arret.")
                self._handle_card_removal()
            except Exception as e:
                logger.error(f"Cloture de session a l'arret echouee: {e}")
        try:
            # ferme la vanne, puis pi.stop()
            self.valve.cleanup()      
        except Exception:
            pass
        try:
            self.flow_meter.cleanup()  # cb.cancel(), puis pi.stop()
        except Exception:
            pass
