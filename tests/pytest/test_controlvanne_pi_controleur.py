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

from controllers.tibeer_controller import TibeerController  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Faux objets / Fakes
# ──────────────────────────────────────────────────────────────────────


class FauxLecteurNFC:
    """Lecteur NFC sans carte. Les tests appellent le contrôleur directement.
    / NFC reader with no card. Tests call the controller directly."""

    def read_uid(self):
        return None


class FausseVanne:
    """Retient si la vanne est ouverte. / Remembers whether the valve is open."""

    def __init__(self):
        self.est_ouverte = False

    def open(self):
        self.est_ouverte = True

    def close(self):
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
    Retient les événements envoyés.
    / Answers authorize with the given response. Records sent events.
    """

    def __init__(self, reponse_a_authorize):
        self.reponse_a_authorize = reponse_a_authorize
        self.evenements_envoyes = []

    def authorize(self, uid):
        return self.reponse_a_authorize

    def send_event(self, event_type, uid, volume_ml=0):
        self.evenements_envoyes.append((event_type, uid, volume_ml))
        return {"status": "ok"}


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
