"""
tests/pytest/test_formatters_fuseau_du_lieu.py — L'heure des tickets imprimes.
/ Printed ticket times.

LOCALISATION : tests/pytest/test_formatters_fuseau_du_lieu.py

Les tickets s'impriment dans le worker Celery, ou le fuseau courant est celui de
settings.TIME_ZONE (UTC). Ils doivent afficher l'heure du lieu.
/ Tickets print in the Celery worker, in UTC. They must show the venue's time.
"""

import zoneinfo
from datetime import datetime, timezone as fuseau_datetime
from types import SimpleNamespace
from unittest.mock import patch

from django.utils import timezone

from laboutik.printing.formatters import (
    formatter_ticket_billet,
    formatter_ticket_commande,
)

# 12:00 UTC le 30 octobre 2026 : 13:00 a Paris (heure d'hiver).
# / 12:00 UTC on 30 October 2026: 13:00 in Paris (winter time).
MIDI_UTC = datetime(2026, 10, 30, 12, 0, tzinfo=fuseau_datetime.utc)


def _configuration_a_paris():
    """Configuration factice du lieu. / Fake venue configuration."""
    return SimpleNamespace(get_tzinfo=lambda: zoneinfo.ZoneInfo("Europe/Paris"))


def test_le_ticket_cuisine_affiche_l_heure_du_lieu():
    """Worker en UTC : le ticket cuisine montre 13:00. / Kitchen ticket shows 13:00."""
    commande = SimpleNamespace(table=None, uuid="abcdef12-0000")
    imprimante = SimpleNamespace(name="CUISINE")

    with (
        patch("BaseBillet.models.Configuration.get_solo", _configuration_a_paris),
        patch("laboutik.printing.formatters.timezone.now", return_value=MIDI_UTC),
        timezone.override("UTC"),
    ):
        ticket = formatter_ticket_commande(commande, [], imprimante)

    assert ticket["header"]["date"] == "13:00"


def test_le_billet_affiche_l_heure_de_l_evenement_dans_le_fuseau_du_lieu():
    """Worker en UTC : le billet montre 13:00. / The ticket shows 13:00."""
    evenement = SimpleNamespace(datetime=MIDI_UTC, name="Concert")
    billet = SimpleNamespace(
        uuid="abcdef12-0000",
        pricesold=None,
        qrcode=lambda: "",
        first_name="",
        last_name="",
    )
    reservation = SimpleNamespace(user_commande=None, event=evenement)

    with (
        patch("BaseBillet.models.Configuration.get_solo", _configuration_a_paris),
        timezone.override("UTC"),
    ):
        ticket = formatter_ticket_billet(billet, reservation, evenement)

    assert "30/10/2026 13:00" in str(ticket)
