"""
Tests — un seul ticket par billet reserve, meme sur un sous-evenement.
/ Tests — exactly one ticket per reserved seat, even on a sub-event.

LOCALISATION : tests/pytest/test_reservation_subevent_tickets.py

CONTEXTE DU BUG :
Un sous-evenement (Event avec un parent) est force en categorie ACTION par
Event.save(). Avant le correctif, TicketCreator executait DEUX chemins pour un
sous-evenement qui avait AUSSI un produit reservable :
  1. la boucle sur products_dict (cree le bon ticket, avec pricesold) ;
  2. method_A (cree un 2e ticket "benevole" SANS pricesold -> identifier vide).
Resultat : 2 tickets pour 1 place reservee, le 2e vide.

LE CORRECTIF (BaseBillet/validators.py) : method_A n'est appele QUE si aucun
produit n'a ete traite (products_dict vide). On verifie ici les 3 cas demandes :
- event normal (sans ACTION) + billet            -> 1 ticket
- event ACTION (benevolat) SANS produit          -> 1 ticket (method_A)
- sous-event ACTION AVEC produit billet           -> 1 ticket (correctif)
Plus un test via l'API v2 reproduisant le scenario exact remonte.

/ A sub-event is forced to ACTION category. Before the fix, a sub-event that
also had a bookable product got TWO tickets (the real one + an empty one from
method_A). The fix only calls method_A when no product was handled.

NOTE TECHNIQUE : on reutilise la DB dev (pattern onboard V2) et on appelle le
validateur dans tenant_context. Le cas "ACTION pur sans produit" n'est pas
atteignable via l'API v2 (reservedTicket y est obligatoire), on le teste donc
au niveau du validateur, la ou vit le bug.
/ TECHNICAL NOTE: reuse dev DB; call the validator inside tenant_context. The
"pure ACTION without product" case is not reachable via API v2 (reservedTicket
is required there), so it is tested at the validator level where the bug lives.
"""

import uuid as uuidlib
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import QueryDict
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient


@pytest.fixture(scope="session")
def django_db_setup():
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


pytestmark = pytest.mark.django_db

HOST = "lespass.tibillet.localhost"


def _suffix():
    """Suffixe court unique pour eviter les collisions de noms.
    / Short unique suffix to avoid name collisions."""
    return uuidlib.uuid4().hex[:6]


@pytest.fixture
def resa_setup():
    """
    Cree dans 'lespass' :
    - un evenement NORMAL publie + un produit gratuit (cas 1) ;
    - un evenement PARENT publie ;
    - un SOUS-evenement benevole (parent, ACTION) SANS produit (cas 2) ;
    - un SOUS-evenement (parent, ACTION) AVEC un produit gratuit (cas 3) ;
    - une cle API avec la permission 'reservation' (pour le test API v2).
    Nettoie en depubliant (piege stdimage post_delete + FK PROTECT).
    / Create a normal event + free product, a parent event, a volunteer
    sub-event without product, a sub-event with a free product, and an API key.
    """
    from Customers.models import Client
    from BaseBillet.models import Event, Product, Price, ExternalApiKey
    from rest_framework_api_key.models import APIKey

    tenant = Client.objects.get(schema_name="lespass")
    suffix = _suffix()

    with tenant_context(tenant):
        # --- Cas 1 : evenement normal (pas ACTION) + produit gratuit ---
        # / Case 1: normal event (not ACTION) + free product
        event_normal = Event.objects.create(
            name=f"Concert normal {suffix}",
            datetime=timezone.now() + timedelta(days=10),
            published=True,
        )
        product_normal = Product.objects.create(
            name=f"Entree gratuite {suffix}",
            categorie_article=Product.FREERES,
        )
        price_normal = Price.objects.create(
            product=product_normal,
            name=f"Gratuit {suffix}",
            prix=Decimal("0"),
        )
        event_normal.products.add(product_normal)

        # --- Evenement parent ---
        # / Parent event
        event_parent = Event.objects.create(
            name=f"Festival {suffix}",
            datetime=timezone.now() + timedelta(days=10),
            published=True,
        )

        # --- Cas 2 : sous-evenement benevole (ACTION) SANS produit ---
        # parent -> Event.save() force categorie=ACTION + easy_reservation=True
        # / Case 2: volunteer sub-event (ACTION) WITHOUT product
        sous_event_benevole = Event.objects.create(
            name=f"Benevolat accueil {suffix}",
            datetime=timezone.now() + timedelta(days=11),
            published=True,
            parent=event_parent,
        )

        # --- Cas 3 : sous-evenement (ACTION) AVEC produit gratuit ---
        # / Case 3: sub-event (ACTION) WITH a free product
        sous_event_billet = Event.objects.create(
            name=f"Atelier sur inscription {suffix}",
            datetime=timezone.now() + timedelta(days=12),
            published=True,
            parent=event_parent,
        )
        product_billet = Product.objects.create(
            name=f"Place atelier {suffix}",
            categorie_article=Product.FREERES,
        )
        price_billet = Price.objects.create(
            product=product_billet,
            name=f"Place {suffix}",
            prix=Decimal("0"),
        )
        sous_event_billet.products.add(product_billet)

        api_obj, key_str = APIKey.objects.create_key(name=f"resakey-{suffix}")
        ext_key = ExternalApiKey.objects.create(
            name=f"resakey-{suffix}",
            key=api_obj,
            reservation=True,
        )

    data = {
        "tenant": tenant,
        "event_normal": event_normal,
        "price_normal": price_normal,
        "sous_event_benevole": sous_event_benevole,
        "sous_event_billet": sous_event_billet,
        "price_billet": price_billet,
        "key": key_str,
    }
    yield data

    # Nettoyage : on depublie (cf. test_api_v2_reservation_laboutik).
    # / Cleanup: unpublish (see test_api_v2_reservation_laboutik).
    with tenant_context(tenant):
        for ev in (event_normal, event_parent, sous_event_benevole, sous_event_billet):
            ev.published = False
            ev.save(update_fields=["published"])
        ext_key.delete()
        api_obj.delete()


