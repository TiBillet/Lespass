"""
tests/pytest/test_admin_membership_custom_form.py — Affichage custom_form dans l'admin membership.
tests/pytest/test_admin_membership_custom_form.py — custom_form display in admin membership change page.

Source PW TS : 26

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_admin_membership_custom_form.py -v
"""
import uuid
from decimal import Decimal

import pytest


@pytest.mark.integration
def test_custom_form_visible_dans_admin(admin_client, tenant):
    """26 — Membership avec custom_form : la valeur s'affiche dans la page admin change.
    / Membership with custom_form: value is displayed in admin change page."""
    from django_tenants.utils import schema_context
    from django.utils import timezone
    from BaseBillet.models import Product, Price, Membership, ProductFormField
    from AuthBillet.models import TibilletUser

    uid = uuid.uuid4().hex[:8]
    email = f'test-custom-{uid}@example.org'

    with schema_context('lespass'):
        product = Product.objects.create(
            name=f'Adhésion Custom Form {uid}',
            categorie_article=Product.ADHESION,
            publish=True,
        )
        price = Price.objects.create(
            product=product, name=f'Gratuit Annuel {uid}',
            prix=Decimal('0.00'), subscription_type='Y', publish=True,
        )
        ProductFormField.objects.create(
            product=product,
            label='Pseudonyme',
            name=f'pseudonyme_{uid}',
            field_type='ST',
            required=True,
        )
        user, _ = TibilletUser.objects.get_or_create(
            email=email,
            defaults={'username': email, 'is_active': True},
        )
        membership = Membership.objects.create(
            user=user, price=price, status=Membership.ONCE,
            last_contribution=timezone.now(),
            contribution_value=Decimal('0.00'),
            custom_form={'pseudonyme': 'TestValue'},
        )
        membership_pk = membership.pk

    # Accéder à la page de modification admin
    # / Access the admin change page
    resp = admin_client.get(f'/admin/BaseBillet/membership/{membership_pk}/change/')
    assert resp.status_code == 200, (
        f"Admin change page failed: {resp.status_code}"
    )
    content = resp.content.decode()
    assert 'TestValue' in content, (
        f"Custom form value 'TestValue' not found in admin change page"
    )
