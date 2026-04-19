"""
Tests du gestionnaire de panier en session.
Session 02 — Tâche 2.1 : squelette (add/remove/count/clear basique).
Session 02 — Tâche 2.2 : validations standards (add_ticket/add_membership).
/ Session cart manager tests. Session 02 — Task 2.1: skeleton.
/ Session 02 — Task 2.2: standard validations (add_ticket/add_membership).

Run:
    poetry run pytest -q tests/pytest/test_panier_session.py
"""
import uuid
from decimal import Decimal

import pytest
from django.db.models import Q
from django_tenants.utils import tenant_context


@pytest.fixture
def tenant_context_lespass():
    from Customers.models import Client as TenantClient
    tenant = TenantClient.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        yield tenant


@pytest.fixture
def request_with_session():
    """RequestFactory avec session middleware activé + user anonyme.
    / RequestFactory with session middleware enabled + anonymous user."""
    from django.contrib.auth.models import AnonymousUser
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory
    factory = RequestFactory()
    request = factory.get('/')

    def _get_response(req):
        return None

    middleware = SessionMiddleware(_get_response)
    middleware.process_request(request)
    request.session.save()
    # AnonymousUser pour permettre request.user.is_authenticated dans PanierSession
    # / AnonymousUser so request.user.is_authenticated works in PanierSession
    request.user = AnonymousUser()
    return request


# ==========================================================================
# Fixtures DB communes (utilisées par les tests Tâche 2.1 adaptés + Tâche 2.2)
# / Shared DB fixtures (used by adapted Task 2.1 tests + Task 2.2 tests)
# ==========================================================================


@pytest.fixture
def event_avec_tarif(tenant_context_lespass):
    """Event + Product billet + Price publié, prêt à l'emploi.
    / Event + ticket Product + published Price, ready to use."""
    from datetime import timedelta
    from decimal import Decimal
    from django.utils import timezone
    from BaseBillet.models import Event, Price, Product

    event = Event.objects.create(
        name=f"Evt {uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=7),
        jauge_max=100,
    )
    product = Product.objects.create(
        name=f"Billet {uuid.uuid4()}",
        categorie_article=Product.BILLET,
    )
    event.products.add(product)
    price = Price.objects.create(
        product=product, name="Plein", prix=Decimal("10.00"), publish=True,
    )
    yield event, price
    # Pas de .delete() explicite — django_db gère le rollback.
    # Appeler .delete() sur Product/Event déclenche le bug stdimage
    # (post_delete sur img=None).
    # / No explicit .delete() — django_db handles rollback.
    # Calling .delete() on Product/Event triggers the stdimage bug
    # (post_delete on img=None).


@pytest.fixture
def adhesion_standard(tenant_context_lespass):
    """Product ADHESION + Price simple (pas recurring, pas manual_validation).
    / Standard ADHESION Product + Price (no recurring, no manual validation)."""
    from decimal import Decimal
    from BaseBillet.models import Price, Product

    product = Product.objects.create(
        name=f"Adh {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price = Price.objects.create(
        product=product, name="Std", prix=Decimal("15.00"), publish=True,
    )
    yield product, price
    # Pas de .delete() explicite — django_db gère le rollback (cf. bug stdimage).
    # / No explicit .delete() — django_db handles rollback (stdimage bug).


# ==========================================================================
# Tests Tâche 2.1 — squelette PanierSession (adaptés aux validations 2.2)
# / Task 2.1 tests — PanierSession skeleton (adapted for 2.2 validations)
# ==========================================================================


@pytest.mark.django_db
def test_panier_vide_au_debut(tenant_context_lespass, request_with_session):
    """Un panier fraîchement instancié est vide.
    / A freshly instantiated cart is empty."""
    from BaseBillet.services_panier import PanierSession
    panier = PanierSession(request_with_session)
    assert panier.is_empty() is True
    assert panier.count() == 0
    assert panier.items() == []


@pytest.mark.django_db
def test_add_ticket_stocke_en_session(request_with_session, event_avec_tarif):
    """add_ticket stocke un item dans la session.
    / add_ticket stores an item in the session."""
    from BaseBillet.services_panier import PanierSession
    event, price = event_avec_tarif
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=2)

    assert panier.count() == 2  # qty=2
    items = panier.items()
    assert len(items) == 1
    assert items[0]['type'] == 'ticket'
    assert items[0]['event_uuid'] == str(event.uuid)
    assert items[0]['price_uuid'] == str(price.uuid)
    assert items[0]['qty'] == 2


