"""
Tests du contrôleur du Pi de la tireuse, sans matériel.
/ Tests for the tap Pi controller, without hardware.

LOCALISATION : tests/pytest/test_controlvanne_pi_controleur.py

Le contrôleur (controlvanne/Pi/controllers/tibeer_controller.py) reçoit ses
quatre objets par son constructeur : lecteur NFC, vanne, débitmètre, client du
serveur. Ces tests lui donnent de faux objets écrits ici. Aucun Raspberry Pi,
aucune base de données, aucun réseau n'est nécessaire.
/ The controller gets its four objects through its constructor. These tests
pass fakes written here: no Pi, no database, no network.

Le code du Pi n'est pas un paquet de Lespass : on ajoute son dossier à
sys.path. Il lit sa configuration dans config/settings.py, qui :
- importe python-dotenv, absent du conteneur Django : on le remplace par un
  module vide s'il manque ;
- crée le dossier des journaux (LOG_DIR) : on le pointe vers un dossier
  temporaire, avant l'import.
/ The Pi code is not a Lespass package: its folder is added to sys.path.
python-dotenv is stubbed when missing, and LOG_DIR points to a temp folder.
"""

import os
import sys
import tempfile
import types
from pathlib import Path

# Dossier du code du Pi / Pi code folder
DOSSIER_DU_CODE_DU_PI = Path(__file__).resolve().parents[2] / "controlvanne" / "Pi"
if str(DOSSIER_DU_CODE_DU_PI) not in sys.path:
    sys.path.insert(0, str(DOSSIER_DU_CODE_DU_PI))

# Journaux du Pi dans un dossier temporaire / Pi logs in a temp folder
os.environ.setdefault("LOG_DIR", tempfile.mkdtemp(prefix="tibeer_logs_test_"))

# python-dotenv n'est installé que sur le Pi / python-dotenv only exists on the Pi
try:
    import dotenv  # noqa: F401
except ModuleNotFoundError:
    module_dotenv_vide = types.ModuleType("dotenv")
    module_dotenv_vide.load_dotenv = lambda *arguments, **options: None
    sys.modules["dotenv"] = module_dotenv_vide

import controllers.tibeer_controller as module_du_controleur  # noqa: E402
from controllers.tibeer_controller import TibeerController  # noqa: E402
from utils.exceptions import BackendError  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Faux objets / Fakes
# ──────────────────────────────────────────────────────────────────────


class FauxLecteurNFC:
    """Lecteur NFC sans carte. Les tests appellent le contrôleur directement.
    / NFC reader with no card. Tests call the controller directly."""

    def read_uid(self):
        return None


class FausseVanne:
    """
    Retient si la vanne est ouverte, et le volume compté à sa fermeture.
    / Remembers whether the valve is open, and the volume counted when it closed.
    """

    def __init__(self, debitmetre=None):
        self.est_ouverte = False
        self.debitmetre = debitmetre
        self.volume_ml_a_la_premiere_fermeture = None

    def open(self):
        self.est_ouverte = True

    def close(self):
        premiere_fermeture_avec_debitmetre = (
            self.debitmetre is not None and self.volume_ml_a_la_premiere_fermeture is None
        )
        if self.est_ouverte and premiere_fermeture_avec_debitmetre:
            self.volume_ml_a_la_premiere_fermeture = self.debitmetre.volume_l() * 1000.0
        self.est_ouverte = False


class FauxDebitmetre:
    """
    Même calcul que controlvanne/Pi/hardware/flow_meter.py :
    1 litre = facteur × 60 impulsions, sur le compteur total.
    / Same math as the real flow meter: 1 L = factor × 60 pulses, on the total count.
    """

    def __init__(self, facteur_de_calibration, impulsions_deja_comptees=0):
        self.calibration_factor = float(facteur_de_calibration)
        self.total_pulses = impulsions_deja_comptees

    def volume_l(self):
        impulsions_par_litre = self.calibration_factor * 60
        return self.total_pulses / impulsions_par_litre

    def set_calibration_factor(self, factor):
        self.calibration_factor = float(factor)

    def update(self):
        pass


