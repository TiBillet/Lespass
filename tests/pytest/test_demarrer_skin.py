"""
Tests de la commande demarrer_skin (migration skins, CHANTIER-07).
/ Tests of the demarrer_skin command (skins migration, CHANTIER-07).

LOCALISATION : tests/pytest/test_demarrer_skin.py

La commande copie pages/templates/pages/classic/ vers pages/<nom>/.
Les tests créent un skin jetable "pytest-skin-jetable" puis le suppriment
(base dev live, pas de rollback filesystem — nettoyage en finally).
/ The command copies the classic base to a new skin folder. Tests create a
throwaway skin then always clean it up.
"""
import shutil
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

DOSSIER_PAGES = Path("pages/templates/pages")
NOM_JETABLE = "pytest-skin-jetable"


def test_demarrer_skin_cree_une_copie_du_socle():
    """La commande copie classic/ vers le nouveau dossier (shell + vues)."""
    dossier_nouveau = DOSSIER_PAGES / NOM_JETABLE
    try:
        call_command("demarrer_skin", NOM_JETABLE)

        assert (dossier_nouveau / "shell.html").is_file()
        assert (dossier_nouveau / "headless.html").is_file()
        assert (dossier_nouveau / "vues" / "agenda.html").is_file()
        assert (dossier_nouveau / "partials" / "carte_evenement.html").is_file()
    finally:
        # Nettoyage : on ne laisse JAMAIS le skin jetable dans le repo.
        # / Cleanup: never leave the throwaway skin in the repo.
        shutil.rmtree(dossier_nouveau, ignore_errors=True)


def test_demarrer_skin_refuse_d_ecraser_un_skin_existant():
    """Relancer la commande sur un skin existant échoue sans rien toucher."""
    dossier_nouveau = DOSSIER_PAGES / NOM_JETABLE
    try:
        call_command("demarrer_skin", NOM_JETABLE)
        with pytest.raises(CommandError, match="existe déjà"):
            call_command("demarrer_skin", NOM_JETABLE)
    finally:
        shutil.rmtree(dossier_nouveau, ignore_errors=True)


def test_demarrer_skin_refuse_les_noms_reserves_et_invalides():
    """'classic', 'reunion' et les noms invalides sont refusés."""
    for nom_interdit in ("classic", "reunion", "Mon Skin", "UPPER", "-tiret"):
        with pytest.raises(CommandError):
            call_command("demarrer_skin", nom_interdit)
