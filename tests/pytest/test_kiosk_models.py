"""
tests/pytest/test_kiosk_models.py — Tests unitaires modeles kiosk (CHANTIER-01).
tests/pytest/test_kiosk_models.py — Unit tests for kiosk models (CHANTIER-01).

Lancement / Run:
    docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_kiosk_models.py -v --api-key dummy
"""

import pytest
from django_tenants.utils import tenant_context
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
def test_payments_intent_send_to_terminal(tenant, clean_kiosk):
    """send_to_terminal cree le PaymentIntent chez Stripe, l'envoie au reader et
    passe IN_PROGRESS. Stripe est mocke (aucun appel reseau dans les tests).
    / send_to_terminal creates the Stripe PaymentIntent, pushes it to the reader
    and moves to IN_PROGRESS. Stripe is mocked (no network call in tests)."""
    with tenant_context(tenant):
        terminal = Terminal.objects.create(name="TEST_BorneTPE", stripe_id="tmr_fake123")
        pi = PaymentsIntent.objects.create(amount=500, terminal=terminal)
        assert pi.status == PaymentsIntent.REQUIRES_PAYMENT_METHOD

        with patch("root_billet.models.RootConfiguration.get_solo") as mock_root, \
             patch("stripe.terminal.Reader.retrieve") as mock_retrieve, \
             patch("stripe.PaymentIntent.create") as mock_pi_create, \
             patch("stripe.terminal.Reader.process_payment_intent") as mock_process:
            mock_root.return_value.get_stripe_api.return_value = "sk_test_x"
            mock_retrieve.return_value = type("R", (), {"status": "online"})()
            mock_pi_create.return_value = type("PI", (), {"id": "pi_fake123"})()

            pi.send_to_terminal(terminal)

        pi.refresh_from_db()
        assert pi.status == PaymentsIntent.IN_PROGRESS
        assert pi.payment_intent_stripe_id == "pi_fake123"
        # Le PaymentIntent est bien pousse vers le reader appaire.
        # / The PaymentIntent is actually pushed to the paired reader.
        mock_process.assert_called_once()


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


@pytest.mark.django_db
def test_terminal_form_invalide_si_stripe_refuse_le_code(tenant, clean_kiosk):
    """Un code d'enregistrement refuse par Stripe invalide le formulaire d'admin :
    l'erreur est portee par le champ registration_code et aucun TPE n'est cree.
    / A registration code rejected by Stripe invalidates the admin form: the error is
    attached to registration_code and no terminal is created."""
    from kiosk.admin import TerminalForm

    with tenant_context(tenant):
        with patch("kiosk.models.StripeLocation.get_primary_location") as mock_loc, \
             patch("root_billet.models.RootConfiguration.get_solo") as mock_root, \
             patch("stripe.terminal.Reader.create") as mock_create:
            mock_loc.return_value = type("L", (), {"stripe_id": "tml_fake"})()
            mock_root.return_value.get_stripe_api.return_value = "sk_test_x"
            mock_create.side_effect = Exception("No such registration code")

            form = TerminalForm(data={
                "name": "TEST_BorneRefusee",
                "type": Terminal.STRIPE_WISEPOS,
                "registration_code": "code-bidon",
            })
            assert form.is_valid() is False

        assert "registration_code" in form.errors
        assert Terminal.objects.filter(name="TEST_BorneRefusee").exists() is False


@pytest.mark.django_db
def test_terminal_form_valide_appaire_et_enregistre_le_stripe_id(tenant, clean_kiosk):
    """Un code accepte par Stripe rend le formulaire valide et le stripe_id est
    enregistre a la sauvegarde. / A code accepted by Stripe makes the form valid and
    the stripe_id is persisted on save."""
    from kiosk.admin import TerminalForm

    with tenant_context(tenant):
        with patch("kiosk.models.StripeLocation.get_primary_location") as mock_loc, \
             patch("root_billet.models.RootConfiguration.get_solo") as mock_root, \
             patch("stripe.terminal.Reader.create") as mock_create:
            mock_loc.return_value = type("L", (), {"stripe_id": "tml_fake"})()
            mock_root.return_value.get_stripe_api.return_value = "sk_test_x"
            mock_create.return_value = type("R", (), {"id": "tmr_ok456"})()

            form = TerminalForm(data={
                "name": "TEST_BorneAcceptee",
                "type": Terminal.STRIPE_WISEPOS,
                "registration_code": "simulated-wpe",
            })
            assert form.is_valid() is True, form.errors
            terminal = form.save()

        assert terminal.stripe_id == "tmr_ok456"
        assert Terminal.objects.get(name="TEST_BorneAcceptee").stripe_id == "tmr_ok456"
