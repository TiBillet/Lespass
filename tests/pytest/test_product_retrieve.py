"""
Test DB-only — API v2 : retrieve d'un Product par uuid.
/ DB-only test — API v2: retrieve a Product by uuid.

Contexte (issue Sentry 7368726717) : `ProductViewSet.retrieve(self, request, uuid=None)`
attendait `uuid`, mais le routeur DRF passait `pk` (il manquait
`lookup_field = "uuid"` sur le ViewSet) -> TypeError -> HTTP 500, meme avec un
uuid valide. L'endpoint detail Product n'avait donc jamais fonctionne.
/ retrieve expected `uuid` but the router passed `pk` (missing lookup_field) ->
TypeError -> 500, even with a valid uuid.

Run: docker exec -e API_KEY=dummy lespass_django poetry run pytest \
        tests/pytest/test_product_retrieve.py -q
"""
import uuid

import pytest
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

HOST = "lespass.tibillet.localhost"


# Reutiliser la DB dev (pattern V2 onboard). / Reuse the dev DB (V2 onboard pattern).
@pytest.fixture(scope="session")
def django_db_setup():
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


pytestmark = pytest.mark.django_db


@pytest.fixture
def product_setup():
    """
    Cree un produit + une cle API (droit `product`), dans une transaction annulee.
    / Create a product + an API key (`product` right), in a rolled-back transaction.
    """
    from django.db import transaction
    from Customers.models import Client
    from BaseBillet.models import ExternalApiKey, Product, Price
    from rest_framework_api_key.models import APIKey

    tenant = Client.objects.get(schema_name="lespass")
    suffix = uuid.uuid4().hex[:6]

    with tenant_context(tenant):
        with transaction.atomic():
            product = Product.objects.create(
                name=f"Test product retrieve {suffix}",
                categorie_article=Product.ADHESION,
            )
            Price.objects.create(
                product=product,
                name="Normal",
                prix=10,
                subscription_type=Price.YEAR,
            )
            api_obj, key_str = APIKey.objects.create_key(name=f"product-{suffix}")
            ExternalApiKey.objects.create(
                name=f"product-{suffix}",
                key=api_obj,
                product=True,
            )
            try:
                yield {"key": key_str, "product": product}
            finally:
                # Annule tout ce qui a ete cree par ce fixture.
                # / Roll back everything created by this fixture.
                transaction.set_rollback(True)


def _get(identifier, key):
    """
    Appelle l'endpoint detail d'un produit avec une cle API valide.
    / Call the product detail endpoint with a valid API key.

    raise_request_exception = False : on observe le code HTTP (ex. 500 si bug)
    plutot que de voir l'exception remonter dans le test.
    / Observe the returned HTTP status rather than letting the exception bubble up.
    """
    client = APIClient()
    client.raise_request_exception = False
    return client.get(
        f"/api/v2/products/{identifier}/",
        SERVER_NAME=HOST,
        HTTP_AUTHORIZATION=f"Api-Key {key}",
    )


def test_product_retrieve_par_uuid(product_setup):
    # Acces par uuid : doit renvoyer 200 et contenir l'uuid du produit.
    # / Lookup by uuid: must return 200 and contain the product uuid.
    product = product_setup["product"]
    resp = _get(product.uuid, key=product_setup["key"])
    assert resp.status_code == 200
    assert str(product.uuid) in str(resp.json())


def test_product_retrieve_uuid_inconnu_renvoie_404(product_setup):
    # Un uuid bien forme mais inconnu -> 404 (non-regression).
    # / A well-formed but unknown uuid -> 404 (regression guard).
    resp = _get(uuid.uuid4(), key=product_setup["key"])
    assert resp.status_code == 404
