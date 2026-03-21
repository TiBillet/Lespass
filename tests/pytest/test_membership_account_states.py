"""
tests/pytest/test_membership_account_states.py — États des adhésions sur la page mon compte.
tests/pytest/test_membership_account_states.py — Membership states on user account page.

Source PW TS : 21, 22

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_membership_account_states.py -v
"""
import uuid
from decimal import Decimal

import pytest


@pytest.mark.integration
def test_account_shows_valid_membership(tenant):
    """21 — La page /my_account/membership/ affiche les adhésions de l'utilisateur.
    / The /my_account/membership/ page shows user's memberships."""
    from django.test import Client as DjangoClient
    from django_tenants.utils import schema_context
    from django.utils import timezone
    from BaseBillet.models import Product, Price, Membership
    from AuthBillet.models import TibilletUser, Wallet

    uid = uuid.uuid4().hex[:8]
    email = f'test-account-{uid}@example.org'
    product_name = f'Adhésion Account {uid}'

    with schema_context('lespass'):
        product = Product.objects.create(
            name=product_name,
            categorie_article=Product.ADHESION,
            publish=True,
        )
        price = Price.objects.create(
            product=product, name=f'Annuel {uid}',
            prix=Decimal('10.00'), subscription_type='Y', publish=True,
        )
        user, _ = TibilletUser.objects.get_or_create(
            email=email,
            defaults={'username': email, 'is_active': True},
        )
        # Wallet requis pour /my_account/ / Wallet required for /my_account/
        if not hasattr(user, 'wallet') or user.wallet is None:
            wallet = Wallet.objects.create()
            user.wallet = wallet
            user.save()

        # Ajouter le tenant dans client_achat (la vue itère sur client_achat)
        # / Add tenant to client_achat (the view iterates over client_achat)
        user.client_achat.add(tenant)

        membership = Membership.objects.create(
            user=user, price=price, status=Membership.ONCE,
            last_contribution=timezone.now(),
            first_contribution=timezone.now(),
            contribution_value=price.prix,
        )
        membership.set_deadline()
        membership.save()

    # Login hors schema_context (le middleware gère le tenant)
    # / Login outside schema_context (middleware handles tenant)
    client = DjangoClient(HTTP_HOST='lespass.tibillet.localhost')
    client.force_login(user)

    resp = client.get('/my_account/membership/')
    assert resp.status_code == 200, f"GET /my_account/membership/ failed: {resp.status_code}"
    content = resp.content.decode()
    assert product_name in content, (
        f"Product '{product_name}' not found on /my_account/membership/"
    )


@pytest.mark.integration
def test_account_shows_cancel_button_recurring(tenant):
    """22 — Adhésion récurrente avec stripe_id_subscription affiche un bouton d'annulation.
    / Recurring membership with stripe_id_subscription shows cancel button."""
    from django.test import Client as DjangoClient
    from django_tenants.utils import schema_context
    from django.utils import timezone
    from datetime import timedelta
    from BaseBillet.models import Product, Price, Membership
    from AuthBillet.models import TibilletUser, Wallet

    uid = uuid.uuid4().hex[:8]
    email = f'test-cancel-auto-{uid}@example.org'
    product_name = f'Adhésion Auto {uid}'

    with schema_context('lespass'):
        product = Product.objects.create(
            name=product_name,
            categorie_article=Product.ADHESION,
            publish=True,
        )
        price = Price.objects.create(
            product=product, name=f'Mensuelle {uid}',
            prix=Decimal('10.00'), subscription_type='M',
            recurring_payment=True, publish=True,
        )
        user, _ = TibilletUser.objects.get_or_create(
            email=email,
            defaults={'username': email, 'is_active': True},
        )
        if not hasattr(user, 'wallet') or user.wallet is None:
            wallet = Wallet.objects.create()
            user.wallet = wallet
            user.save()

        user.client_achat.add(tenant)

        membership = Membership.objects.create(
            user=user, price=price, status=Membership.ONCE,
            last_contribution=timezone.now(),
            first_contribution=timezone.now(),
            contribution_value=price.prix,
            stripe_id_subscription='sub_test_00000000',
            deadline=timezone.now() + timedelta(days=30),
        )

    client = DjangoClient(HTTP_HOST='lespass.tibillet.localhost')
    client.force_login(user)

    resp = client.get('/my_account/membership/')
    assert resp.status_code == 200
    content = resp.content.decode()
    # Le template affiche le bouton cancel quand status='A' (ONCE) + stripe_id_subscription
    # data-testid="membership-cancel-auto-{uuid}"
    # / Template shows cancel button when status='A' (ONCE) + stripe_id_subscription
    assert 'membership-cancel-auto' in content, (
        f"Cancel button not found for recurring membership. Content snippet: {content[:1000]}"
    )
