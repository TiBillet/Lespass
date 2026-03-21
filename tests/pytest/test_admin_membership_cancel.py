"""
tests/pytest/test_admin_membership_cancel.py — Annulation d'adhésion via HTMX admin.
tests/pytest/test_admin_membership_cancel.py — Membership cancellation via admin HTMX endpoint.

Source PW TS : 34

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_admin_membership_cancel.py -v
"""
import uuid
from decimal import Decimal

import pytest


@pytest.mark.integration
def test_cancel_membership_sans_avoir(admin_client, tenant):
    """34.1 — Annuler un membership gratuit sans avoir → statut ADMIN_CANCELED.
    / Cancel a free membership without credit note → status ADMIN_CANCELED."""
    from django_tenants.utils import schema_context
    from django.utils import timezone
    from BaseBillet.models import Product, Price, Membership
    from AuthBillet.models import TibilletUser

    uid = uuid.uuid4().hex[:8]
    email = f'test-canc-{uid}@example.org'

    with schema_context('lespass'):
        product = Product.objects.create(
            name=f'Adhésion Cancel Free {uid}',
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
            contribution_value=Decimal('0.00'),
        )
        membership_pk = membership.pk

    # POST annulation sans avoir / POST cancel without credit note
    resp = admin_client.post(f'/memberships/{membership_pk}/cancel/')
    # La vue retourne 204 avec HX-Redirect / View returns 204 with HX-Redirect
    assert resp.status_code == 204, (
        f"Cancel should return 204, got {resp.status_code}"
    )
    assert 'HX-Redirect' in resp.headers, "Response should have HX-Redirect header"

    with schema_context('lespass'):
        membership = Membership.objects.get(pk=membership_pk)
        assert membership.status == Membership.ADMIN_CANCELED, (
            f"Expected ADMIN_CANCELED, got {membership.status}"
        )
        assert membership.archiver is True


@pytest.mark.integration
def test_cancel_membership_avec_avoir(admin_client, tenant):
    """34.2 — Annuler un membership payé avec avoir → ADMIN_CANCELED + LigneArticle CREDIT_NOTE.
    / Cancel a paid membership with credit note → ADMIN_CANCELED + LigneArticle CREDIT_NOTE."""
    from django_tenants.utils import schema_context
    from django.utils import timezone
    from BaseBillet.models import (
        Product, Price, Membership, LigneArticle,
        ProductSold, PriceSold, SaleOrigin,
    )
    from AuthBillet.models import TibilletUser

    uid = uuid.uuid4().hex[:8]
    email = f'test-cancp-{uid}@example.org'

    with schema_context('lespass'):
        product = Product.objects.create(
            name=f'Adhésion Cancel Paid {uid}',
            categorie_article=Product.ADHESION,
            publish=True,
        )
        price = Price.objects.create(
            product=product, name=f'Annuel {uid}',
            prix=Decimal('30.00'), subscription_type='Y', publish=True,
        )
        user, _ = TibilletUser.objects.get_or_create(
            email=email,
            defaults={'username': email, 'is_active': True},
        )
        membership = Membership.objects.create(
            user=user, price=price, status=Membership.ONCE,
            last_contribution=timezone.now(),
            first_contribution=timezone.now(),
            contribution_value=Decimal('30.00'),
            payment_method='CA',
        )

        # Créer une LigneArticle payée (VALID) pour ce membership
        # / Create a paid LigneArticle (VALID) for this membership
        product_sold = ProductSold.objects.create(product=product)
        price_sold = PriceSold.objects.create(
            productsold=product_sold,
            price=price,
            prix=price.prix,
            qty_solded=0,
        )
        ligne = LigneArticle.objects.create(
            pricesold=price_sold,
            qty=1,
            membership=membership,
            amount=3000,
            payment_method='CA',
            status=LigneArticle.CREATED,
            sale_origin=SaleOrigin.ADMIN,
        )
        # Passer en VALID en bypassant les signaux
        # / Set to VALID bypassing signals
        LigneArticle.objects.filter(pk=ligne.pk).update(status=LigneArticle.VALID)

        membership_pk = membership.pk
        ligne_pk = ligne.pk

    # POST annulation avec avoir / POST cancel with credit note
    resp = admin_client.post(
        f'/memberships/{membership_pk}/cancel/',
        data={'with_credit_note': '1'},
    )
    assert resp.status_code == 204, (
        f"Cancel should return 204, got {resp.status_code}"
    )

    with schema_context('lespass'):
        membership = Membership.objects.get(pk=membership_pk)
        assert membership.status == Membership.ADMIN_CANCELED
        assert membership.archiver is True

        # L'avoir (credit note) doit exister
        # / Credit note should exist
        credit_notes = LigneArticle.objects.filter(
            membership=membership,
            status=LigneArticle.CREDIT_NOTE,
            credit_note_for_id=ligne_pk,
        )
        assert credit_notes.exists(), "Credit note LigneArticle should exist"
        avoir = credit_notes.first()
        assert avoir.qty == -1, f"Credit note qty should be -1, got {avoir.qty}"
