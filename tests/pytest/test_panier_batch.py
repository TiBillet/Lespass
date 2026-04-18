"""
Tests du endpoint add_tickets_batch sur PanierMVT.
Session 05 — Tâche 5.1.

Run:
    poetry run pytest -q tests/pytest/test_panier_batch.py
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context


@pytest.fixture(autouse=True)
def _reset_translation_after_test():
    from django.utils import translation
    yield
    translation.deactivate()


@pytest.fixture
def tenant_context_lespass():
    from Customers.models import Client as TenantClient
    tenant = TenantClient.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        yield tenant


@pytest.fixture
def http_client(tenant_context_lespass):
    return Client(HTTP_HOST='lespass.tibillet.localhost')


@pytest.fixture
def event_avec_2_tarifs(tenant_context_lespass):
    """Event avec 1 product et 2 prices.
    / Event with 1 product and 2 prices."""
    from BaseBillet.models import Event, Price, Product

    event = Event.objects.create(
        name=f"Batch-{uuid.uuid4()}",
        slug=f"batch-{uuid.uuid4().hex[:8]}",
        datetime=timezone.now() + timedelta(days=4),
        jauge_max=100,
    )
    product = Product.objects.create(
        name=f"Billets {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(product)
    price_a = Price.objects.create(
        product=product, name="Plein", prix=Decimal("10.00"), publish=True,
    )
    price_b = Price.objects.create(
        product=product, name="Réduit", prix=Decimal("5.00"), publish=True,
    )
    return event, product, price_a, price_b


@pytest.mark.django_db
def test_batch_ajoute_plusieurs_tarifs_dun_coup(http_client, event_avec_2_tarifs):
    """POST /panier/add/tickets_batch/ avec 2 tarifs → 2 items en panier.
    / POST /panier/add/tickets_batch/ with 2 rates → 2 items in cart."""
    event, _product, price_a, price_b = event_avec_2_tarifs

    response = http_client.post('/panier/add/tickets_batch/', {
        'slug': event.slug,
        str(price_a.uuid): '2',  # 2 billets plein
        str(price_b.uuid): '1',  # 1 billet réduit
    })
    assert response.status_code == 200
    assert b"added" in response.content.lower() or b"ajout" in response.content.lower()

    session = http_client.session
    items = session.get('panier', {}).get('items', [])
    assert len(items) == 2
    qtys = {i['price_uuid']: i['qty'] for i in items}
    assert qtys[str(price_a.uuid)] == 2
    assert qtys[str(price_b.uuid)] == 1


@pytest.mark.django_db
def test_batch_event_inexistant_retourne_erreur(http_client):
    """Event slug invalide → toast error."""
    response = http_client.post('/panier/add/tickets_batch/', {
        'slug': 'does-not-exist',
        str(uuid.uuid4()): '1',
    })
    assert response.status_code == 200
    assert b"Event not found" in response.content or b"not found" in response.content.lower()


@pytest.mark.django_db
def test_batch_aucune_quantite_retourne_erreur(http_client, event_avec_2_tarifs):
    """Aucun tarif avec qty > 0 → toast 'No tickets selected'."""
    event, _product, price_a, _price_b = event_avec_2_tarifs

    response = http_client.post('/panier/add/tickets_batch/', {
        'slug': event.slug,
        str(price_a.uuid): '0',  # qty 0 ignoré
    })
    assert response.status_code == 200
    assert b"No tickets" in response.content or b"Aucun" in response.content or b"ticket" in response.content.lower()
    session = http_client.session
    assert len(session.get('panier', {}).get('items', [])) == 0


@pytest.mark.django_db
def test_batch_rollback_si_un_item_echoue(http_client, tenant_context_lespass):
    """Si un des tarifs est invalide en cours de batch, rollback total.
    / If one rate is invalid mid-batch, total rollback."""
    from BaseBillet.models import Event, Price, Product

    event = Event.objects.create(
        name=f"RB-{uuid.uuid4()}",
        slug=f"rb-{uuid.uuid4().hex[:8]}",
        datetime=timezone.now() + timedelta(days=3),
        jauge_max=100,
    )
    product = Product.objects.create(
        name=f"P {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(product)
    # price_ok
    price_ok = Price.objects.create(
        product=product, name="OK", prix=Decimal("10.00"), publish=True,
    )
    # price_invalid : non publié → add_ticket raise
    price_invalid = Price.objects.create(
        product=product, name="KO", prix=Decimal("5.00"), publish=False,
    )
    http_client = Client(HTTP_HOST='lespass.tibillet.localhost')

    response = http_client.post('/panier/add/tickets_batch/', {
        'slug': event.slug,
        str(price_ok.uuid): '1',
        str(price_invalid.uuid): '1',
    })
    assert response.status_code == 200
    # Toast d'erreur
    assert b"not available" in response.content.lower() or b"error" in response.content.lower()
    # Panier vide après rollback
    session = http_client.session
    assert len(session.get('panier', {}).get('items', [])) == 0


@pytest.mark.django_db
def test_batch_accepte_event_uuid_aussi(http_client, event_avec_2_tarifs):
    """Le batch accepte aussi `event` (uuid) a la place de `slug`.
    / Batch accepts `event` (uuid) instead of `slug`."""
    event, _product, price_a, price_b = event_avec_2_tarifs

    response = http_client.post('/panier/add/tickets_batch/', {
        'event': str(event.uuid),  # <-- uuid au lieu de slug
        str(price_a.uuid): '1',
    })
    assert response.status_code == 200
    session = http_client.session
    items = session.get('panier', {}).get('items', [])
    assert len(items) == 1
