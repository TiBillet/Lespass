"""
Tests — API v2 réservation « payée en caisse » (LaBoutik POS).
/ Tests — API v2 reservation "paid at the POS" (LaBoutik).

LOCALISATION : tests/pytest/test_api_v2_reservation_laboutik.py

Route testée : POST /api/v2/reservations/
Cas d'usage : la caisse LaBoutik vend un billet payé en espèce ou carte
bancaire. Elle envoie la vente à Lespass avec :
- additionalProperty paymentMethod = "cash" ou "card"
- PAS de reservationFor : Lespass déduit l'événement depuis le tarif.

Comportement attendu :
- Réservation créée directement VALID (pas de checkout Stripe).
- Tickets créés NOT_SCANNED (payés, prêts à scanner).
- LigneArticle créée VALID, payment_method CASH ou CC, sale_origin LABOUTIK.

NOTE TECHNIQUE : ces tests réutilisent la base de données dev existante
(pattern V2 onboard). On crée les objets dans tenant_context(lespass) puis on
appelle la vue via APIClient avec SERVER_NAME pour que le middleware tenant
résolve le schéma 'lespass'.
/ TECHNICAL NOTE: reuse dev DB; create objects in tenant_context then call
the view through APIClient with SERVER_NAME.
"""

import uuid as uuidlib
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient


# ---------------------------------------------------------------------------
# Réutiliser la DB dev au lieu d'une test DB temporaire (pattern onboard V2).
# / Reuse the dev DB instead of a temporary test DB.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def django_db_setup():
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


pytestmark = pytest.mark.django_db

PATH = "/api/v2/reservations/"
HOST = "lespass.tibillet.localhost"


def _suffix():
    """Suffixe court unique pour éviter les collisions de noms.
    / Short unique suffix to avoid name collisions."""
    return uuidlib.uuid4().hex[:6]


@pytest.fixture
def pos_setup():
    """
    Crée dans le tenant 'lespass' : un événement futur publié, un produit
    billet avec un tarif payant lié à l'événement, et une clé API avec la
    permission 'reservation'. Nettoie tout en fin de test.
    / Create a future published event, a ticket product with a paid price
    linked to the event, and an API key with the 'reservation' permission.
    Cleans everything afterwards.
    """
    from Customers.models import Client
    from BaseBillet.models import Event, Product, Price, ExternalApiKey
    from rest_framework_api_key.models import APIKey

    tenant = Client.objects.get(schema_name="lespass")
    suffix = _suffix()

    with tenant_context(tenant):
        event = Event.objects.create(
            name=f"Concert caisse {suffix}",
            datetime=timezone.now() + timedelta(days=10),
            published=True,
        )
        product = Product.objects.create(
            name=f"Billet caisse {suffix}",
            categorie_article=Product.BILLET,
        )
        price = Price.objects.create(
            product=product,
            name=f"Plein tarif {suffix}",
            prix=Decimal("10.00"),
        )
        event.products.add(product)

        api_obj, key_str = APIKey.objects.create_key(name=f"poskey-{suffix}")
        ext_key = ExternalApiKey.objects.create(
            name=f"poskey-{suffix}",
            key=api_obj,
            reservation=True,
        )

    data = {
        "tenant": tenant,
        "event": event,
        "product": product,
        "price": price,
        "key": key_str,
    }
    yield data

    # Nettoyage / Cleanup
    # PIEGE : ne pas supprimer Event/Product/Price ici.
    # 1) Les ventes creees protegent ces objets (FK PROTECT -> ProtectedError).
    # 2) stdimage plante au post_delete quand l'objet n'a pas d'image
    #    (get_variation_name(None) -> TypeError).
    # La DB dev est partagee : on laisse les objets suffixes en base
    # (pattern test_comptabilite_service.py) et on depublie l'event.
    # / TRAP: do not delete Event/Product/Price here (PROTECT FKs + stdimage
    # / post_delete crash on imageless objects). Unpublish instead.
    with tenant_context(tenant):
        event.published = False
        event.save(update_fields=["published"])
        ext_key.delete()
        api_obj.delete()


def _post(payload, key):
    """Effectue le POST sur la route en résolvant le tenant via SERVER_NAME.
    / Perform the POST, resolving the tenant via SERVER_NAME."""
    client = APIClient()
    return client.post(
        PATH,
        payload,
        format="json",
        SERVER_NAME=HOST,
        HTTP_AUTHORIZATION=f"Api-Key {key}",
    )


def test_vente_caisse_cash_sans_event_cree_reservation_valide(pos_setup):
    """
    Une vente en espèces depuis la caisse, sans reservationFor :
    Lespass déduit l'événement et crée une réservation valide sans Stripe.
    / Cash sale from the POS without reservationFor: Lespass resolves the
    event and creates a valid reservation without Stripe.
    """
    from BaseBillet.models import (
        Reservation, Ticket, LigneArticle, PaymentMethod, SaleOrigin,
    )

    email_client = f"client-caisse-{_suffix()}@example.org"
    payload = {
        "@context": "https://schema.org",
        "@type": "Reservation",
        "underName": {"@type": "Person", "email": email_client},
        "reservedTicket": [
            {
                "@type": "Ticket",
                "identifier": str(pos_setup["price"].uuid),
                "ticketQuantity": 2,
            }
        ],
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "paymentMethod", "value": "cash"},
        ],
    }

    response = _post(payload, pos_setup["key"])
    assert response.status_code == 201, f"{response.status_code} {response.data}"

    with tenant_context(pos_setup["tenant"]):
        reservation = Reservation.objects.get(uuid=response.data["identifier"])

        # La réservation est valide tout de suite : le client a déjà payé.
        # / The reservation is valid right away: the customer already paid.
        assert reservation.status == Reservation.VALID
        assert reservation.event == pos_setup["event"]

        # Les billets sont payés, prêts à être scannés.
        # / Tickets are paid, ready to be scanned.
        tickets = reservation.tickets.all()
        assert tickets.count() == 2
        for ticket in tickets:
            assert ticket.status == Ticket.NOT_SCANNED

        # Une seule ligne de vente, valide, en espèces, origine LaBoutik.
        # / One single sale line, valid, cash, LaBoutik origin.
        lignes = reservation.lignearticles.all()
        assert lignes.count() == 1
        ligne = lignes.first()
        assert ligne.status == LigneArticle.VALID
        assert ligne.payment_method == PaymentMethod.CASH
        assert ligne.sale_origin == SaleOrigin.LABOUTIK
        assert ligne.qty == 2