@pytest.mark.django_db
def test_add_membership_stocke_en_session(request_with_session, adhesion_standard):
    """add_membership stocke un item adhésion.
    / add_membership stores a membership item."""
    from BaseBillet.services_panier import PanierSession
    _product, price = adhesion_standard
    panier = PanierSession(request_with_session)
    panier.add_membership(price.uuid)
    assert panier.count() == 1
    items = panier.items()
    assert items[0]['type'] == 'membership'
    assert items[0]['price_uuid'] == str(price.uuid)


@pytest.mark.django_db
def test_count_cumule_tickets_et_memberships(
    request_with_session, event_avec_tarif, adhesion_standard
):
    """count() somme qty des billets + 1 par adhésion.
    / count() sums ticket qty + 1 per membership."""
    from BaseBillet.services_panier import PanierSession
    event, price = event_avec_tarif
    _product, price_adh = adhesion_standard
    panier = PanierSession(request_with_session)
    # Deux ajouts ticket sur le même event/price : qty 3 puis 2
    # / Two ticket adds on same event/price: qty 3 then 2
    panier.add_ticket(event.uuid, price.uuid, qty=3)
    panier.add_ticket(event.uuid, price.uuid, qty=2)
    panier.add_membership(price_adh.uuid)
    # 3 + 2 + 1 = 6
    assert panier.count() == 6


@pytest.mark.django_db
def test_remove_item_retire_a_index(request_with_session, event_avec_tarif):
    """remove_item retire l'item à l'index spécifié.
    / remove_item removes the item at the given index."""
    from BaseBillet.services_panier import PanierSession
    event, price = event_avec_tarif
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=1)
    panier.add_ticket(event.uuid, price.uuid, qty=1)

    panier.remove_item(0)

    items = panier.items()
    assert len(items) == 1
    assert items[0]['price_uuid'] == str(price.uuid)


@pytest.mark.django_db
def test_remove_item_index_invalide_silencieux(request_with_session, event_avec_tarif):
    """remove_item sur index invalide ne plante pas.
    / remove_item on invalid index does not crash."""
    from BaseBillet.services_panier import PanierSession
    event, price = event_avec_tarif
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=1)

    panier.remove_item(99)  # OOR — silent
    panier.remove_item(-1)  # negative — silent

    assert len(panier.items()) == 1


# Note : les tests update_quantity ont ete supprimes (refactor 2026-04).
# La methode n'existe plus — pour changer une qty, l'user retire + re-ajoute.
# / update_quantity tests removed (2026-04 refactor). Method no longer exists.


@pytest.mark.django_db
def test_clear_vide_tout(request_with_session, event_avec_tarif, adhesion_standard):
    """clear() vide totalement le panier.
    / clear() completely empties the cart."""
    from BaseBillet.services_panier import PanierSession
    event, price = event_avec_tarif
    _product, price_adh = adhesion_standard
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=2)
    panier.add_membership(price_adh.uuid)
    assert panier.count() > 0

    panier.clear()

    assert panier.is_empty() is True
    assert panier.count() == 0


@pytest.mark.django_db
def test_panier_persiste_entre_instances(request_with_session, event_avec_tarif):
    """Deux PanierSession sur la même request voient les mêmes items.
    / Two PanierSession on the same request see the same items."""
    from BaseBillet.services_panier import PanierSession
    event, price = event_avec_tarif
    panier1 = PanierSession(request_with_session)
    panier1.add_ticket(event.uuid, price.uuid, qty=2)

    panier2 = PanierSession(request_with_session)
    assert panier2.count() == 2


@pytest.mark.django_db
def test_adhesions_product_ids_retourne_products_adhesion(
    request_with_session, event_avec_tarif, adhesion_standard
):
    """adhesions_product_ids() renvoie les UUIDs de Product des adhésions présentes.
    / adhesions_product_ids() returns UUIDs of Product for present memberships."""
    from BaseBillet.services_panier import PanierSession

    event, price_billet = event_avec_tarif
    prod_adhesion, price_adhesion = adhesion_standard

    panier = PanierSession(request_with_session)
    panier.add_membership(price_adhesion.uuid)
    panier.add_ticket(event.uuid, price_billet.uuid, qty=1)  # ne doit pas apparaître

    product_ids = panier.adhesions_product_ids()
    assert prod_adhesion.uuid in product_ids
    assert len(product_ids) == 1


# ==========================================================================
# Tests Tâche 2.2 — validations standards
# / Task 2.2 tests — standard validations
# ==========================================================================


@pytest.mark.django_db
def test_add_ticket_refuse_qty_zero(request_with_session, event_avec_tarif):
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    event, price = event_avec_tarif
    panier = PanierSession(request_with_session)
    with pytest.raises(InvalidItemError, match="Quantity must be positive"):
        panier.add_ticket(event.uuid, price.uuid, qty=0)


