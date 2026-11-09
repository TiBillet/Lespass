"""
API v2 : un identifiant qui n'est pas un UUID donne un 404, jamais un 500.
/ API v2: an identifier that is not a UUID gives a 404, never a 500.

LOCALISATION : tests/pytest/test_api_v2_identifiant_mal_forme.py

CE QUE CES TESTS PROTEGENT
--------------------------
Le routeur DRF accepte n'importe quel texte a la place de l'uuid dans l'URL
(un uuid tronque, une faute de frappe, un slug). Sans verification, Django
leve ValidationError en convertissant ce texte en UUID, et l'API repond 500.
Les vues passent donc par get_objet_par_uuid_ou_404 (api_v2/views.py).
Les routes des pages et des blocs sont couvertes dans test_pages_api.py.
/ Each route below must answer 404 to a malformed uuid. Pages and blocks
are covered in test_pages_api.py.
"""

import pytest
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

from Customers.models import Client

IDENTIFIANT_QUI_N_EST_PAS_UN_UUID = "8d22a6b4-x"

# Chaque route, avec le droit de cle API qu'elle demande.
# / Each route, with the API key right it requires.
ROUTES_AVEC_UUID_DANS_L_URL = [
    ("crowd", "get", "/api/v2/initiatives/{identifiant}/"),
    ("crowd", "delete", "/api/v2/initiatives/{identifiant}/"),
    ("crowd", "get", "/api/v2/initiatives/{identifiant}/budget-items/"),
    ("crowd", "get", "/api/v2/initiatives/{identifiant}/votes/"),
    ("crowd", "get", "/api/v2/initiatives/{identifiant}/participations/"),
    ("product", "get", "/api/v2/products/{identifiant}/"),
    ("reservation", "get", "/api/v2/reservations/{identifiant}/"),
    ("membership", "get", "/api/v2/memberships/{identifiant}/"),
]


@pytest.fixture
def cle_api_crowd_product_reservation_membership(db):
    """Cree une cle API avec les droits crowd, product, reservation et membership
    sur le tenant lespass, et renvoie la cle brute.
    / Creates an API key with the four rights and returns the raw key."""
    from BaseBillet.models import ExternalApiKey
    from rest_framework_api_key.models import APIKey
    tenant = Client.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        api_key_obj, cle_brute = APIKey.objects.create_key(name="identifiant-mal-forme")
        ExternalApiKey.objects.create(
            name="identifiant-mal-forme", key=api_key_obj,
            crowd=True, product=True, reservation=True, membership=True,
        )
    return cle_brute


@pytest.mark.django_db
@pytest.mark.parametrize("droit_de_la_cle, methode, gabarit_de_route", ROUTES_AVEC_UUID_DANS_L_URL)
def test_identifiant_qui_n_est_pas_un_uuid_renvoie_404(
        cle_api_crowd_product_reservation_membership, droit_de_la_cle, methode, gabarit_de_route):
    """Un identifiant mal forme donne un 404 : la ressource ne peut pas exister.
    / A malformed identifier gives a 404: the resource cannot exist."""
    client = APIClient()
    client.raise_request_exception = False
    route = gabarit_de_route.format(identifiant=IDENTIFIANT_QUI_N_EST_PAS_UN_UUID)
    entetes = {
        "HTTP_AUTHORIZATION": f"Api-Key {cle_api_crowd_product_reservation_membership}",
        "HTTP_HOST": "lespass.tibillet.localhost",
    }

    appel_http = getattr(client, methode)
    reponse = appel_http(route, **entetes)

    assert reponse.status_code == 404, (droit_de_la_cle, reponse.status_code, reponse.content[:200])
