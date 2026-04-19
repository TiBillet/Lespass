"""
Tests C3 : persistance de l'URL Stripe checkout.
Session 07 — Tache 7.4.
/ Tests C3: Stripe checkout URL persistence.

Run:
    poetry run pytest -q tests/pytest/test_stripe_checkout_url.py
"""
import uuid
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


@pytest.mark.django_db
def test_paiement_stripe_a_champ_checkout_session_url(tenant_context_lespass):
    """
    Le modele Paiement_stripe a bien le champ checkout_session_url.
    / Paiement_stripe model has the checkout_session_url field.
    """
    from BaseBillet.models import Paiement_stripe
    fields = [f.name for f in Paiement_stripe._meta.get_fields()]
    assert 'checkout_session_url' in fields


@pytest.mark.django_db
def test_paiement_stripe_checkout_session_url_nullable(tenant_context_lespass):
    """
    Le champ est nullable (defaut None).
    / The field is nullable (default None).
    """
    from AuthBillet.models import TibilletUser
    from BaseBillet.models import Paiement_stripe
    user = TibilletUser.objects.create(
        email=f"c3-{uuid.uuid4()}@example.org",
        username=f"c3-{uuid.uuid4()}",
    )
    p = Paiement_stripe.objects.create(
        user=user,
        source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.PENDING,
    )
    assert p.checkout_session_url is None
    p.checkout_session_url = "https://checkout.stripe.com/c/pay/cs_test_xxx"
    p.save()
    p.refresh_from_db()
    assert p.checkout_session_url == "https://checkout.stripe.com/c/pay/cs_test_xxx"
    try:
        p.delete()
        user.delete()
    except Exception:
        pass
