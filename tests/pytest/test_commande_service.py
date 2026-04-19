"""
Tests du service de matérialisation de commande.
Session 02 — Tâche 2.5.

Run:
    poetry run pytest -q tests/pytest/test_commande_service.py
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context


@pytest.fixture(autouse=True)
def _reset_translation_after_test():
    """Remet la langue par défaut après chaque test.
    Les signaux (envoi mail, Celery eager) appellent translation.activate(config.language),
    ce qui fait fuiter le locale entre tests. Pre-existing issue hors de ce chantier.
    / Reset default language after each test — signals activate tenant language,
    leaking locale across tests. Pre-existing, not introduced by Session 02.
    """
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
    """User acheteur de test. Le rollback @pytest.mark.django_db s'occupe du cleanup.
    / Test buyer user. @pytest.mark.django_db rollback handles cleanup.
    """
    from AuthBillet.models import TibilletUser
    user = TibilletUser.objects.create(
        email=f"cs-{uuid.uuid4()}@example.org",
        username=f"cs-{uuid.uuid4()}",
    )
    return user


@pytest.fixture
def request_authentifie(user_acheteur, tenant_context_lespass):
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory
    factory = RequestFactory()
    request = factory.get('/')
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    request.user = user_acheteur
    return request


@pytest.mark.django_db
def test_materialiser_commande_gratuite_multi_events(
    request_authentifie, user_acheteur, tenant_context_lespass,
):
    """Un panier 100% gratuit avec 2 events → Commande PAID direct (pas de Stripe).
    / A 100% free cart with 2 events → Commande PAID direct (no Stripe)."""
    from BaseBillet.models import Commande, Event, Price, Product, Reservation
    from BaseBillet.services_commande import CommandeService
    from BaseBillet.services_panier import PanierSession

    # Setup : 2 events gratuits avec produit et prix 0€
    prod_free = Product.objects.create(
        name=f"Free {uuid.uuid4()}", categorie_article=Product.FREERES,
    )
    event_a = Event.objects.create(
        name=f"EA-{uuid.uuid4()}", datetime=timezone.now() + timedelta(days=3),
        end_datetime=timezone.now() + timedelta(days=3, hours=2), jauge_max=100,
    )
    event_b = Event.objects.create(
        name=f"EB-{uuid.uuid4()}", datetime=timezone.now() + timedelta(days=5),
        end_datetime=timezone.now() + timedelta(days=5, hours=2), jauge_max=100,
    )
    event_a.products.add(prod_free)
    event_b.products.add(prod_free)
    # Price 0€ créé automatiquement via signal post_save sur FREERES
    # / Price 0€ auto-created via post_save signal on FREERES
    price_free = prod_free.prices.filter(prix=0).first()
    assert price_free is not None

    # Ajout au panier
    panier = PanierSession(request_authentifie)
    panier.add_ticket(event_a.uuid, price_free.uuid, qty=2)
    panier.add_ticket(event_b.uuid, price_free.uuid, qty=1)

    # Matérialisation
    commande = CommandeService.materialiser(
        panier, user_acheteur,
        first_name="Free",
        last_name="Tester",
        email=user_acheteur.email,
    )

    # Assertions
    assert commande.status == Commande.PAID
    assert commande.paid_at is not None
    assert commande.paiement_stripe is None
    assert commande.reservations.count() == 2
    # Chaque reservation doit être en FREERES ou FREERES_USERACTIV
    # / Each reservation must be in FREERES or FREERES_USERACTIV
    for r in commande.reservations.all():
        assert r.status in [Reservation.FREERES, Reservation.FREERES_USERACTIV]
    # Panier gratuit : somme des LigneArticle via reservations = 0 centimes.
    # / Free cart: sum of LigneArticle via reservations = 0 cents.
    total_lignes_centimes = 0
    for r in commande.reservations.all():
        for ligne in r.lignearticles.all():
            total_lignes_centimes += int(ligne.amount * ligne.qty)
    assert total_lignes_centimes == 0

    # Cleanup : @pytest.mark.django_db rollback s'occupe de tout.
    # django-stdimage lève des erreurs sur .delete() (trap connu).
    # / Cleanup: @pytest.mark.django_db rollback handles everything.
    # django-stdimage raises errors on .delete() (known trap).


@pytest.mark.django_db
def test_materialiser_commande_vide_leve_erreur(
    request_authentifie, user_acheteur, tenant_context_lespass,
):
    from BaseBillet.services_commande import CommandeService, CommandeServiceError
    from BaseBillet.services_panier import PanierSession

    panier = PanierSession(request_authentifie)
    with pytest.raises(CommandeServiceError, match="empty"):
        CommandeService.materialiser(
            panier, user_acheteur,
            first_name="X", last_name="Y", email=user_acheteur.email,
        )


@pytest.mark.django_db
def test_materialiser_cree_membership_avant_reservation(
    request_authentifie, user_acheteur, tenant_context_lespass,
):
    """Phase 1 (Membership) doit finir avant Phase 2 (Reservation).
    Vérifié par : un tarif gaté par l'adhésion du panier est accepté.
    / Phase 1 (Membership) must finish before Phase 2 (Reservation).
    Verified by: a rate gated by the cart's membership is accepted."""
    from BaseBillet.models import Commande, Event, Membership, Price, Product
    from BaseBillet.services_commande import CommandeService
    from BaseBillet.services_panier import PanierSession

    # Adhésion gratuite + billet gaté à 0€
    prod_adh = Product.objects.create(
        name=f"Ad {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price_adh = Price.objects.create(
        product=prod_adh, name="A", prix=Decimal("0.00"), publish=True,
        # subscription_type YEAR pour que set_deadline() retourne une deadline
        # / subscription_type YEAR so set_deadline() returns a non-None deadline
        subscription_type=Price.YEAR,
    )
    prod_billet = Product.objects.create(
        name=f"Bg {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event = Event.objects.create(
        name=f"Gated {uuid.uuid4()}", datetime=timezone.now() + timedelta(days=2),
        end_datetime=timezone.now() + timedelta(days=2, hours=1), jauge_max=50,
    )
    event.products.add(prod_billet)
    price_billet = Price.objects.create(
        product=prod_billet, name="Adh", prix=Decimal("0.00"), publish=True,
    )
    price_billet.adhesions_obligatoires.add(prod_adh)

    panier = PanierSession(request_authentifie)
    panier.add_membership(price_adh.uuid)
    panier.add_ticket(event.uuid, price_billet.uuid, qty=1)

    commande = CommandeService.materialiser(
        panier, user_acheteur,
        first_name="O", last_name="K", email=user_acheteur.email,
    )

    assert commande.status == Commande.PAID  # tout gratuit
    assert commande.memberships_commande.count() == 1
    assert commande.reservations.count() == 1
    # Le membership doit être ONCE (gratuit)
    m = commande.memberships_commande.first()
    assert m.status == Membership.ONCE
    assert m.deadline is not None

    # Cleanup : @pytest.mark.django_db rollback s'occupe de tout.
    # / Cleanup: @pytest.mark.django_db rollback handles everything.


