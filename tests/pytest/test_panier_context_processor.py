"""
Tests du context processor panier.
Session 04 — Tâche 4.1.

Run:
    poetry run pytest -q tests/pytest/test_panier_context_processor.py
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
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
def request_with_session(tenant_context_lespass):
    from django.contrib.auth.models import AnonymousUser
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory
    factory = RequestFactory()
    request = factory.get('/')
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    request.user = AnonymousUser()
    return request


@pytest.mark.django_db
def test_panier_context_panier_vide(request_with_session):
    """Panier vide → count=0, is_empty=True.
    / Empty cart → count=0, is_empty=True."""
    from BaseBillet.context_processors import panier_context
    ctx = panier_context(request_with_session)
    assert 'panier' in ctx
    assert ctx['panier']['count'] == 0
    assert ctx['panier']['is_empty'] is True
    assert ctx['panier']['items'] == []
    assert ctx['panier']['items_with_details'] == []
    assert ctx['panier']['total_ttc'] == Decimal('0.00')
    assert ctx['panier']['adhesions_product_ids'] == []
    assert ctx['panier']['promo_code_name'] is None


@pytest.mark.django_db
def test_panier_context_avec_billet(request_with_session):
    """Panier avec 1 billet → count=qty, items_with_details enrichi.
    / Cart with 1 ticket → count=qty, items_with_details enriched."""
    from BaseBillet.models import Event, Price, Product
    from BaseBillet.context_processors import panier_context
    from BaseBillet.services_panier import PanierSession

    event = Event.objects.create(
        name=f"CtxE-{uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=3),
        jauge_max=50,
    )
    prod = Product.objects.create(
        name=f"B {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(prod)
    price = Price.objects.create(
        product=prod, name="Plein", prix=Decimal("10.00"), publish=True,
    )

    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=2)

    ctx = panier_context(request_with_session)
    assert ctx['panier']['count'] == 2
    assert ctx['panier']['is_empty'] is False
    assert ctx['panier']['total_ttc'] == Decimal('20.00')  # 2 x 10€

    items_details = ctx['panier']['items_with_details']
    assert len(items_details) == 1
    assert items_details[0]['type'] == 'ticket'
    assert items_details[0]['event'] == event
    assert items_details[0]['price'] == price
    assert items_details[0]['qty'] == 2


@pytest.mark.django_db
def test_panier_context_avec_adhesion(request_with_session):
    """Panier avec adhesion → adhesions_product_ids inclut le product adhesion.
    / Cart with membership → adhesions_product_ids includes the adhesion product."""
    from BaseBillet.models import Price, Product
    from BaseBillet.context_processors import panier_context
    from BaseBillet.services_panier import PanierSession

    prod = Product.objects.create(
        name=f"A {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price = Price.objects.create(
        product=prod, name="Std", prix=Decimal("15.00"), publish=True,
    )

    panier = PanierSession(request_with_session)
    panier.add_membership(price.uuid)

    ctx = panier_context(request_with_session)
    assert ctx['panier']['count'] == 1
    assert prod.uuid in ctx['panier']['adhesions_product_ids']
    assert ctx['panier']['total_ttc'] == Decimal('15.00')


@pytest.mark.django_db
def test_panier_context_fail_safe_sur_exception():
    """Si une exception est levee dans le chargement du panier, on retourne un dict vide.
    / If an exception is raised during cart load, return an empty dict."""
    from BaseBillet.context_processors import panier_context

    # Request minimal sans session → should fail-safe
    # / Minimal request without session → should fail-safe
    class FakeRequest:
        pass

    ctx = panier_context(FakeRequest())
    assert ctx['panier']['count'] == 0
    assert ctx['panier']['is_empty'] is True
