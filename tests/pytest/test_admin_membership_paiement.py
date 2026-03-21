"""
tests/pytest/test_admin_membership_paiement.py — Paiement hors-ligne via HTMX admin.
tests/pytest/test_admin_membership_paiement.py — Offline payment via admin HTMX endpoint.

Source PW TS : 33

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_admin_membership_paiement.py -v
"""
import uuid
from decimal import Decimal

import pytest


@pytest.mark.integration
def test_paiement_especes_sur_membership(admin_client, tenant):
    """33.1 — POST espèces sur une adhésion en attente → statut ONCE + LigneArticle créée.
    / POST cash payment on pending membership → status ONCE + LigneArticle created."""
    from django_tenants.utils import schema_context
    from BaseBillet.models import Product, Price, Membership, LigneArticle
    from AuthBillet.models import TibilletUser

    uid = uuid.uuid4().hex[:8]
    email = f'test-pay-{uid}@example.org'

    with schema_context('lespass'):
        product = Product.objects.create(
            name=f'Adhésion Paiement {uid}',
            categorie_article=Product.ADHESION,
            publish=True,
        )
        price = Price.objects.create(
            product=product, name=f'Annuel {uid}',
            prix=Decimal('25.00'), subscription_type='Y', publish=True,
        )
        user, _ = TibilletUser.objects.get_or_create(
            email=email,
            defaults={'username': email, 'is_active': True},
        )
        membership = Membership.objects.create(
            user=user, price=price,
            status=Membership.ADMIN_WAITING,
            first_name='Test', last_name='Paiement',
        )
        membership_pk = membership.pk

    # POST paiement espèces / POST cash payment
    resp = admin_client.post(
        f'/memberships/{membership_pk}/ajouter_paiement/',
        data={'amount': '25.00', 'payment_method': 'CA'},
    )
    assert resp.status_code == 200, (
        f"ajouter_paiement failed: {resp.status_code} {resp.content.decode()[:300]}"
    )

    # Vérifier : statut → ONCE, LigneArticle créée
    # / Verify: status → ONCE, LigneArticle created
    with schema_context('lespass'):
        membership = Membership.objects.get(pk=membership_pk)
        assert membership.status == Membership.ONCE, (
            f"Expected ONCE, got {membership.status}"
        )
        assert LigneArticle.objects.filter(membership=membership).exists(), (
            "LigneArticle should exist after payment"
        )


@pytest.mark.integration
def test_offert_rejete_avec_montant_positif(admin_client, tenant):
    """33.2 — POST 'Offert' (NA) avec montant > 0 → erreur inline.
    / POST 'Offered' (NA) with amount > 0 → inline error."""
    from django_tenants.utils import schema_context
    from BaseBillet.models import Product, Price, Membership
    from AuthBillet.models import TibilletUser

    uid = uuid.uuid4().hex[:8]
    email = f'test-guard-{uid}@example.org'

    with schema_context('lespass'):
        product = Product.objects.create(
            name=f'Adhésion Guard {uid}',
            categorie_article=Product.ADHESION,
            publish=True,
        )
        price = Price.objects.create(
            product=product, name=f'Annuel {uid}',
            prix=Decimal('25.00'), subscription_type='Y', publish=True,
        )
        user, _ = TibilletUser.objects.get_or_create(
            email=email,
            defaults={'username': email, 'is_active': True},
        )
        membership = Membership.objects.create(
            user=user, price=price,
            status=Membership.ADMIN_WAITING,
            first_name='Guard', last_name='Test',
        )
        membership_pk = membership.pk

    # POST "Offert" avec montant positif → doit être rejeté par le serializer
    # / POST "Offered" with positive amount → should be rejected by serializer
    resp = admin_client.post(
        f'/memberships/{membership_pk}/ajouter_paiement/',
        data={'amount': '25.00', 'payment_method': 'NA'},
    )
    assert resp.status_code == 200, "Should return form with errors (200)"
    content = resp.content.decode()
    # Le message d'erreur du PaiementHorsLigneSerializer
    # / The PaiementHorsLigneSerializer error message
    assert 'Impossible' in content or 'Offert' in content or 'error' in content.lower(), (
        f"Error message not found in response. Content snippet: {content[:500]}"
    )

    # Le statut ne doit PAS avoir changé / Status should NOT have changed
    with schema_context('lespass'):
        membership = Membership.objects.get(pk=membership_pk)
        assert membership.status == Membership.ADMIN_WAITING, (
            f"Status should still be ADMIN_WAITING, got {membership.status}"
        )
