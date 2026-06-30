"""
Tests — API v2 : partager un produit sur PLUSIEURS evenements.
/ Tests — API v2: share a product across SEVERAL events.

LOCALISATION : tests/pytest/test_api_v2_product_link_event.py

CONTEXTE :
Le lien Product<->Event est une ManyToMany (Event.products). Un meme produit
peut donc etre reutilise sur N evenements. Deux chemins sont testes ici :
  1. POST /api/v2/products/ avec isRelatedTo en LISTE -> le produit cree est
     attache a tous les events de la liste.
  2. POST /api/v2/events/{uuid}/link-product/ -> attache un (ou plusieurs)
     produit(s) DEJA cree(s) a l'evenement, sans en creer de nouveau.

Avant le correctif, isRelatedTo en liste etait accepte (201) mais n'attachait
rien, et il n'existait aucune route pour relier un produit existant.
/ Before the fix, a list isRelatedTo was accepted (201) but linked nothing, and
no route existed to attach an existing product.

NOTE TECHNIQUE : on reutilise la DB dev et on appelle les vues via APIClient
avec SERVER_NAME (le middleware tenant resout 'lespass').
/ TECHNICAL NOTE: reuse dev DB; call views via APIClient with SERVER_NAME.
"""

import uuid as uuidlib
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient


@pytest.fixture(scope="session")
def django_db_setup():
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


pytestmark = pytest.mark.django_db

HOST = "lespass.tibillet.localhost"


def _suffix():
    """Suffixe court unique pour eviter les collisions de noms.
    / Short unique suffix to avoid name collisions."""
    return uuidlib.uuid4().hex[:6]


@pytest.fixture
def link_setup():
    """
    Cree dans 'lespass' : deux evenements futurs publies, un produit existant
    (avec un tarif) attache a aucun event, et une cle API avec les permissions
    'event' ET 'product'. Nettoie en depubliant.
    / Create two future events, one existing product (with a price) attached to
    no event, and an API key with 'event' AND 'product' permissions.
    """
    from Customers.models import Client
    from BaseBillet.models import Event, Product, Price, ExternalApiKey
    from rest_framework_api_key.models import APIKey

    tenant = Client.objects.get(schema_name="lespass")
    suffix = _suffix()

    with tenant_context(tenant):
        event_a = Event.objects.create(
            name=f"Date A {suffix}",
            datetime=timezone.now() + timedelta(days=10),
            published=True,
        )
        event_b = Event.objects.create(
            name=f"Date B {suffix}",
            datetime=timezone.now() + timedelta(days=20),
            published=True,
        )
        produit = Product.objects.create(
            name=f"Pass commun {suffix}",
            categorie_article=Product.FREERES,
        )
        Price.objects.create(
            product=produit, name=f"Tarif {suffix}", prix=Decimal("0"),
        )

        api_obj, key_str = APIKey.objects.create_key(name=f"linkkey-{suffix}")
        ext_key = ExternalApiKey.objects.create(
            name=f"linkkey-{suffix}",
            key=api_obj,
            event=True,
            product=True,
        )

    data = {
        "tenant": tenant,
        "event_a": event_a,
        "event_b": event_b,
        "produit": produit,
        "key": key_str,
    }
    yield data

    with tenant_context(tenant):
        for ev in (event_a, event_b):
            ev.published = False
            ev.save(update_fields=["published"])
        ext_key.delete()
        api_obj.delete()


def _post(path, payload, key):
    """POST en resolvant le tenant via SERVER_NAME.
    / POST resolving the tenant via SERVER_NAME."""
    client = APIClient()
    return client.post(
        path, payload, format="json",
        SERVER_NAME=HOST,
        HTTP_AUTHORIZATION=f"Api-Key {key}",
    )


