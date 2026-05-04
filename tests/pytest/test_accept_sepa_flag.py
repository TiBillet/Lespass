"""
Tests du flag accept_sepa sur CreationPaiementStripe.
Session 03 — Tâche 3.3.

Run:
    poetry run pytest -q tests/pytest/test_accept_sepa_flag.py
"""
import pytest
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
def config_sepa_on(tenant_context_lespass):
    """Active SEPA dans la config (et restore en teardown).
    / Enable SEPA in config (restore on teardown).

    Note : on passe par .filter(...).update(...) pour bypasser Configuration.save()
    qui valide l'activation SEPA contre le vrai compte Stripe (erreur en test).
    / We use .filter(...).update(...) to bypass Configuration.save() which validates
    SEPA activation against the real Stripe account (fails in tests).
    """
    from BaseBillet.models import Configuration
    config = Configuration.get_solo()
    original = config.stripe_accept_sepa
    Configuration.objects.filter(pk=config.pk).update(stripe_accept_sepa=True)
    # Rafraichir l'instance retournee / refresh the yielded instance
    config.refresh_from_db()
    yield config
    Configuration.objects.filter(pk=config.pk).update(stripe_accept_sepa=original)


def _make_creator_stub(reservation=None, accept_sepa=None):
    """
    Construit une fausse instance CreationPaiementStripe juste assez peuplée
    pour appeler dict_checkout_creator() sans toucher à Stripe.
    / Build a fake CreationPaiementStripe instance populated enough to call
    dict_checkout_creator() without hitting Stripe.
    """
    from unittest.mock import MagicMock
    from BaseBillet.models import Configuration
    from PaiementStripe.views import CreationPaiementStripe

    # On crée l'instance sans __init__ (évite l'appel Stripe)
    # / Create instance without __init__ (avoid Stripe call)
    instance = CreationPaiementStripe.__new__(CreationPaiementStripe)
    instance.user = MagicMock(email="test@example.org", pk=1)
    instance.reservation = reservation
    instance.source = "F"
    instance.absolute_domain = "https://example.org/"
    instance.success_url = "ok/"
    instance.cancel_url = "ko/"
    instance.paiement_stripe_db = MagicMock(uuid="00000000")
    instance.line_items = []
    instance.mode = "payment"
    instance.metadata = {"tenant": "test"}
    instance.stripe_connect_account = "acct_x"
    # Rafraichir depuis la DB pour lire la valeur courante de stripe_accept_sepa
    # (get_solo() peut renvoyer un cache solo, d'ou le refresh_from_db).
    # / Refresh from DB to read the current stripe_accept_sepa value
    # (get_solo() may return a cached instance, hence refresh_from_db).
    instance.config = Configuration.get_solo()
    instance.config.refresh_from_db()
    instance.accept_sepa = accept_sepa
    return instance


@pytest.mark.django_db
def test_accept_sepa_none_legacy_sans_reservation_sepa_autorise(config_sepa_on):
    """
    Legacy (accept_sepa=None) + reservation=None + config SEPA ON → sepa_debit dans les methods.
    / Legacy + reservation=None + config SEPA ON → sepa_debit in methods.
    """
    instance = _make_creator_stub(reservation=None, accept_sepa=None)
    data = instance.dict_checkout_creator()
    assert "sepa_debit" in data["payment_method_types"]


@pytest.mark.django_db
def test_accept_sepa_none_legacy_avec_reservation_pas_de_sepa(config_sepa_on):
    """
    Legacy + reservation set → pas de sepa_debit.
    / Legacy + reservation set → no sepa_debit.
    """
    from unittest.mock import MagicMock
    reservation = MagicMock(uuid="reservation-x")
    instance = _make_creator_stub(reservation=reservation, accept_sepa=None)
    data = instance.dict_checkout_creator()
    assert "sepa_debit" not in data["payment_method_types"]


@pytest.mark.django_db
def test_accept_sepa_false_force_refus_meme_sans_reservation(config_sepa_on):
    """
    Flag False → pas de sepa_debit, même si reservation=None.
    Cas panier avec billets.
    / Flag False → no sepa_debit even if reservation=None. Cart-with-tickets case.
    """
    instance = _make_creator_stub(reservation=None, accept_sepa=False)
    data = instance.dict_checkout_creator()
    assert "sepa_debit" not in data["payment_method_types"]


@pytest.mark.django_db
def test_accept_sepa_true_force_autorisation(config_sepa_on):
    """
    Flag True → sepa_debit activé.
    Cas adhésion-only via panier.
    / Flag True → sepa_debit enabled. Standalone adhesion case via cart.
    """
    instance = _make_creator_stub(reservation=None, accept_sepa=True)
    data = instance.dict_checkout_creator()
    assert "sepa_debit" in data["payment_method_types"]


@pytest.mark.django_db
def test_accept_sepa_true_mais_config_off_ignore(tenant_context_lespass):
    """
    Flag True mais config SEPA OFF → pas de sepa_debit.
    / Flag True but config SEPA OFF → no sepa_debit.
    """
    from BaseBillet.models import Configuration
    config = Configuration.get_solo()
    original = config.stripe_accept_sepa
    # Bypass save() pour eviter la validation Stripe
    # / Bypass save() to avoid Stripe validation
    Configuration.objects.filter(pk=config.pk).update(stripe_accept_sepa=False)
    try:
        instance = _make_creator_stub(reservation=None, accept_sepa=True)
        data = instance.dict_checkout_creator()
        assert "sepa_debit" not in data["payment_method_types"]
    finally:
        Configuration.objects.filter(pk=config.pk).update(stripe_accept_sepa=original)
