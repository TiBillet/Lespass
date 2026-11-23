"""
Tests des identifiants raccourcis ecrits dans les logs.
/ Tests of the shortened identifiers written to logs.

LOCALISATION : tests/pytest/test_identifiants_pour_les_logs.py
Code teste : TiBillet/identifiants_pour_les_logs.py

SIMULATIONS
- Aucune : fonctions pures, ni base de donnees ni reseau.
/ None: pure functions, no database, no network.
"""

import uuid

from TiBillet.identifiants_pour_les_logs import carte_courte, uuid_court


def test_carte_courte_ne_garde_que_les_4_premiers_caracteres():
    """Le tag entier n'apparait jamais. / The full tag never shows."""
    assert carte_courte("89eee11a") == "89EE…"


def test_carte_courte_sans_carte():
    """Pas de carte : un mot lisible, pas « None ». / No card: a readable word."""
    assert carte_courte(None) == "aucune"
    assert carte_courte("") == "aucune"


def test_uuid_court_garde_les_8_premiers_caracteres():
    """Le debut de l'UUID, celui de l'URL de la fiche admin. / Start of the UUID."""
    uuid_de_test = uuid.UUID("1a2b3c4d-0000-4000-8000-000000000000")
    assert uuid_court(uuid_de_test) == "1a2b3c4d"


def test_uuid_court_sans_uuid():
    """Pas d'UUID : un mot lisible, pas « None ». / No UUID: a readable word."""
    assert uuid_court(None) == "aucun"