@pytest.mark.django_db
def test_add_ticket_refuse_event_inexistant(request_with_session, tenant_context_lespass):
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    panier = PanierSession(request_with_session)
    with pytest.raises(InvalidItemError, match="Event not found"):
        panier.add_ticket(uuid.uuid4(), uuid.uuid4(), qty=1)


@pytest.mark.django_db
def test_add_ticket_refuse_price_inexistant(request_with_session, event_avec_tarif):
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    event, _price = event_avec_tarif
    panier = PanierSession(request_with_session)
    with pytest.raises(InvalidItemError, match="Price not found"):
        panier.add_ticket(event.uuid, uuid.uuid4(), qty=1)


@pytest.mark.django_db
def test_add_ticket_refuse_price_non_publie(request_with_session, event_avec_tarif):
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    event, price = event_avec_tarif
    price.publish = False
    price.save()
    panier = PanierSession(request_with_session)
    with pytest.raises(InvalidItemError, match="not available"):
        panier.add_ticket(event.uuid, price.uuid, qty=1)


@pytest.mark.django_db
def test_add_ticket_refuse_price_pas_dans_event(request_with_session, tenant_context_lespass):
    """Si un price n'est pas lié à l'event via products, refusé.
    / If a price is not linked to the event via products, refused."""
    from datetime import timedelta
    from decimal import Decimal
    from django.utils import timezone
    from BaseBillet.models import Event, Price, Product
    from BaseBillet.services_panier import PanierSession, InvalidItemError

    event = Event.objects.create(
        name=f"Evt {uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=5),
        jauge_max=50,
    )
    # Product non lié à l'event / Product not linked to event
    product_other = Product.objects.create(
        name=f"Other {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    price_other = Price.objects.create(
        product=product_other, name="X", prix=Decimal("5.00"), publish=True,
    )
    panier = PanierSession(request_with_session)
    with pytest.raises(InvalidItemError, match="not available for this event"):
        panier.add_ticket(event.uuid, price_other.uuid, qty=1)
    # Pas de .delete() — django_db rollback suffit (bug stdimage sur img=None).
    # / No .delete() — django_db rollback handles it (stdimage bug on img=None).


@pytest.mark.django_db
def test_add_membership_refuse_recurring(request_with_session, adhesion_standard):
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    _product, price = adhesion_standard
    price.recurring_payment = True
    price.save()
    panier = PanierSession(request_with_session)
    with pytest.raises(InvalidItemError, match="Recurring memberships"):
        panier.add_membership(price.uuid)


@pytest.mark.django_db
def test_add_membership_refuse_manual_validation(request_with_session, adhesion_standard):
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    _product, price = adhesion_standard
    price.manual_validation = True
    price.save()
    panier = PanierSession(request_with_session)
    with pytest.raises(InvalidItemError, match="manual validation"):
        panier.add_membership(price.uuid)


@pytest.mark.django_db
def test_add_membership_refuse_doublon(request_with_session, adhesion_standard):
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    _product, price = adhesion_standard
    panier = PanierSession(request_with_session)
    panier.add_membership(price.uuid)
    with pytest.raises(InvalidItemError, match="already in your cart"):
        panier.add_membership(price.uuid)


@pytest.mark.django_db
def test_add_membership_refuse_produit_non_adhesion(request_with_session, event_avec_tarif):
    """Un price de type BILLET ne peut pas être ajouté via add_membership.
    / A BILLET-type price cannot be added via add_membership."""
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    _event, price_billet = event_avec_tarif
    panier = PanierSession(request_with_session)
    with pytest.raises(InvalidItemError, match="not a membership"):
        panier.add_membership(price_billet.uuid)


# ==========================================================================
# Tests Tâche 2.3 — overlap, cart-aware adhésion, code promo
# / Task 2.3 tests — overlap, cart-aware membership, promo code
# ==========================================================================


@pytest.fixture
def request_authentifie(request_with_session, tenant_context_lespass):
    """Request avec user authentifié (pour tests overlap DB).
    / Request with authenticated user (for DB overlap tests)."""
    from AuthBillet.models import TibilletUser
    user = TibilletUser.objects.create(
        email=f"req-{uuid.uuid4()}@example.org",
        username=f"req-{uuid.uuid4()}",
    )
    request_with_session.user = user
    yield request_with_session
    # cleanup des objets qui pointent sur user (PROTECT/SET_NULL)
    from BaseBillet.models import Commande, LigneArticle, Membership, Reservation, Paiement_stripe
    LigneArticle.objects.filter(
        Q(reservation__user_commande=user) | Q(membership__user=user)
    ).delete()
    Reservation.objects.filter(user_commande=user).delete()
    Membership.objects.filter(user=user).delete()
    Commande.objects.filter(user=user).delete()
    Paiement_stripe.objects.filter(user=user).delete()
    user.delete()