@pytest.mark.django_db
def test_materialiser_rollback_si_erreur(
    request_authentifie, user_acheteur, tenant_context_lespass,
):
    """Si une exception survient en cours de matérialisation, tout rollback.
    / If an exception occurs during materialization, everything rolls back."""
    from unittest.mock import patch
    from BaseBillet.models import Commande, Event, Price, Product
    from BaseBillet.services_commande import CommandeService
    from BaseBillet.services_panier import PanierSession

    prod = Product.objects.create(
        name=f"R {uuid.uuid4()}", categorie_article=Product.FREERES,
    )
    event = Event.objects.create(
        name=f"RB-{uuid.uuid4()}", datetime=timezone.now() + timedelta(days=3),
        end_datetime=timezone.now() + timedelta(days=3, hours=2), jauge_max=50,
    )
    event.products.add(prod)
    price = prod.prices.filter(prix=0).first()

    panier = PanierSession(request_authentifie)
    panier.add_ticket(event.uuid, price.uuid, qty=1)

    count_before = Commande.objects.filter(user=user_acheteur).count()

    # Force une exception dans la Phase 4 (gratuit) via mock
    with patch(
        "BaseBillet.services_commande.CommandeService._finaliser_gratuit",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(RuntimeError):
            CommandeService.materialiser(
                panier, user_acheteur,
                first_name="R", last_name="B", email=user_acheteur.email,
            )

    # La commande ne doit pas exister (rollback)
    count_after = Commande.objects.filter(user=user_acheteur).count()
    assert count_after == count_before

    # Cleanup : @pytest.mark.django_db rollback s'occupe de tout.
    # / Cleanup: @pytest.mark.django_db rollback handles everything.


@pytest.mark.django_db
def test_materialiser_propage_options_et_custom_form(
    request_authentifie, user_acheteur, tenant_context_lespass,
):
    """
    C1 fix : les options et custom_form des items panier sont propagés
    sur la Reservation créée en Phase 2.
    / C1 fix: options and custom_form from cart items are propagated to
    the Reservation created in Phase 2.
    """
    from BaseBillet.models import (
        Commande, Event, OptionGenerale, Price, Product, Reservation,
    )
    from BaseBillet.services_commande import CommandeService
    from BaseBillet.services_panier import PanierSession

    # Setup event + product FREERES + option
    prod = Product.objects.create(
        name=f"C1-{uuid.uuid4()}", categorie_article=Product.FREERES,
    )
    event = Event.objects.create(
        name=f"C1evt-{uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=3),
        jauge_max=50,
    )
    event.products.add(prod)
    price = prod.prices.filter(prix=0).first()
    option = OptionGenerale.objects.create(name=f"Opt-{uuid.uuid4().hex[:6]}")
    event.options_radio.add(option)

    panier = PanierSession(request_authentifie)
    panier.add_ticket(
        event.uuid, price.uuid, qty=1,
        options=[str(option.uuid)],
        custom_form={"dietary": "vegan"},
    )

    commande = CommandeService.materialiser(
        panier, user_acheteur,
        first_name="C1", last_name="Test",
        email=user_acheteur.email,
    )

    reservation = commande.reservations.first()
    assert reservation is not None
    assert reservation.custom_form == {"dietary": "vegan"}, (
        f"custom_form lost: {reservation.custom_form}"
    )
    assert option in reservation.options.all(), (
        "option not propagated to reservation"
    )