class FauxClientDuServeur:
    """
    Répond à authorize avec la réponse donnée au constructeur.
    Retient les événements envoyés. Les types listés dans
    `evenements_en_erreur_reseau` lèvent BackendError, comme une 4G coupée.
    / Answers authorize with the given response. Records sent events. Event
    types listed in `evenements_en_erreur_reseau` raise BackendError.
    """

    def __init__(self, reponse_a_authorize, evenements_en_erreur_reseau=()):
        self.reponse_a_authorize = reponse_a_authorize
        self.evenements_en_erreur_reseau = evenements_en_erreur_reseau
        self.evenements_envoyes = []

    def authorize(self, uid):
        return self.reponse_a_authorize

    def send_event(self, event_type, uid, volume_ml=0):
        if event_type in self.evenements_en_erreur_reseau:
            raise BackendError(f"Erreur reseau simulee sur {event_type}")
        self.evenements_envoyes.append((event_type, uid, volume_ml))
        return {"status": "ok"}


class FausseHorloge:
    """
    Remplace le module `time` du contrôleur. sleep() avance l'heure sans attendre.
    / Replaces the controller's `time` module. sleep() moves time forward instantly.
    """

    def __init__(self):
        self.heure_actuelle = 1000.0

    def time(self):
        return self.heure_actuelle

    def sleep(self, secondes):
        self.heure_actuelle += secondes


class FauxLecteurQuiVerse:
    """
    Carte toujours posée. À chaque lecture, tant que la vanne est ouverte, le
    débitmètre reçoit des impulsions (la bière coule). La boucle s'arrête après
    `nombre_de_lectures` lectures.
    / Card always present. On each read, while the valve is open, the flow meter
    gets pulses. The loop stops after `nombre_de_lectures` reads.
    """

    def __init__(self, uid, vanne, debitmetre, impulsions_par_lecture, nombre_de_lectures):
        self.uid = uid
        self.vanne = vanne
        self.debitmetre = debitmetre
        self.impulsions_par_lecture = impulsions_par_lecture
        self.lectures_restantes = nombre_de_lectures
        self.controleur = None

    def read_uid(self):
        if self.vanne.est_ouverte:
            self.debitmetre.total_pulses += self.impulsions_par_lecture
        self.lectures_restantes -= 1
        if self.lectures_restantes <= 0:
            self.controleur.running = False
        return self.uid


def reponse_autorisee(**champs_en_plus):
    """Réponse d'authorize pour une carte acceptée.
    / authorize response for an accepted card."""
    reponse = {
        "authorized": True,
        "session_id": 1,
        "is_maintenance": False,
        "allowed_ml": 1000.0,
        "solde_centimes": 500,
        "message": "OK",
    }
    reponse.update(champs_en_plus)
    return reponse


def volume_servi_ml(controleur):
    """Même calcul que le contrôleur pendant un service.
    / Same computation as the controller during a pour."""
    return controleur.flow_meter.volume_l() * 1000.0 - controleur.session_start_vol


# ──────────────────────────────────────────────────────────────────────
# Tests : facteur de calibration reçu à l'authorize
# ──────────────────────────────────────────────────────────────────────


class TestFacteurDeCalibrationRecuAuBadge:
    def test_le_facteur_recu_est_applique_avant_la_mesure(self):
        """
        Le facteur renvoyé par authorize sert à mesurer la session.
        / The factor returned by authorize is used to measure the session.

        Le compteur garde les impulsions des services précédents (390 ici).
        Si le facteur changeait APRÈS la photo du volume de départ, le volume
        servi serait faux : le départ serait calculé avec l'ancien facteur.
        / The counter keeps pulses from previous pours (390 here). Changing the
        factor AFTER the start snapshot would skew the served volume.
        """
        debimetre = FauxDebitmetre(facteur_de_calibration=6.5, impulsions_deja_comptees=390)
        client = FauxClientDuServeur(reponse_autorisee(calibration_factor=7.5))
        controleur = TibeerController(FauxLecteurNFC(), FausseVanne(), debimetre, client)

        controleur._handle_new_session("CARTE01")

        assert debimetre.calibration_factor == 7.5

        # 450 impulsions à 7,5 = exactement 1 litre / 450 pulses at 7.5 = 1 liter
        debimetre.total_pulses += 450
        assert round(volume_servi_ml(controleur), 1) == 1000.0

    def test_sans_facteur_dans_la_reponse_le_facteur_ne_change_pas(self):
        """
        Un serveur qui ne renvoie pas de facteur ne change rien au débitmètre.
        / A server that sends no factor leaves the flow meter unchanged.
        """
        debimetre = FauxDebitmetre(facteur_de_calibration=6.5)
        client = FauxClientDuServeur(reponse_autorisee())
        controleur = TibeerController(FauxLecteurNFC(), FausseVanne(), debimetre, client)

        controleur._handle_new_session("CARTE01")

        assert debimetre.calibration_factor == 6.5