@pytest.mark.django_db
def test_set_promo_code_refuse_code_inexistant(request_with_session, event_avec_tarif):
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    event, price = event_avec_tarif
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=1)
    with pytest.raises(InvalidItemError, match="Invalid"):
        panier.set_promo_code("DOES_NOT_EXIST")


@pytest.mark.django_db
def test_set_promo_code_refuse_si_product_pas_dans_panier(
    request_with_session, event_avec_tarif, tenant_context_lespass,
):
    """Un code lié à un product absent du panier est refusé.
    / A code linked to a product absent from the cart is refused."""
    from decimal import Decimal
    from BaseBillet.models import Product, PromotionalCode
    from BaseBillet.services_panier import PanierSession, InvalidItemError

    event, price = event_avec_tarif
    other_product = Product.objects.create(
        name=f"Other {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    promo = PromotionalCode.objects.create(
        name=f"PROMO-{uuid.uuid4().hex[:8]}",
        discount_rate=Decimal("10.00"),
        product=other_product,
    )
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=1)
    with pytest.raises(InvalidItemError, match="does not apply"):
        panier.set_promo_code(promo.name)

    # Pas de .delete() sur Product — django_db rollback (bug stdimage).
    # / No .delete() on Product — django_db rollback (stdimage bug).


@pytest.mark.django_db
def test_set_promo_code_ok_si_product_dans_panier(
    request_with_session, event_avec_tarif,
):
    """Le code s'applique si son product est présent.
    / The code applies if its product is present."""
    from decimal import Decimal
    from BaseBillet.models import PromotionalCode
    from BaseBillet.services_panier import PanierSession

    event, price = event_avec_tarif
    promo = PromotionalCode.objects.create(
        name=f"OK-{uuid.uuid4().hex[:8]}",
        discount_rate=Decimal("10.00"),
        product=price.product,
    )
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=1)
    panier.set_promo_code(promo.name)

    assert panier.data['promo_code_name'] == promo.name
    assert panier.promo_code() == promo

    promo.delete()


@pytest.mark.django_db
def test_clear_promo_code(request_with_session, event_avec_tarif):
    from decimal import Decimal
    from BaseBillet.models import PromotionalCode
    from BaseBillet.services_panier import PanierSession

    event, price = event_avec_tarif
    promo = PromotionalCode.objects.create(
        name=f"CLR-{uuid.uuid4().hex[:8]}",
        discount_rate=Decimal("5.00"), product=price.product,
    )
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=1)
    panier.set_promo_code(promo.name)
    panier.clear_promo_code()
    assert panier.data['promo_code_name'] is None
    assert panier.promo_code() is None

    promo.delete()


