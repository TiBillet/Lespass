"""
Tests du ReservationValidator cart-aware + fix bug overlap.
Session 03 — Tâche 3.4.

Run:
    poetry run pytest -q tests/pytest/test_reservation_validator_cart_aware.py
"""
import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.http import QueryDict
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
    # username == email : le validator appelle get_or_create_user(email) qui
    # fait un get_or_create(email=X, username=X, espece=HU). Si username != email,
    # le get ne matche pas et le create viole la contrainte unique email.
    # / username == email: the validator calls get_or_create_user(email) which
    # does get_or_create(email=X, username=X, espece=HU). If username != email,
    # the get misses and the create violates the unique email constraint.
    email = f"rv-{uuid.uuid4()}@example.org"
    user = TibilletUser.objects.create(
        email=email,
        username=email,
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


def _make_request(user, payload):
    """Fabrique un faux request compatible DRF (expose .data) pour le validator.
    / Builds a DRF-compatible fake request (exposes .data) for the validator.
    Cf. tests/scripts/setup_test_data.py pour le pattern d'origine."""
    data = QueryDict(mutable=True)
    data.update(payload)
    return SimpleNamespace(user=user, data=data)


# ==========================================================================
# Tests cart-aware adhesions_obligatoires
# ==========================================================================


@pytest.mark.django_db
def test_validator_refuse_tarif_gate_sans_adhesion_ni_commande(
    user_acheteur, tenant_context_lespass,
):
    """
    Flow direct : tarif gaté + user sans adhésion + pas de current_commande → rejet.
    / Direct flow: gated rate + user without membership + no current_commande → reject.
    """
    from rest_framework.exceptions import ValidationError
    from BaseBillet.models import Event, Price, Product
    from BaseBillet.validators import ReservationValidator

    # Setup : event + billet gaté + adhésion requise
    event = Event.objects.create(
        name=f"Gate-{uuid.uuid4()}", datetime=timezone.now() + timedelta(days=2),
        jauge_max=50,
    )
    prod_billet = Product.objects.create(
        name=f"B {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(prod_billet)
    prod_adh = Product.objects.create(
        name=f"A {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price = Price.objects.create(
        product=prod_billet, name="Gated", prix=Decimal("5.00"), publish=True,
    )
    price.adhesions_obligatoires.add(prod_adh)

    payload = {
        "email": user_acheteur.email, "event": str(event.uuid),
        str(price.uuid): "1",
    }
    request = _make_request(user_acheteur, payload)
    validator = ReservationValidator(
        data=payload,
        context={"request": request},
    )
    with pytest.raises(ValidationError, match="User is not subscribed"):
        validator.is_valid(raise_exception=True)


# ==========================================================================
# Tests fix bug overlap
# ==========================================================================


@pytest.mark.django_db
def test_overlap_fix_reservation_canceled_ne_bloque_plus(
    user_acheteur, tenant_context_lespass, mock_stripe,
):
    """
    FIX BUG : une reservation CANCELED chevauchante ne bloque plus.
    / BUG FIX: a CANCELED overlapping reservation no longer blocks.
    """
    from BaseBillet.models import Configuration, Event, Price, Product, Reservation
    from BaseBillet.validators import ReservationValidator

    config = Configuration.get_solo()
    orig = config.allow_concurrent_bookings
    config.allow_concurrent_bookings = False
    config.save()
    try:
        start = timezone.now() + timedelta(days=3)
        event_past = Event.objects.create(
            name=f"Past-{uuid.uuid4()}", datetime=start,
            end_datetime=start + timedelta(hours=2), jauge_max=50,
        )
        # Reservation CANCELED sur créneau chevauchant
        # / CANCELED reservation on overlapping slot
        Reservation.objects.create(
            user_commande=user_acheteur, event=event_past, status=Reservation.CANCELED,
        )

        # Maintenant on tente de réserver un autre event qui chevauche
        event_new = Event.objects.create(
            name=f"New-{uuid.uuid4()}", datetime=start + timedelta(hours=1),
            end_datetime=start + timedelta(hours=3), jauge_max=50,
        )
        prod = Product.objects.create(
            name=f"P {uuid.uuid4()}", categorie_article=Product.BILLET,
        )
        event_new.products.add(prod)
        price = Price.objects.create(
            product=prod, name="x", prix=Decimal("10.00"), publish=True,
        )

        payload = {
            "email": user_acheteur.email, "event": str(event_new.uuid),
            str(price.uuid): "1",
        }
        request = _make_request(user_acheteur, payload)
        validator = ReservationValidator(
            data=payload,
            context={"request": request},
        )
        # Doit passer — la resa CANCELED ne bloque plus
        # / Must pass — CANCELED resa no longer blocks
        assert validator.is_valid() is True
    finally:
        config.allow_concurrent_bookings = orig
        config.save()


@pytest.mark.django_db
def test_overlap_unpaid_ancien_ne_bloque_plus(
    user_acheteur, tenant_context_lespass, mock_stripe,
):
    """
    FIX BUG : une reservation UNPAID abandonnée > 15 min ne bloque plus.
    / BUG FIX: an UNPAID reservation abandoned > 15 min no longer blocks.
    """
    from BaseBillet.models import Configuration, Event, Price, Product, Reservation
    from BaseBillet.validators import ReservationValidator

    config = Configuration.get_solo()
    orig = config.allow_concurrent_bookings
    config.allow_concurrent_bookings = False
    config.save()
    try:
        start = timezone.now() + timedelta(days=3)
        event_old = Event.objects.create(
            name=f"Old-{uuid.uuid4()}", datetime=start,
            end_datetime=start + timedelta(hours=2), jauge_max=50,
        )
        old_resa = Reservation.objects.create(
            user_commande=user_acheteur, event=event_old, status=Reservation.UNPAID,
        )
        # Forcer datetime > 15 min (simule resa abandonnée)
        # / Force datetime > 15 min (simulate abandoned resa)
        Reservation.objects.filter(pk=old_resa.pk).update(
            datetime=timezone.now() - timedelta(minutes=30)
        )

        event_new = Event.objects.create(
            name=f"Fresh-{uuid.uuid4()}", datetime=start + timedelta(hours=1),
            end_datetime=start + timedelta(hours=3), jauge_max=50,
        )
        prod = Product.objects.create(
            name=f"P {uuid.uuid4()}", categorie_article=Product.BILLET,
        )
        event_new.products.add(prod)
        price = Price.objects.create(
            product=prod, name="x", prix=Decimal("10.00"), publish=True,
        )

        payload = {
            "email": user_acheteur.email, "event": str(event_new.uuid),
            str(price.uuid): "1",
        }
        request = _make_request(user_acheteur, payload)
        validator = ReservationValidator(
            data=payload,
            context={"request": request},
        )
        # Doit passer — UNPAID abandonnée ne bloque plus
        # / Must pass — abandoned UNPAID no longer blocks
        assert validator.is_valid() is True
    finally:
        config.allow_concurrent_bookings = orig
        config.save()


@pytest.mark.django_db
def test_overlap_paid_bloque_toujours(user_acheteur, tenant_context_lespass):
    """
    Non-régression : une reservation PAID/VALID chevauchante bloque TOUJOURS.
    / Non-regression: PAID/VALID overlapping reservation STILL blocks.
    """
    from rest_framework.exceptions import ValidationError
    from BaseBillet.models import Configuration, Event, Price, Product, Reservation
    from BaseBillet.validators import ReservationValidator

    config = Configuration.get_solo()
    orig = config.allow_concurrent_bookings
    config.allow_concurrent_bookings = False
    config.save()
    try:
        start = timezone.now() + timedelta(days=3)
        event_paid = Event.objects.create(
            name=f"Paid-{uuid.uuid4()}", datetime=start,
            end_datetime=start + timedelta(hours=2), jauge_max=50,
        )
        Reservation.objects.create(
            user_commande=user_acheteur, event=event_paid, status=Reservation.PAID,
        )

        event_new = Event.objects.create(
            name=f"Tentative-{uuid.uuid4()}", datetime=start + timedelta(hours=1),
            end_datetime=start + timedelta(hours=3), jauge_max=50,
        )
        prod = Product.objects.create(
            name=f"P {uuid.uuid4()}", categorie_article=Product.BILLET,
        )
        event_new.products.add(prod)
        price = Price.objects.create(
            product=prod, name="x", prix=Decimal("10.00"), publish=True,
        )

        payload = {
            "email": user_acheteur.email, "event": str(event_new.uuid),
            str(price.uuid): "1",
        }
        request = _make_request(user_acheteur, payload)
        validator = ReservationValidator(
            data=payload,
            context={"request": request},
        )
        # Doit échouer — PAID bloque toujours
        # / Must fail — PAID still blocks
        with pytest.raises(ValidationError, match="already booked"):
            validator.is_valid(raise_exception=True)
    finally:
        config.allow_concurrent_bookings = orig
        config.save()


@pytest.mark.django_db
def test_overlap_unpaid_recent_bloque_avec_message_paiement_en_cours(
    user_acheteur, tenant_context_lespass,
):
    """
    UNPAID < 15 min → bloque avec message "payment in progress".
    / UNPAID < 15 min → blocks with "payment in progress" message.
    """
    from rest_framework.exceptions import ValidationError
    from BaseBillet.models import Configuration, Event, Price, Product, Reservation
    from BaseBillet.validators import ReservationValidator

    config = Configuration.get_solo()
    orig = config.allow_concurrent_bookings
    config.allow_concurrent_bookings = False
    config.save()
    try:
        start = timezone.now() + timedelta(days=3)
        event_recent = Event.objects.create(
            name=f"Rec-{uuid.uuid4()}", datetime=start,
            end_datetime=start + timedelta(hours=2), jauge_max=50,
        )
        Reservation.objects.create(
            user_commande=user_acheteur, event=event_recent, status=Reservation.UNPAID,
            # datetime sera auto_now=True (maintenant) → < 15 min
        )

        event_new = Event.objects.create(
            name=f"New-{uuid.uuid4()}", datetime=start + timedelta(hours=1),
            end_datetime=start + timedelta(hours=3), jauge_max=50,
        )
        prod = Product.objects.create(
            name=f"P {uuid.uuid4()}", categorie_article=Product.BILLET,
        )
        event_new.products.add(prod)
        price = Price.objects.create(
            product=prod, name="x", prix=Decimal("10.00"), publish=True,
        )

        payload = {
            "email": user_acheteur.email, "event": str(event_new.uuid),
            str(price.uuid): "1",
        }
        request = _make_request(user_acheteur, payload)
        validator = ReservationValidator(
            data=payload,
            context={"request": request},
        )
        with pytest.raises(ValidationError, match="payment in progress"):
            validator.is_valid(raise_exception=True)
    finally:
        config.allow_concurrent_bookings = orig
        config.save()