def _reserver_via_validator(tenant, event, price_qty=None):
    """Cree une reservation en appelant directement ReservationValidator
    (chemin partage front + API, la ou vit le bug). Retourne la reservation.
    / Create a reservation by calling ReservationValidator directly. Returns it.
    """
    from BaseBillet.validators import ReservationValidator
    from BaseBillet.models import SaleOrigin

    email = f"resa-{_suffix()}@example.org"
    data = QueryDict(mutable=True)
    data.update({"email": email, "event": str(event.pk)})
    if price_qty:
        for price_uuid, qty in price_qty.items():
            data.update({str(price_uuid): str(qty)})

    fake_request = SimpleNamespace(user=AnonymousUser(), data=data)
    with tenant_context(tenant):
        validator = ReservationValidator(
            data=data,
            context={"request": fake_request, "sale_origin": SaleOrigin.LESPASS},
        )
        validator.is_valid(raise_exception=True)
        return validator.reservation


def test_event_normal_avec_billet_un_seul_ticket(resa_setup):
    """Cas 1 : un evenement normal (pas ACTION) avec un produit reservable
    cree UN seul ticket. / Case 1: a normal event with a product -> one ticket.
    """
    reservation = _reserver_via_validator(
        resa_setup["tenant"],
        resa_setup["event_normal"],
        price_qty={resa_setup["price_normal"].uuid: 1},
    )
    with tenant_context(resa_setup["tenant"]):
        assert reservation.tickets.count() == 1


def test_sous_event_action_sans_produit_un_seul_ticket(resa_setup):
    """Cas 2 : un sous-evenement benevole (ACTION) SANS produit cree UN seul
    ticket (la place benevole via method_A).
    / Case 2: a volunteer sub-event (ACTION) without product -> one ticket.
    """
    reservation = _reserver_via_validator(
        resa_setup["tenant"],
        resa_setup["sous_event_benevole"],
    )
    with tenant_context(resa_setup["tenant"]):
        tickets = reservation.tickets.all()
        assert tickets.count() == 1


def test_sous_event_action_avec_billet_un_seul_ticket(resa_setup):
    """Cas 3 (LE BUG) : un sous-evenement (ACTION car il a un parent) AVEC un
    produit reservable cree UN seul ticket, pas deux. Avant le correctif, un 2e
    ticket vide (sans pricesold) etait cree par method_A.
    / Case 3 (THE BUG): a sub-event (ACTION) WITH a product -> one ticket only.
    """
    reservation = _reserver_via_validator(
        resa_setup["tenant"],
        resa_setup["sous_event_billet"],
        price_qty={resa_setup["price_billet"].uuid: 1},
    )
    with tenant_context(resa_setup["tenant"]):
        tickets = reservation.tickets.all()
        assert tickets.count() == 1, (
            f"Un sous-evenement avec billet doit avoir 1 ticket, obtenu {tickets.count()}"
        )
        # Le ticket porte bien un pricesold (pas le ticket vide de method_A).
        # / The ticket carries a pricesold (not method_A's empty ticket).
        assert tickets.first().pricesold is not None


def test_api_v2_sous_event_action_avec_billet_un_seul_ticket(resa_setup):
    """Reproduit le scenario exact remonte : POST /api/v2/reservations/ sur un
    SOUS-evenement avec 1 reservedTicket -> la reponse ne contient qu'UN ticket
    (pas de second ticket avec identifier vide).
    / Reproduces the reported scenario via the API: one reservedTicket on a
    sub-event -> exactly one ticket in the response (no empty-identifier ticket).
    """
    from BaseBillet.models import Reservation

    payload = {
        "@context": "https://schema.org",
        "@type": "Reservation",
        "reservationFor": {
            "@type": "Event",
            "identifier": str(resa_setup["sous_event_billet"].uuid),
        },
        "underName": {"@type": "Person", "email": f"api-resa-{_suffix()}@example.org"},
        "reservedTicket": [
            {
                "@type": "Ticket",
                "identifier": str(resa_setup["price_billet"].uuid),
                "ticketQuantity": 1,
            }
        ],
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "confirmed", "value": True}
        ],
    }

    client = APIClient()
    response = client.post(
        "/api/v2/reservations/",
        payload,
        format="json",
        SERVER_NAME=HOST,
        HTTP_AUTHORIZATION=f"Api-Key {resa_setup['key']}",
    )
    assert response.status_code == 201, f"{response.status_code} {response.data}"

    # La reponse ne doit lister qu'UN seul ticket, sans identifier vide.
    # / The response must list a single ticket, with no empty identifier.
    reserved = response.data.get("reservedTicket", [])
    total_qty = sum(item.get("ticketQuantity", 0) for item in reserved)
    assert total_qty == 1, f"Attendu 1 ticket, obtenu {total_qty} : {reserved}"
    for item in reserved:
        assert item.get("identifier"), f"Ticket sans identifier (ticket vide) : {item}"

    # Verification en base : une seule ligne Ticket pour cette reservation.
    # / DB check: a single Ticket row for this reservation.
    with tenant_context(resa_setup["tenant"]):
        reservation = Reservation.objects.get(uuid=response.data["identifier"])
        assert reservation.tickets.count() == 1