@pytest.mark.django_db
def test_add_ticket_refuse_adhesion_obligatoire_sans_adhesion(
    request_authentifie, tenant_context_lespass,
):
    """Un tarif gaté est refusé si l'user n'a pas l'adhésion (ni en DB ni en panier).
    / A gated rate is refused if the user has no membership (neither in DB nor cart)."""
    from datetime import timedelta
    from decimal import Decimal
    from django.utils import timezone
    from BaseBillet.models import Event, Price, Product
    from BaseBillet.services_panier import PanierSession, InvalidItemError

    # Setup : un event + un tarif gaté par une adhésion requise
    event = Event.objects.create(
        name=f"Gated {uuid.uuid4()}", datetime=timezone.now() + timedelta(days=5),
        jauge_max=50,
    )
    prod_billet = Product.objects.create(
        name=f"B {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(prod_billet)
    prod_adhesion_required = Product.objects.create(
        name=f"A {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price_gated = Price.objects.create(
        product=prod_billet, name="Adhérent", prix=Decimal("5.00"), publish=True,
    )
    price_gated.adhesions_obligatoires.add(prod_adhesion_required)

    panier = PanierSession(request_authentifie)
    with pytest.raises(InvalidItemError, match="requires a membership"):
        panier.add_ticket(event.uuid, price_gated.uuid, qty=1)

    # Pas de .delete() sur Product/Event — django_db rollback (bug stdimage).
    # / No .delete() on Product/Event — django_db rollback (stdimage bug).


@pytest.mark.django_db
def test_add_ticket_accepte_si_adhesion_dans_panier(
    request_authentifie, tenant_context_lespass,
):
    """Un tarif gaté est accepté si l'adhésion requise est dans le panier.
    / A gated rate is accepted if the required membership is in the cart."""
    from datetime import timedelta
    from decimal import Decimal
    from django.utils import timezone
    from BaseBillet.models import Event, Price, Product
    from BaseBillet.services_panier import PanierSession

    event = Event.objects.create(
        name=f"GatedOK {uuid.uuid4()}", datetime=timezone.now() + timedelta(days=5),
        jauge_max=50,
    )
    prod_billet = Product.objects.create(
        name=f"B {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(prod_billet)
    prod_adhesion_required = Product.objects.create(
        name=f"A {uuid.uuid4()}", categorie_article=Product.ADHESION,
    )
    price_adhesion = Price.objects.create(
        product=prod_adhesion_required, name="Std", prix=Decimal("15.00"), publish=True,
    )
    price_gated = Price.objects.create(
        product=prod_billet, name="Adh", prix=Decimal("5.00"), publish=True,
    )
    price_gated.adhesions_obligatoires.add(prod_adhesion_required)

    panier = PanierSession(request_authentifie)
    panier.add_membership(price_adhesion.uuid)
    # Le tarif gaté est maintenant acceptable car l'adhésion est dans le panier
    panier.add_ticket(event.uuid, price_gated.uuid, qty=1)

    assert panier.count() == 2  # 1 adhésion + 1 billet

    # Pas de .delete() sur Product/Event — django_db rollback (bug stdimage).
    # / No .delete() on Product/Event — django_db rollback (stdimage bug).


@pytest.mark.django_db
def test_add_ticket_refuse_overlap_contre_panier(
    request_with_session, tenant_context_lespass,
):
    """Deux events chevauchants dans le panier = refus si allow_concurrent_bookings=False.
    / Two overlapping events in the cart = refused if allow_concurrent_bookings=False."""
    from datetime import timedelta
    from decimal import Decimal
    from django.utils import timezone
    from BaseBillet.models import Configuration, Event, Price, Product
    from BaseBillet.services_panier import PanierSession, InvalidItemError

    config = Configuration.get_solo()
    config.allow_concurrent_bookings = False
    config.save()

    try:
        start = timezone.now() + timedelta(days=3)
        event_a = Event.objects.create(
            name=f"A-{uuid.uuid4()}", datetime=start,
            end_datetime=start + timedelta(hours=2), jauge_max=50,
        )
        event_b = Event.objects.create(
            name=f"B-{uuid.uuid4()}", datetime=start + timedelta(hours=1),  # chevauche A
            end_datetime=start + timedelta(hours=3), jauge_max=50,
        )
        prod = Product.objects.create(
            name=f"P {uuid.uuid4()}", categorie_article=Product.BILLET,
        )
        event_a.products.add(prod)
        event_b.products.add(prod)
        price = Price.objects.create(
            product=prod, name="x", prix=Decimal("5.00"), publish=True,
        )

        panier = PanierSession(request_with_session)
        panier.add_ticket(event_a.uuid, price.uuid, qty=1)
        with pytest.raises(InvalidItemError, match="overlaps with another event in your cart"):
            panier.add_ticket(event_b.uuid, price.uuid, qty=1)

        # Pas de .delete() sur Product/Event — django_db rollback (bug stdimage).
        # / No .delete() on Product/Event — django_db rollback (stdimage bug).
    finally:
        config.allow_concurrent_bookings = True
        config.save()


# ==========================================================================
# Tests Session 07 — revalidate_all() + calcul_total_centimes()
# / Session 07 tests — revalidate_all() + calcul_total_centimes()
# ==========================================================================


@pytest.mark.django_db
def test_revalidate_all_detecte_price_depublie(
    request_with_session, event_avec_tarif,
):
    """
    revalidate_all() detecte un price qui a ete depublie apres ajout.
    / revalidate_all() detects a price unpublished after add.
    """
    from BaseBillet.services_panier import PanierSession, InvalidItemError

    event, price = event_avec_tarif
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=1)

    # Simuler un depubliage entre add et checkout
    # / Simulate unpublishing between add and checkout
    price.publish = False
    price.save()

    with pytest.raises(InvalidItemError, match="not available"):
        panier.revalidate_all()


@pytest.mark.django_db
def test_calcul_total_centimes(request_with_session, event_avec_tarif):
    """
    calcul_total_centimes() retourne le total en int centimes.
    / calcul_total_centimes() returns total in int cents.
    """
    from BaseBillet.services_panier import PanierSession

    event, price = event_avec_tarif  # price = 10.00 EUR
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=3)

    assert panier.calcul_total_centimes() == 3000  # 3 x 10€ = 3000 centimes


