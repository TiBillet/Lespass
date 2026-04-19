"""
Tests du post_save Paiement_stripe → Commande.PAID.
Session 03 — Tâche 3.2.

Run:
    poetry run pytest -q tests/pytest/test_commande_post_save_paid.py
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
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
def user_acheteur(tenant_context_lespass):
    from AuthBillet.models import TibilletUser
    user = TibilletUser.objects.create(
        email=f"ps-{uuid.uuid4()}@example.org",
        username=f"ps-{uuid.uuid4()}",
    )
    yield user
    try:
        from django.db.models import Q
        from BaseBillet.models import (
            Commande, LigneArticle, Membership, Paiement_stripe, Reservation,
        )
        LigneArticle.objects.filter(
            Q(reservation__user_commande=user) | Q(membership__user=user)
        ).delete()
        Reservation.objects.filter(user_commande=user).delete()
        Membership.objects.filter(user=user).delete()
        Commande.objects.filter(user=user).delete()
        Paiement_stripe.objects.filter(user=user).delete()
        user.delete()
    except Exception:
        pass


@pytest.mark.django_db
def test_paiement_valid_bascule_commande_en_paid(user_acheteur, tenant_context_lespass):
    """
    Quand un Paiement_stripe passe à VALID, la Commande liée passe à PAID + paid_at=now.
    / When Paiement_stripe goes to VALID, the linked Commande goes to PAID + paid_at=now.
    """
    from BaseBillet.models import Commande, Paiement_stripe

    paiement = Paiement_stripe.objects.create(
        user=user_acheteur, source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.PENDING,
    )
    commande = Commande.objects.create(
        user=user_acheteur, email_acheteur=user_acheteur.email,
        first_name="A", last_name="B",
        status=Commande.PENDING,
        paiement_stripe=paiement,
    )

    paiement.status = Paiement_stripe.VALID
    paiement.save()

    commande.refresh_from_db()
    assert commande.status == Commande.PAID
    assert commande.paid_at is not None


@pytest.mark.django_db
def test_paiement_sans_commande_ne_plante_pas(user_acheteur, tenant_context_lespass):
    """
    Un Paiement_stripe VALID sans Commande associée (flow legacy) ne lève pas d'exception.
    / A VALID Paiement_stripe without linked Commande (legacy flow) raises no exception.
    """
    from BaseBillet.models import Paiement_stripe

    paiement = Paiement_stripe.objects.create(
        user=user_acheteur, source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.PAID,
    )
    # Pas de Commande attachée / No linked Commande
    paiement.status = Paiement_stripe.VALID
    paiement.save()  # doit passer sans erreur


@pytest.mark.django_db
def test_paiement_autre_status_ne_bascule_pas_commande(
    user_acheteur, tenant_context_lespass,
):
    """
    Si le Paiement_stripe passe à PENDING ou PAID (pas VALID), la Commande reste en PENDING.
    / If Paiement_stripe goes to PENDING or PAID (not VALID), Commande stays PENDING.
    """
    from BaseBillet.models import Commande, Paiement_stripe

    paiement = Paiement_stripe.objects.create(
        user=user_acheteur, source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.PENDING,
    )
    commande = Commande.objects.create(
        user=user_acheteur, email_acheteur=user_acheteur.email,
        first_name="X", last_name="Y",
        status=Commande.PENDING,
        paiement_stripe=paiement,
    )
    # Transition non VALID / Non-VALID transition
    paiement.status = Paiement_stripe.PAID
    paiement.save()

    commande.refresh_from_db()
    assert commande.status == Commande.PENDING
    assert commande.paid_at is None


@pytest.mark.django_db
def test_paiement_deja_valid_ne_re_bascule_pas(user_acheteur, tenant_context_lespass):
    """
    Si la Commande est déjà PAID, le save ne modifie pas paid_at (idempotence).
    / If Commande is already PAID, save doesn't modify paid_at (idempotence).
    """
    from BaseBillet.models import Commande, Paiement_stripe

    paiement = Paiement_stripe.objects.create(
        user=user_acheteur, source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.VALID,
    )
    initial_paid_at = timezone.now() - timedelta(hours=1)
    commande = Commande.objects.create(
        user=user_acheteur, email_acheteur=user_acheteur.email,
        first_name="I", last_name="J",
        status=Commande.PAID,
        paid_at=initial_paid_at,
        paiement_stripe=paiement,
    )
    # Re-save du paiement VALID / Re-save VALID payment
    paiement.save()

    commande.refresh_from_db()
    # paid_at n'a pas été écrasé / paid_at not overwritten
    assert commande.paid_at == initial_paid_at
