"""
tests/pytest/test_kiosk_models.py — Tests unitaires modeles kiosk (CHANTIER-01).
tests/pytest/test_kiosk_models.py — Unit tests for kiosk models (CHANTIER-01).

Lancement / Run:
    docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_kiosk_models.py -v --api-key dummy
"""

import pytest
from django_tenants.utils import tenant_context
from django.test import override_settings
from unittest.mock import patch

from Customers.models import Client
from kiosk.models import StripeLocation, Terminal, PaymentsIntent


@pytest.fixture
def tenant():
    # Tenant de dev. Aligner le schema_name sur test_fedow_core.py si different.
    return Client.objects.get(schema_name="lespass")


@pytest.fixture
def clean_kiosk(tenant):
    """Nettoie les objets kiosk prefixes TEST_ avant ET apres (DB dev partagee).
    Ordre : PaymentsIntent -> Terminal -> StripeLocation (FK PROTECT)."""
    def _clean():
        with tenant_context(tenant):
            PaymentsIntent.objects.filter(terminal__name__startswith="TEST_").delete()
            Terminal.objects.filter(name__startswith="TEST_").delete()
            StripeLocation.objects.filter(name__startswith="TEST_").delete()
    _clean()
    yield
    _clean()


@pytest.mark.django_db
def test_stripe_location_creation(tenant, clean_kiosk):
    """Une StripeLocation se cree (is_primary_location=False pour ne pas percuter
    la vraie location primaire). / A StripeLocation is created (non-primary)."""
    with tenant_context(tenant):
        loc = StripeLocation.objects.create(
            name="TEST_loc", stripe_id="tml_fake123", is_primary_location=False,
        )
        assert loc.stripe_id == "tml_fake123"
        assert str(loc) == "TEST_loc"


@pytest.mark.django_db
def test_terminal_creation_wisepos(tenant, clean_kiosk):
    """Un Terminal WisePOS se cree, type par defaut = STRIPE_WISEPOS.
    A WisePOS Terminal is created, default type = STRIPE_WISEPOS."""
    with tenant_context(tenant):
        terminal = Terminal.objects.create(name="TEST_Borne1", registration_code="simulated-wpe")
        assert terminal.type == Terminal.STRIPE_WISEPOS
        assert terminal.archived is False
        assert terminal.term_user is None  # lien borne optionnel a la creation


@pytest.mark.django_db
@override_settings(DEMO=True)
def test_payments_intent_send_to_terminal_demo(tenant, clean_kiosk):
    """En DEMO, send_to_terminal simule un PI Stripe et passe IN_PROGRESS.
    In DEMO mode, send_to_terminal fakes a Stripe PI and moves to IN_PROGRESS."""
    with tenant_context(tenant):
        terminal = Terminal.objects.create(name="TEST_BorneDEMO")
        pi = PaymentsIntent.objects.create(amount=500, terminal=terminal)
        assert pi.status == PaymentsIntent.REQUIRES_PAYMENT_METHOD
        pi.send_to_terminal(terminal)
        pi.refresh_from_db()
        assert pi.status == PaymentsIntent.IN_PROGRESS
        assert pi.payment_intent_stripe_id  # renseigné par la simulation


@pytest.mark.django_db
def test_terminal_pairing_sets_stripe_id(tenant, clean_kiosk):
    """L'appairage (get_stripe_id) renseigne le stripe_id depuis le reader Stripe créé.
    Pairing (get_stripe_id) sets stripe_id from the created Stripe reader."""
    with tenant_context(tenant):
        terminal = Terminal.objects.create(name="TEST_BorneAppairage", registration_code="simulated-wpe")
        with patch("kiosk.models.StripeLocation.get_primary_location") as mock_loc, \
             patch("stripe.terminal.Reader.create") as mock_create, \
             patch("root_billet.models.RootConfiguration.get_solo") as mock_root:
            mock_loc.return_value = type("L", (), {"stripe_id": "tml_fake"})()
            mock_root.return_value.get_stripe_api.return_value = "sk_test_x"
            mock_create.return_value = type("R", (), {"id": "tmr_fake123"})()
            stripe_id = terminal.get_stripe_id()
        assert stripe_id == "tmr_fake123"
        assert terminal.stripe_id == "tmr_fake123"