# ==========================================================================
# Tests validate_ticket_cart_limits (Validation 5bis cart-aware)
# / Tests for validate_ticket_cart_limits (Validation 5bis cart-aware)
# ==========================================================================


@pytest.fixture
def event_avec_limites(tenant_context_lespass):
    """
    Event configure avec limites : jauge_max=10, max_per_user=4.
    Product max_per_user=3, Price Plein max_per_user=2.
    / Event with limits configured for max_per_user testing.
    """
    from datetime import timedelta
    from decimal import Decimal
    from django.utils import timezone
    from BaseBillet.models import Event, Price, Product

    event = Event.objects.create(
        name=f"EvtLim {uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=7),
        jauge_max=10,
        max_per_user=4,
    )
    product = Product.objects.create(
        name=f"Billet {uuid.uuid4()}",
        categorie_article=Product.BILLET,
        max_per_user=3,
    )
    event.products.add(product)
    price = Price.objects.create(
        product=product, name="Plein", prix=Decimal("10.00"),
        publish=True, max_per_user=2,
    )
    yield event, product, price


@pytest.mark.django_db
def test_add_ticket_refuse_si_panier_seul_depasse_event_max_per_user(
    request_with_session, event_avec_limites,
):
    """
    Panier anonyme : 2 items qty=2 chacun = 4 tickets. Event max_per_user=4.
    Un 3e add (qty=1) ferait 5 → refuse.
    / Cart alone > event.max_per_user → rejected.
    """
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    from decimal import Decimal
    from BaseBillet.models import Price

    event, product, price = event_avec_limites
    # Pour isoler le check event.max_per_user, on desactive product.max_per_user
    # (qui vaut 3) sinon il serait hit avant event.max_per_user (=4).
    # On cree aussi un 2eme price pour bypass price.max_per_user=2.
    # / To isolate event.max_per_user check, relax product.max_per_user (=3)
    # otherwise it triggers before event.max_per_user (=4). Add 2nd price too.
    product.max_per_user = None
    product.save()
    price2 = Price.objects.create(
        product=product, name="Plein 2", prix=Decimal("10.00"),
        publish=True, max_per_user=2,
    )
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=2)
    panier.add_ticket(event.uuid, price2.uuid, qty=2)  # total 4 = max_per_user

    # 5e ticket → dépasse event.max_per_user
    # / 5th ticket → exceeds event.max_per_user
    with pytest.raises(InvalidItemError) as exc_info:
        panier.add_ticket(event.uuid, price.uuid, qty=1)
    assert "per-user limit" in str(exc_info.value).lower() or \
           "event" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_add_ticket_refuse_si_panier_depasse_product_max_per_user(
    request_with_session, event_avec_limites,
):
    """
    Panier avec 3 billets (= product.max_per_user=3). Un 4e add → refuse.
    / Cart reaches product.max_per_user → next add rejected.
    """
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    from decimal import Decimal
    from BaseBillet.models import Price

    event, product, price = event_avec_limites
    # 2nd price sur le meme product pour pouvoir atteindre product.max_per_user=3
    # sans etre limite par price.max_per_user=2.
    # / 2nd price on same product to reach product limit without price limit.
    price2 = Price.objects.create(
        product=product, name="Plein 2", prix=Decimal("10.00"),
        publish=True, max_per_user=2,
    )
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=2)  # 2 sur price1
    panier.add_ticket(event.uuid, price2.uuid, qty=1)  # 1 sur price2 = 3 total product

    with pytest.raises(InvalidItemError) as exc_info:
        panier.add_ticket(event.uuid, price2.uuid, qty=1)  # 4 total product
    assert "product" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_add_ticket_refuse_si_panier_depasse_price_max_per_user(
    request_with_session, event_avec_limites,
):
    """
    Panier avec 2 billets sur price (= price.max_per_user=2). 3e → refuse.
    / Cart reaches price.max_per_user → next add rejected.
    """
    from BaseBillet.services_panier import PanierSession, InvalidItemError

    event, _product, price = event_avec_limites
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=2)  # = price.max_per_user

    with pytest.raises(InvalidItemError) as exc_info:
        panier.add_ticket(event.uuid, price.uuid, qty=1)
    assert "rate" in str(exc_info.value).lower() or \
           "per-user" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_add_ticket_accepte_exactement_a_la_limite(
    request_with_session, event_avec_limites,
):
    """
    Ajout pile a la limite (max_per_user=2, qty=2) → accepte.
    Cas "edge" : limite inclusive.
    / Adding exactly at limit (qty=max) → accepted. Edge case: inclusive limit.
    """
    from BaseBillet.services_panier import PanierSession

    event, _product, price = event_avec_limites  # price.max_per_user=2
    panier = PanierSession(request_with_session)
    panier.add_ticket(event.uuid, price.uuid, qty=2)  # exactement 2

    assert panier.count() == 2


