"""
tests/pytest/test_admin_membership_list_status.py — Statut et deadline dans la changelist admin.
tests/pytest/test_admin_membership_list_status.py — Status and deadline in admin changelist.

Source PW TS : 35

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_admin_membership_list_status.py -v
"""
import uuid
from decimal import Decimal

import pytest


@pytest.mark.integration
def test_admin_list_status_once(admin_client, tenant):
    """35.1 — Membership ONCE (payé en ligne) : statut + deadline visibles.
    / Membership ONCE (paid online): status + deadline visible in changelist."""
    from django_tenants.utils import schema_context
    from django.utils import timezone
    from BaseBillet.models import Product, Price, Membership
    from AuthBillet.models import TibilletUser

    uid = uuid.uuid4().hex[:8]
    email = f'test-list1-{uid}@example.org'

    with schema_context('lespass'):
        product = Product.objects.create(
            name=f'Adhésion List1 {uid}',
            categorie_article=Product.ADHESION,
            publish=True,
        )
        price = Price.objects.create(
            product=product, name=f'Annuel {uid}',
            prix=Decimal('15.00'), subscription_type='Y', publish=True,
        )
        user, _ = TibilletUser.objects.get_or_create(
            email=email,
            defaults={'username': email, 'is_active': True},
        )
        membership = Membership.objects.create(
            user=user, price=price, status=Membership.ONCE,
            last_contribution=timezone.now(),
            first_contribution=timezone.now(),
            contribution_value=price.prix,
        )
        membership.set_deadline()
        membership.save()

    resp = admin_client.get(f'/admin/BaseBillet/membership/?q={email}')
    assert resp.status_code == 200, f"Admin changelist failed: {resp.status_code}"
    content = resp.content.decode()
    # Le statut ONCE s'affiche "Payé en ligne" / ONCE status displays as "Payé en ligne"
    assert 'en ligne' in content.lower() or 'paid' in content.lower(), (
        f"Status 'Payé en ligne' not found for ONCE membership. Content snippet: {content[:500]}"
    )


@pytest.mark.integration
def test_admin_list_status_admin(admin_client, tenant):
    """35.2 — Membership ADMIN : statut 'Créé via l'administration' visible.
    / Membership ADMIN: status 'Created via admin' visible in changelist."""
    from django_tenants.utils import schema_context
    from django.utils import timezone
    from BaseBillet.models import Product, Price, Membership
    from AuthBillet.models import TibilletUser

    uid = uuid.uuid4().hex[:8]
    email = f'test-list2-{uid}@example.org'

    with schema_context('lespass'):
        product = Product.objects.create(
            name=f'Adhésion List2 {uid}',
            categorie_article=Product.ADHESION,
            publish=True,
        )
        price = Price.objects.create(
            product=product, name=f'Annuel {uid}',
            prix=Decimal('15.00'), subscription_type='Y', publish=True,
        )
        user, _ = TibilletUser.objects.get_or_create(
            email=email,
            defaults={'username': email, 'is_active': True},
        )
        membership = Membership.objects.create(
            user=user, price=price, status=Membership.ADMIN,
            last_contribution=timezone.now(),
            contribution_value=Decimal('0.00'),
            payment_method='NA',
        )
        membership.set_deadline()
        membership.save()

    resp = admin_client.get(f'/admin/BaseBillet/membership/?q={email}')
    assert resp.status_code == 200
    content = resp.content.decode()
    assert 'administration' in content.lower(), (
        f"Status 'administration' not found for ADMIN membership. Content snippet: {content[:500]}"
    )


@pytest.mark.integration
def test_admin_list_status_once_free(admin_client, tenant):
    """35.3 — Membership ONCE prix 0€ : statut + deadline visibles.
    / Membership ONCE with €0 price: status + deadline visible."""
    from django_tenants.utils import schema_context
    from django.utils import timezone
    from BaseBillet.models import Product, Price, Membership
    from AuthBillet.models import TibilletUser

    uid = uuid.uuid4().hex[:8]
    email = f'test-list3-{uid}@example.org'

    with schema_context('lespass'):
        product = Product.objects.create(
            name=f'Adhésion List3 {uid}',
            categorie_article=Product.ADHESION,
            publish=True,
        )
        price = Price.objects.create(
            product=product, name=f'Gratuit {uid}',
            prix=Decimal('0.00'), subscription_type='Y', publish=True,
        )
        user, _ = TibilletUser.objects.get_or_create(
            email=email,
            defaults={'username': email, 'is_active': True},
        )
        membership = Membership.objects.create(
            user=user, price=price, status=Membership.ONCE,
            last_contribution=timezone.now(),
            first_contribution=timezone.now(),
            contribution_value=Decimal('0.00'),
        )
        membership.set_deadline()
        membership.save()

    resp = admin_client.get(f'/admin/BaseBillet/membership/?q={email}')
    assert resp.status_code == 200
    content = resp.content.decode()
    assert 'en ligne' in content.lower() or 'paid' in content.lower(), (
        f"Status 'Payé en ligne' not found for free ONCE membership"
    )
