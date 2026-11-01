"""
Route legacy de la jauge du jour : GET /api/gauge/
/ Legacy route for today's gauge: GET /api/gauge/

LOCALISATION : tests/pytest/test_api_gauge.py

Code testé / Tested code : ApiBillet/views.py (Gauge), ApiBillet/permissions.py (get_apikey_valid)

Le droit vient du basename de la vue. `Gauge` est montée avec `path()`, sans routeur :
elle doit déclarer son basename elle-même.
/ Access comes from the view's basename. `Gauge` is mounted with `path()`, without a
router, so it must declare its own basename.

Lancer / Run : make test ARGS="tests/pytest/test_api_gauge.py"
"""

import pytest
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient
from rest_framework_api_key.models import APIKey

from BaseBillet.models import Configuration, ExternalApiKey
from fabriques_panier import identifiant_unique

pytestmark = pytest.mark.django_db


def appeler_la_jauge_avec_une_cle(tenant, utilisateur_de_la_cle, droit_ticket):
    """Crée une clé API sur le lieu et appelle la route. / Creates a key and calls the route."""
    with tenant_context(tenant):
        cle_technique, cle_en_clair = APIKey.objects.create_key(
            name=f"jauge-{identifiant_unique()}",
        )
        ExternalApiKey.objects.create(
            name=f"jauge-{identifiant_unique()}",
            key=cle_technique,
            ticket=droit_ticket,
            user=utilisateur_de_la_cle,
        )

    return APIClient().get(
        "/api/gauge/",
        HTTP_AUTHORIZATION=f"Api-Key {cle_en_clair}",
        HTTP_HOST="lespass.tibillet.localhost",
    )


def test_une_cle_admin_avec_le_droit_ticket_lit_la_jauge(tenant, admin_user):
    reponse = appeler_la_jauge_avec_une_cle(tenant, admin_user, droit_ticket=True)

    assert reponse.status_code == 200, reponse.content
    donnees_de_la_jauge = reponse.json()
    with tenant_context(tenant):
        assert donnees_de_la_jauge["gauge_max"] == Configuration.get_solo().jauge_max
    assert (
        donnees_de_la_jauge["all_tickets"]
        >= donnees_de_la_jauge["scanned_tickets"]
        >= 0
    )


def test_une_cle_sans_le_droit_ticket_est_refusee(tenant, admin_user):
    reponse = appeler_la_jauge_avec_une_cle(tenant, admin_user, droit_ticket=False)

    assert reponse.status_code == 403, reponse.content