@pytest.mark.django_db
def test_add_ticket_refuse_si_jauge_event_depassee(
    request_with_session, tenant_context_lespass,
):
    """
    Jauge event=5, pas de tickets existants, panier vide. Ajout qty=6 → refuse.
    / Event jauge=5, empty cart, adding qty=6 → rejected.
    """
    from datetime import timedelta
    from decimal import Decimal
    from django.utils import timezone
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    from BaseBillet.models import Event, Price, Product

    event = Event.objects.create(
        name=f"EvtJauge {uuid.uuid4()}",
        datetime=timezone.now() + timedelta(days=7),
        jauge_max=5,
        max_per_user=10,  # desactive pour isoler la jauge
    )
    product = Product.objects.create(
        name=f"Billet {uuid.uuid4()}", categorie_article=Product.BILLET,
    )
    event.products.add(product)
    price = Price.objects.create(
        product=product, name="Plein", prix=Decimal("10.00"),
        publish=True, max_per_user=10,
    )
    panier = PanierSession(request_with_session)

    with pytest.raises(InvalidItemError) as exc_info:
        panier.add_ticket(event.uuid, price.uuid, qty=6)  # > jauge_max
    assert "seat" in str(exc_info.value).lower() or \
           "available" in str(exc_info.value).lower() or \
           "place" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_add_ticket_user_auth_refuse_si_db_plus_cart_depasse_event_max(
    tenant_context_lespass, event_avec_limites,
):
    """
    User auth avec 2 tickets VALID en DB + 2 dans panier = 4 (event.max_per_user=4).
    5e ticket → refuse.
    / Auth user with 2 DB tickets + 2 cart = event.max. Next → rejected.
    """
    import uuid as uuid_mod
    from decimal import Decimal
    from datetime import timedelta
    from django.utils import timezone
    from django.test import RequestFactory
    from django.contrib.sessions.middleware import SessionMiddleware
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    from BaseBillet.models import (
        Event, Price, Product, Reservation, Ticket, ProductSold, PriceSold,
    )
    from AuthBillet.models import TibilletUser

    event, product, price = event_avec_limites
    # Desactiver product.max_per_user (=3) pour isoler event.max_per_user (=4).
    # / Relax product.max_per_user to isolate event check.
    product.max_per_user = None
    product.save()

    user = TibilletUser.objects.create(
        email=f"limit-{uuid_mod.uuid4()}@example.org",
        username=f"limit-{uuid_mod.uuid4()}",
        is_active=True,
    )
    # Creer 2 tickets VALID en DB pour ce user/event/price
    # / Create 2 VALID tickets in DB for this user/event/price
    product_sold = ProductSold.objects.create(product=product)
    price_sold = PriceSold.objects.create(
        productsold=product_sold, price=price, prix=price.prix,
    )
    reservation = Reservation.objects.create(
        user_commande=user, event=event, status=Reservation.PAID,
    )
    for _i in range(2):
        Ticket.objects.create(
            reservation=reservation, pricesold=price_sold,
            status=Ticket.NOT_SCANNED,
        )

    # Creer request avec user auth
    # / Create request with auth user
    factory = RequestFactory()
    request = factory.post('/')
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request.user = user

    panier = PanierSession(request)
    # Ajouter 2 dans le panier → DB (2) + cart (2) = 4 = event.max_per_user
    # Mais price.max_per_user=2 limite aussi → on change de price pour bypass
    from BaseBillet.models import Price as PriceModel
    price2 = PriceModel.objects.create(
        product=product, name="Plein 2", prix=Decimal("10.00"),
        publish=True, max_per_user=2,
    )
    panier.add_ticket(event.uuid, price2.uuid, qty=2)  # DB 2 + cart 2 = 4 OK

    # 5e ticket → depasse event.max_per_user=4
    # / 5th ticket → exceeds event.max_per_user
    with pytest.raises(InvalidItemError):
        panier.add_ticket(event.uuid, price2.uuid, qty=1)


