"""
Tests de non-régression + nouveau flow multi-reservations sur set_ligne_article_paid().
Session 03 — Tâche 3.1.

Run:
    poetry run pytest -q tests/pytest/test_signals_cascade_multi_reservations.py
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context


@pytest.fixture(autouse=True)
def _reset_translation_after_test():
    """Reset le locale Django modifie par les signaux post-paiement.
    / Reset Django locale modified by post-payment signals."""
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
        email=f"sig-{uuid.uuid4()}@example.org",
        username=f"sig-{uuid.uuid4()}",
    )
    yield user
    # Best-effort cleanup / Cleanup best-effort
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


def _creer_paiement_avec_n_reservations(user, n_reservations=2):
    """
    Helper : crée un Paiement_stripe PENDING avec N reservations + leurs tickets
    via `LigneArticle.reservation` (nouveau flow panier), sans FK
    `Paiement_stripe.reservation` (donc =None).
    / Helper: creates a PENDING Paiement_stripe with N reservations + tickets
    via `LigneArticle.reservation` (new cart flow), without FK `Paiement_stripe.reservation`.
    """
    from ApiBillet.serializers import get_or_create_price_sold
    from BaseBillet.models import (
        Event, LigneArticle, Paiement_stripe, PaymentMethod, Price, Product,
        Reservation, SaleOrigin, Ticket,
    )

    paiement = Paiement_stripe.objects.create(
        user=user, source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.PENDING,
    )
    reservations = []
    for i in range(n_reservations):
        event = Event.objects.create(
            name=f"EvtSig-{uuid.uuid4()}",
            datetime=timezone.now() + timedelta(days=3 + i),
            jauge_max=50,
        )
        product = Product.objects.create(
            name=f"B {uuid.uuid4()}", categorie_article=Product.BILLET,
        )
        event.products.add(product)
        price = Price.objects.create(
            product=product, name="x", prix=Decimal("10.00"), publish=True,
        )
        resa = Reservation.objects.create(
            user_commande=user, event=event, status=Reservation.UNPAID,
        )
        pricesold = get_or_create_price_sold(price, event=event)
        line = LigneArticle.objects.create(
            pricesold=pricesold, amount=1000, qty=1,
            payment_method=PaymentMethod.STRIPE_NOFED,
            reservation=resa,
            paiement_stripe=paiement,
            status=LigneArticle.UNPAID,
        )
        Ticket.objects.create(
            status=Ticket.NOT_ACTIV, reservation=resa, pricesold=pricesold,
        )
        reservations.append(resa)
    return paiement, reservations


@pytest.mark.django_db
def test_legacy_mono_event_reservation_passe_en_paid(user_acheteur, tenant_context_lespass):
    """
    Flow mono-event legacy : Paiement_stripe.reservation FK set + ligne.reservation = même resa.
    Le set() dédoublonne → 1 seule reservation traitée. Comportement identique à avant.
    / Legacy mono-event: Paiement_stripe.reservation FK set + ligne.reservation = same resa.
    set() dedupes → 1 reservation processed. Identical behavior.
    """
    from ApiBillet.serializers import get_or_create_price_sold
    from BaseBillet.models import (
        Event, LigneArticle, Paiement_stripe, PaymentMethod, Price, Product,
        Reservation, Ticket,
    )

    event = Event.objects.create(
        name=f"LegacyE-{uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=2),
        jauge_max=50,
    )
    product = Product.objects.create(
        name=f"B {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(product)
    price = Price.objects.create(
        product=product, name="x", prix=Decimal("10.00"), publish=True,
    )
    resa = Reservation.objects.create(
        user_commande=user_acheteur, event=event, status=Reservation.UNPAID,
    )
    paiement = Paiement_stripe.objects.create(
        user=user_acheteur, source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.PENDING,
        reservation=resa,  # FK legacy — flow mono-event
    )
    pricesold = get_or_create_price_sold(price, event=event)
    LigneArticle.objects.create(
        pricesold=pricesold, amount=1000, qty=1,
        payment_method=PaymentMethod.STRIPE_NOFED,
        reservation=resa,  # aussi peuplée, même resa
        paiement_stripe=paiement,
        status=LigneArticle.UNPAID,
    )
    Ticket.objects.create(
        status=Ticket.NOT_ACTIV, reservation=resa, pricesold=pricesold,
    )

    # Passage PENDING → PAID déclenche set_ligne_article_paid
    paiement.status = Paiement_stripe.PAID
    paiement.save()

    resa.refresh_from_db()
    # La reservation a été passée en PAID (puis trigger enchaîne → possiblement VALID)
    # / The reservation was moved to PAID (trigger chain may progress to VALID)
    assert resa.status in [Reservation.PAID, Reservation.VALID]


@pytest.mark.django_db
def test_flow_panier_n_reservations_toutes_passent_en_paid(
    user_acheteur, tenant_context_lespass,
):
    """
    Flow panier : Paiement_stripe.reservation=None + N lignes sur N reservations.
    Toutes les reservations doivent passer en PAID via le patch.
    / Cart flow: Paiement_stripe.reservation=None + N lines on N reservations.
    All reservations must move to PAID via the patch.
    """
    from BaseBillet.models import Paiement_stripe, Reservation

    paiement, reservations = _creer_paiement_avec_n_reservations(user_acheteur, n_reservations=3)
    # Confirmation préalable : FK legacy est None (panier)
    # / Sanity check: legacy FK is None (cart)
    assert paiement.reservation is None

    paiement.status = Paiement_stripe.PAID
    paiement.save()

    for resa in reservations:
        resa.refresh_from_db()
        assert resa.status in [Reservation.PAID, Reservation.VALID], (
            f"Reservation {resa.uuid} should be PAID/VALID, got {resa.status}"
        )


@pytest.mark.django_db
def test_adhesion_only_ne_touche_pas_reservations(user_acheteur, tenant_context_lespass):
    """
    Flow adhésion seule : paiement.reservation=None + ligne.reservation=None.
    Le set() est vide → aucun save() sur Reservation. Comportement identique à avant.
    / Standalone adhesion: paiement.reservation=None + ligne.reservation=None.
    Empty set → no Reservation save(). Identical behavior.
    """
    from ApiBillet.serializers import get_or_create_price_sold
    from BaseBillet.models import (
        LigneArticle, Membership, Paiement_stripe, PaymentMethod, Price, Product,
    )

    prod = Product.objects.create(
        name=f"A {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price = Price.objects.create(
        product=prod, name="std", prix=Decimal("10.00"), publish=True,
    )
    membership = Membership.objects.create(
        user=user_acheteur, price=price,
        status=Membership.WAITING_PAYMENT,
        first_name="A", last_name="B",
        contribution_value=Decimal("10.00"),
    )
    paiement = Paiement_stripe.objects.create(
        user=user_acheteur, source=Paiement_stripe.FRONT_BILLETTERIE,
        status=Paiement_stripe.PENDING,
    )
    pricesold = get_or_create_price_sold(price)
    LigneArticle.objects.create(
        pricesold=pricesold, amount=1000, qty=1,
        payment_method=PaymentMethod.STRIPE_NOFED,
        membership=membership,
        paiement_stripe=paiement,
        status=LigneArticle.UNPAID,
    )
    # Aucune reservation dans le setup / No reservation in setup
    assert paiement.reservation is None

    paiement.status = Paiement_stripe.PAID
    paiement.save()

    # Le membership trigger_A passe au ONCE via la cascade standard
    # / The membership trigger_A moves to ONCE via standard cascade
    membership.refresh_from_db()
    assert membership.status == Membership.ONCE