# ──────────────────────────────────────────────────────────────────────
# Tests : erreurs réseau pendant le service
# ──────────────────────────────────────────────────────────────────────


class TestErreurReseauPendantLeService:
    def test_pour_start_en_erreur_ne_fait_pas_planter_le_pi(self):
        """
        Une erreur réseau sur pour_start ne lève rien : le service continue.
        / A network error on pour_start raises nothing: the pour goes on.

        pour_start ne sert qu'à l'écran. Sans protection, l'erreur remontait
        jusqu'à main.py, qui quittait : le Pi redémarrait, vanne ouverte.
        / pour_start only feeds the screen; unprotected, the error killed the Pi.
        """
        debimetre = FauxDebitmetre(facteur_de_calibration=6.5)
        vanne = FausseVanne()
        client = FauxClientDuServeur(
            reponse_autorisee(), evenements_en_erreur_reseau=("pour_start",)
        )
        controleur = TibeerController(FauxLecteurNFC(), vanne, debimetre, client)

        controleur._handle_new_session("CARTE01")

        assert vanne.est_ouverte is True
        assert controleur.is_serving is True


# ──────────────────────────────────────────────────────────────────────
# Tests : plafond de volume
# ──────────────────────────────────────────────────────────────────────


def lancer_un_service_jusqu_au_plafond(monkeypatch, client, debimetre):
    """
    Lance la vraie boucle run() avec une fausse horloge, carte posée, bière qui coule.
    10 impulsions par tour de 0,1 s, au facteur 6,5 : environ 25,6 ml par tour.
    / Runs the real run() loop with a fake clock, card present, beer flowing.
    """
    monkeypatch.setattr(module_du_controleur, "time", FausseHorloge())
    vanne = FausseVanne(debitmetre=debimetre)
    lecteur = FauxLecteurQuiVerse(
        "CARTE01", vanne, debimetre, impulsions_par_lecture=10, nombre_de_lectures=40
    )
    controleur = TibeerController(lecteur, vanne, debimetre, client)
    lecteur.controleur = controleur
    controleur.run()
    return vanne, controleur


class TestPlafondDeVolume:
    def test_la_vanne_se_ferme_des_que_le_plafond_est_atteint(self, monkeypatch):
        """
        Le plafond est contrôlé à chaque tour de boucle, pas une fois par seconde.
        / The cap is checked on every loop turn, not once per second.

        Plafond de 100 ml, environ 25,6 ml versés par tour de 0,1 s. La vanne doit
        se fermer au premier tour qui dépasse 100 ml, donc avant 130 ml.
        Contrôlé une fois par seconde, elle se fermait vers 256 ml : le surplus
        n'est pas facturé, c'est une perte pour le lieu.
        / 100 ml cap, ~25.6 ml per 0.1 s turn: the valve must close before 130 ml.
        """
        debimetre = FauxDebitmetre(facteur_de_calibration=6.5)
        client = FauxClientDuServeur(reponse_autorisee(allowed_ml=100.0))

        vanne, _controleur = lancer_un_service_jusqu_au_plafond(monkeypatch, client, debimetre)

        assert vanne.volume_ml_a_la_premiere_fermeture is not None
        assert 100.0 <= vanne.volume_ml_a_la_premiere_fermeture < 130.0
        evenements_de_fin = [e for e in client.evenements_envoyes if e[0] == "pour_end"]
        assert len(evenements_de_fin) == 1

    def test_pour_end_en_erreur_au_plafond_ne_fait_pas_planter_le_pi(self, monkeypatch):
        """
        Au plafond, une erreur réseau sur pour_end ne lève rien. La vanne reste fermée.
        Le serveur clôt la session au retrait de la carte, ou au badge suivant.
        / At the cap, a network error on pour_end raises nothing; the valve stays closed.
        """
        debimetre = FauxDebitmetre(facteur_de_calibration=6.5)
        client = FauxClientDuServeur(
            reponse_autorisee(allowed_ml=100.0), evenements_en_erreur_reseau=("pour_end",)
        )

        vanne, controleur = lancer_un_service_jusqu_au_plafond(monkeypatch, client, debimetre)

        assert vanne.volume_ml_a_la_premiere_fermeture is not None
        assert vanne.est_ouverte is False