@pytest.mark.django_db
def test_add_ticket_jauge_compte_under_purchase(
    tenant_context_lespass, event_avec_limites,
):
    """
    Jauge=10. Autre user a 8 tickets CREATED (<15min = under_purchase).
    Panier courant 2 tickets → total 10 = jauge. Un 3e → refuse (11 > 10).
    / Jauge 10 with 8 under-purchase tickets from another user. Cart 2 ok,
    but next add would exceed.
    """
    import uuid as uuid_mod
    from decimal import Decimal
    from django.utils import timezone
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    from BaseBillet.models import (
        Event, Price, Product, Reservation, Ticket, ProductSold, PriceSold,
    )
    from AuthBillet.models import TibilletUser

    event, product, price = event_avec_limites
    # Pousser max_per_user pour isoler la jauge
    # / Relax max_per_user to isolate jauge check
    event.max_per_user = 100
    event.save()
    price.max_per_user = 100
    price.save()
    product.max_per_user = 100
    product.save()

    # Autre user avec 8 tickets CREATED (under_purchase)
    # / Other user with 8 under_purchase tickets
    other = TibilletUser.objects.create(
        email=f"other-{uuid_mod.uuid4()}@example.org",
        username=f"other-{uuid_mod.uuid4()}",
        is_active=True,
    )
    product_sold = ProductSold.objects.create(product=product)
    price_sold = PriceSold.objects.create(
        productsold=product_sold, price=price, prix=price.prix,
    )
    reservation = Reservation.objects.create(
        user_commande=other, event=event, status=Reservation.UNPAID,
    )
    # Force datetime recent pour que under_purchase() les compte
    # / Force recent datetime so under_purchase() counts them
    reservation.datetime = timezone.now()
    reservation.save()
    for _i in range(8):
        Ticket.objects.create(
            reservation=reservation, pricesold=price_sold,
            status=Ticket.CREATED,
        )

    # Panier courant (user anonyme) : 2 tickets OK (8 + 2 = 10 = jauge)
    # / Current cart (anon): 2 tickets OK
    from django.test import RequestFactory
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.contrib.auth.models import AnonymousUser
    factory = RequestFactory()
    request = factory.post('/')
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request.user = AnonymousUser()
    panier = PanierSession(request)
    panier.add_ticket(event.uuid, price.uuid, qty=2)

    # 3e → 11 > 10 jauge
    # / 3rd → 11 > 10 jauge
    with pytest.raises(InvalidItemError) as exc_info:
        panier.add_ticket(event.uuid, price.uuid, qty=1)
    assert "seat" in str(exc_info.value).lower() or \
           "available" in str(exc_info.value).lower() or \
           "place" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_revalidate_all_detecte_limite_depassee_entre_ajout_et_checkout(
    tenant_context_lespass, event_avec_limites,
):
    """
    Scenario : user ajoute 2 billets, entre l'ajout et le checkout un autre
    user fait saturer la jauge de l'event. revalidate_all() doit detecter.
    / User adds 2 tickets, another user fills the jauge, then revalidate_all
    detects the overflow at checkout.
    """
    import uuid as uuid_mod
    from decimal import Decimal
    from django.utils import timezone
    from django.test import RequestFactory
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.contrib.auth.models import AnonymousUser
    from BaseBillet.services_panier import PanierSession, InvalidItemError
    from BaseBillet.models import (
        Event, Price, Product, Reservation, Ticket, ProductSold, PriceSold,
    )
    from AuthBillet.models import TibilletUser

    event, product, price = event_avec_limites
    event.max_per_user = 100
    event.save()
    price.max_per_user = 100
    price.save()
    product.max_per_user = 100
    product.save()
    event.jauge_max = 3
    event.save()

    # 1. User 1 (anonyme) ajoute 2 billets — jauge=3, DB vide, cart 2 → OK
    # / User 1 (anon) adds 2 tickets — jauge=3, DB empty, cart 2 → OK
    factory = RequestFactory()
    request = factory.post('/')
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request.user = AnonymousUser()
    panier = PanierSession(request)
    panier.add_ticket(event.uuid, price.uuid, qty=2)
    assert panier.count() == 2

    # 2. Entre-temps, un autre user fait 2 reservations VALID
    # / Meanwhile, another user makes 2 VALID reservations
    other = TibilletUser.objects.create(
        email=f"o-{uuid_mod.uuid4()}@example.org",
        username=f"o-{uuid_mod.uuid4()}",
        is_active=True,
    )
    product_sold = ProductSold.objects.create(product=product)
    price_sold = PriceSold.objects.create(
        productsold=product_sold, price=price, prix=price.prix,
    )
    reservation = Reservation.objects.create(
        user_commande=other, event=event, status=Reservation.PAID,
    )
    for _i in range(2):
        Ticket.objects.create(
            reservation=reservation, pricesold=price_sold,
            status=Ticket.NOT_SCANNED,
        )

    # 3. Au checkout, revalidate_all() re-injecte le panier : 2 DB + 2 cart = 4 > 3
    # / At checkout, revalidate_all() re-injects cart: 2 DB + 2 cart > jauge
    with pytest.raises(InvalidItemError):
        panier.revalidate_all()


