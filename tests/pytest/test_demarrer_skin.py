"""
Tests de la commande demarrer_skin (migration skins, CHANTIER-07).
/ Tests of the demarrer_skin command (skins migration, CHANTIER-07).

LOCALISATION : tests/pytest/test_demarrer_skin.py

Ce fichier ne teste QUE le refus des noms interdits — aucun test n'ecrit sur le
disque. Les deux tests qui creaient reellement un skin jetable sous
`pages/templates/pages/` ont ete retires : le StatReloader du serveur de dev
globe cette arborescence, voyait le dossier apparaitre puis disparaitre, et
mourait sur une FileNotFoundError. Le serveur tombe, et tous les tests suivants
qui l'appellent en HTTP echouent en 502 (cf. tests/PIEGES.md 9.111).
/ This file ONLY tests the rejection of forbidden names — no test writes to
disk. The two tests that actually created a throwaway skin were removed: the dev
server's StatReloader globs that tree and died on the vanishing folder, taking
every later HTTP test down with it (see tests/PIEGES.md 9.111).
"""
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def test_demarrer_skin_refuse_les_noms_reserves_et_invalides():
    """'classic', 'reunion' et les noms invalides sont refusés."""
    for nom_interdit in ("classic", "reunion", "Mon Skin", "UPPER", "-tiret"):
        with pytest.raises(CommandError):
            call_command("demarrer_skin", nom_interdit)