def test_product_create_isrelatedto_liste_attache_plusieurs_events(link_setup):
    """POST /products/ avec isRelatedTo en LISTE attache le produit cree aux
    DEUX evenements. / List isRelatedTo links the new product to both events.
    """
    from BaseBillet.models import Product

    payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": f"Billet partage {_suffix()}",
        "category": "Free booking",
        "isRelatedTo": [
            str(link_setup["event_a"].uuid),
            {"@type": "Event", "identifier": str(link_setup["event_b"].uuid)},
        ],
        "offers": [
            {"@type": "Offer", "name": "Gratuit", "price": "0.00", "priceCurrency": "EUR"}
        ],
    }
    response = _post("/api/v2/products/", payload, link_setup["key"])
    assert response.status_code == 201, f"{response.status_code} {response.data}"

    with tenant_context(link_setup["tenant"]):
        produit = Product.objects.get(name=payload["name"])
        # Le produit est bien rattache aux DEUX events.
        # / The product is attached to BOTH events.
        assert link_setup["event_a"].products.filter(pk=produit.pk).exists()
        assert link_setup["event_b"].products.filter(pk=produit.pk).exists()


def test_link_product_attache_produit_existant(link_setup):
    """POST /events/{uuid}/link-product/ avec productId attache un produit
    EXISTANT a l'evenement. / link-product attaches an EXISTING product.
    """
    payload = {"productId": str(link_setup["produit"].uuid)}
    response = _post(
        f"/api/v2/events/{link_setup['event_a'].uuid}/link-product/",
        payload, link_setup["key"],
    )
    assert response.status_code == 200, f"{response.status_code} {response.data}"

    with tenant_context(link_setup["tenant"]):
        assert link_setup["event_a"].products.filter(pk=link_setup["produit"].pk).exists()


def test_link_product_meme_produit_sur_deux_events(link_setup):
    """Le MEME produit existant peut etre attache a deux evenements via deux
    appels link-product. / The SAME product can be attached to two events.
    """
    produit_uuid = str(link_setup["produit"].uuid)
    r1 = _post(
        f"/api/v2/events/{link_setup['event_a'].uuid}/link-product/",
        {"productId": produit_uuid}, link_setup["key"],
    )
    r2 = _post(
        f"/api/v2/events/{link_setup['event_b'].uuid}/link-product/",
        {"productId": produit_uuid}, link_setup["key"],
    )
    assert r1.status_code == 200, f"{r1.status_code} {r1.data}"
    assert r2.status_code == 200, f"{r2.status_code} {r2.data}"

    with tenant_context(link_setup["tenant"]):
        assert link_setup["event_a"].products.filter(pk=link_setup["produit"].pk).exists()
        assert link_setup["event_b"].products.filter(pk=link_setup["produit"].pk).exists()


def test_link_product_liste_productids(link_setup):
    """link-product accepte une LISTE de produits (productIds).
    / link-product accepts a LIST of products (productIds).

    On cree un 2e produit a la volee et on attache les deux d'un coup.
    / Create a 2nd product on the fly and attach both at once.
    """
    from BaseBillet.models import Product

    with tenant_context(link_setup["tenant"]):
        produit2 = Product.objects.create(
            name=f"Pass bis {_suffix()}",
            categorie_article=Product.FREERES,
        )
        produit2_uuid = str(produit2.uuid)

    payload = {"productIds": [str(link_setup["produit"].uuid), produit2_uuid]}
    response = _post(
        f"/api/v2/events/{link_setup['event_b'].uuid}/link-product/",
        payload, link_setup["key"],
    )
    assert response.status_code == 200, f"{response.status_code} {response.data}"

    with tenant_context(link_setup["tenant"]):
        attaches = link_setup["event_b"].products.values_list("pk", flat=True)
        assert link_setup["produit"].pk in attaches
        assert produit2.pk in attaches


def test_link_product_sans_identifiant_400(link_setup):
    """link-product sans aucun identifiant de produit -> 400.
    / link-product with no product identifier -> 400.
    """
    response = _post(
        f"/api/v2/events/{link_setup['event_a'].uuid}/link-product/",
        {}, link_setup["key"],
    )
    assert response.status_code == 400


def test_link_product_uuid_inexistant_400(link_setup):
    """link-product avec un uuid de produit inexistant -> 400.
    / link-product with a non-existent product uuid -> 400.
    """
    response = _post(
        f"/api/v2/events/{link_setup['event_a'].uuid}/link-product/",
        {"productId": str(uuidlib.uuid4())}, link_setup["key"],
    )
    assert response.status_code == 400
