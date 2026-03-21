"""
tests/pytest/test_sepa_duplicate_protection.py — Protection contre les paiements SEPA en double.
tests/pytest/test_sepa_duplicate_protection.py — SEPA duplicate payment protection.

Source PW TS : 36

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_sepa_duplicate_protection.py -v
"""
import os
import uuid
from decimal import Decimal

import pytest


@pytest.mark.integration
def test_template_payment_already_pending_exists():
    """36.1 — Le template payment_already_pending.html existe.
    / Template payment_already_pending.html exists."""
    import BaseBillet
    app_dir = os.path.dirname(BaseBillet.__file__)
    template_path = os.path.join(
        app_dir, 'templates', 'reunion', 'views', 'membership',
        'payment_already_pending.html',
    )
    assert os.path.isfile(template_path), (
        f"Template not found: {template_path}"
    )


@pytest.mark.integration
def test_template_payment_already_pending_data_testids():
    """36.2 — Le template contient les 4 data-testid requis.
    / Template contains the 4 required data-testid attributes."""
    import BaseBillet
    app_dir = os.path.dirname(BaseBillet.__file__)
    template_path = os.path.join(
        app_dir, 'templates', 'reunion', 'views', 'membership',
        'payment_already_pending.html',
    )
    with open(template_path, 'r') as f:
        content = f.read()

    expected_testids = [
        'membership-payment-already-pending',
        'membership-payment-pending-summary',
        'membership-payment-pending-link-memberships',
        'membership-payment-pending-link-home',
    ]
    for testid in expected_testids:
        assert testid in content, (
            f"data-testid '{testid}' not found in template"
        )


@pytest.mark.integration
def test_paid_membership_blocks_checkout(admin_client, tenant):
    """36.3 — Un membership déjà payé (ONCE) bloque l'accès au checkout Stripe.
    / An already-paid membership (ONCE) blocks Stripe checkout access."""
    from django_tenants.utils import schema_context
    from django.utils import timezone
    from BaseBillet.models import Product, Price, Membership
    from AuthBillet.models import TibilletUser

    uid = uuid.uuid4().hex[:8]
    email = f'test-sepa-{uid}@example.org'

    with schema_context('lespass'):
        product = Product.objects.create(
            name=f'Adhésion SEPA {uid}',
            categorie_article=Product.ADHESION,
            publish=True,
        )
        price = Price.objects.create(
            product=product, name=f'Annuel SEPA {uid}',
            prix=Decimal('20.00'), subscription_type='Y',
            manual_validation=True, publish=True,
        )
        user, _ = TibilletUser.objects.get_or_create(
            email=email,
            defaults={'username': email, 'is_active': True},
        )
        # Membership déjà payée (status ONCE) — ne devrait plus permettre le checkout
        # / Already-paid membership (ONCE) — should not allow checkout anymore
        membership = Membership.objects.create(
            user=user, price=price, status=Membership.ONCE,
            last_contribution=timezone.now(),
            first_contribution=timezone.now(),
            contribution_value=price.prix,
        )
        membership.set_deadline()
        membership.save()
        membership_uuid = str(membership.uuid)

    # Le checkout ne doit pas fonctionner sur une adhésion déjà payée
    # (la garde vérifie status == ADMIN_VALID uniquement)
    # La vue utilise uuid.UUID(pk) pour chercher le membership
    # / Checkout should not work on an already-paid membership
    # (guard checks status == ADMIN_VALID only)
    # View uses uuid.UUID(pk) to look up the membership
    resp = admin_client.get(
        f'/memberships/{membership_uuid}/get_checkout_for_membership/',
        follow=False,
    )
    # Le statut n'est pas ADMIN_VALID → la vue refuse (404 ou redirect ou erreur)
    # / Status is not ADMIN_VALID → view refuses (404, redirect, or error)
    assert resp.status_code != 302 or 'checkout.stripe.com' not in resp.get('Location', ''), (
        "Paid membership should not redirect to Stripe checkout"
    )
