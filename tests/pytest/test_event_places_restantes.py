"""
Tests des méthodes Event.places_restantes() et Event.jauge_presque_pleine(),
lues par le talon de la page événement V2 (partials/reservation_declencheur.html).
/ Tests for the seats-left helpers used by the V2 event page ticket stub.

LOCALISATION : tests/pytest/test_event_places_restantes.py

Aucune base : un Event non enregistré, et les deux compteurs (billets validés,
billets en cours de paiement) remplacés par des valeurs fixes.
/ No database: unsaved Event, both counters patched.

Lancer / Run :
    poetry run pytest -q tests/pytest/test_event_places_restantes.py
"""
from unittest.mock import patch

import pytest

from BaseBillet.models import Event


def creer_event_avec_compteurs(jauge_max, billets_valides, billets_en_paiement):
    event = Event(jauge_max=jauge_max)
    patch_valides = patch.object(Event, "valid_tickets_count", return_value=billets_valides)
    patch_en_paiement = patch.object(Event, "under_purchase", return_value=billets_en_paiement)
    return event, patch_valides, patch_en_paiement


@pytest.mark.parametrize(
    "jauge_max, billets_valides, billets_en_paiement, places_attendues",
    [
        (120, 83, 0, 37),   # cas nominal / nominal
        (120, 83, 5, 32),   # les paiements en cours sont retirés / pending payments taken out
        (50, 50, 0, 0),     # complet / full
        (50, 48, 6, 0),     # dépassement : jamais négatif / overbooked: never negative
    ],
)
def test_places_restantes(jauge_max, billets_valides, billets_en_paiement, places_attendues):
    event, patch_valides, patch_en_paiement = creer_event_avec_compteurs(
        jauge_max, billets_valides, billets_en_paiement
    )
    with patch_valides, patch_en_paiement:
        assert event.places_restantes() == places_attendues


@pytest.mark.parametrize(
    "jauge_max, billets_valides, presque_pleine_attendue",
    [
        (120, 83, False),   # 37 places sur 120 : 31 % restant
        (120, 102, True),   # 18 places sur 120 : 15 % restant, seuil inclus
        (120, 101, False),  # 19 places sur 120 : juste au-dessus du seuil
        (0, 0, False),      # jauge à zéro : pas de division par zéro
    ],
)
def test_jauge_presque_pleine(jauge_max, billets_valides, presque_pleine_attendue):
    event, patch_valides, patch_en_paiement = creer_event_avec_compteurs(
        jauge_max, billets_valides, 0
    )
    with patch_valides, patch_en_paiement:
        assert event.jauge_presque_pleine() is presque_pleine_attendue