def test_vente_caisse_card_avec_event_explicite(pos_setup):
    """
    Une vente en carte bancaire avec reservationFor explicite :
    la ligne de vente porte le moyen de paiement CC.
    / Card sale with explicit reservationFor: sale line carries CC.
    """
    from BaseBillet.models import Reservation, LigneArticle, PaymentMethod

    payload = {
        "@context": "https://schema.org",
        "@type": "Reservation",
        "reservationFor": {"@type": "Event", "identifier": str(pos_setup["event"].uuid)},
        "underName": {"@type": "Person", "email": f"client-cb-{_suffix()}@example.org"},
        "reservedTicket": [
            {
                "@type": "Ticket",
                "identifier": str(pos_setup["price"].uuid),
                "ticketQuantity": 1,
            }
        ],
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "paymentMethod", "value": "card"},
        ],
    }

    response = _post(payload, pos_setup["key"])
    assert response.status_code == 201, f"{response.status_code} {response.data}"

    with tenant_context(pos_setup["tenant"]):
        reservation = Reservation.objects.get(uuid=response.data["identifier"])
        assert reservation.status == Reservation.VALID
        ligne = reservation.lignearticles.first()
        assert ligne.status == LigneArticle.VALID
        assert ligne.payment_method == PaymentMethod.CC


def test_vente_caisse_payment_method_inconnu_renvoie_400(pos_setup):
    """
    Un paymentMethod inconnu est refusé avec une erreur claire.
    / An unknown paymentMethod is rejected with a clear error.
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "Reservation",
        "underName": {"@type": "Person", "email": f"client-{_suffix()}@example.org"},
        "reservedTicket": [
            {
                "@type": "Ticket",
                "identifier": str(pos_setup["price"].uuid),
                "ticketQuantity": 1,
            }
        ],
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "paymentMethod", "value": "bitcoin"},
        ],
    }

    response = _post(payload, pos_setup["key"])
    assert response.status_code == 400


def test_resolution_event_ambigue_renvoie_400(pos_setup):
    """
    Deux événements futurs proposent le même produit : sans reservationFor,
    Lespass refuse avec une erreur claire.
    / Two future events offer the same product: without reservationFor,
    Lespass rejects with a clear error.
    """
    from BaseBillet.models import Event

    with tenant_context(pos_setup["tenant"]):
        autre_event = Event.objects.create(
            name=f"Concert bis {_suffix()}",
            datetime=timezone.now() + timedelta(days=20),
            published=True,
        )
        autre_event.products.add(pos_setup["product"])

    payload = {
        "@context": "https://schema.org",
        "@type": "Reservation",
        "underName": {"@type": "Person", "email": f"client-{_suffix()}@example.org"},
        "reservedTicket": [
            {
                "@type": "Ticket",
                "identifier": str(pos_setup["price"].uuid),
                "ticketQuantity": 1,
            }
        ],
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "paymentMethod", "value": "cash"},
        ],
    }

    response = _post(payload, pos_setup["key"])

    # Depublier au lieu de supprimer (piege stdimage post_delete, cf. fixture).
    # / Unpublish instead of deleting (stdimage post_delete trap, see fixture).
    with tenant_context(pos_setup["tenant"]):
        autre_event.published = False
        autre_event.save(update_fields=["published"])

    assert response.status_code == 400


def test_aucun_event_futur_renvoie_400(pos_setup):
    """
    Le produit n'est lié à aucun événement futur : erreur claire.
    / The product is not linked to any future event: clear error.
    """
    from BaseBillet.models import Product, Price

    with tenant_context(pos_setup["tenant"]):
        produit_orphelin = Product.objects.create(
            name=f"Billet orphelin {_suffix()}",
            categorie_article=Product.BILLET,
        )
        price_orphelin = Price.objects.create(
            product=produit_orphelin,
            name=f"Tarif orphelin {_suffix()}",
            prix=Decimal("5.00"),
        )

    payload = {
        "@context": "https://schema.org",
        "@type": "Reservation",
        "underName": {"@type": "Person", "email": f"client-{_suffix()}@example.org"},
        "reservedTicket": [
            {
                "@type": "Ticket",
                "identifier": str(price_orphelin.uuid),
                "ticketQuantity": 1,
            }
        ],
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "paymentMethod", "value": "cash"},
        ],
    }

    response = _post(payload, pos_setup["key"])

    # On laisse le produit orphelin en base (piege stdimage post_delete,
    # cf. fixture). Il n'est lie a aucun event : aucune pollution.
    # / Leave the orphan product in DB (stdimage post_delete trap, see
    # / fixture). It is linked to no event: no pollution.
    assert response.status_code == 400
