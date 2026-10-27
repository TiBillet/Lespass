"""
Tests — API v2 : liste des réservations et champs du détail.
/ Tests — API v2: reservation list and detail fields.

LOCALISATION : tests/pytest/test_api_v2_reservation_liste.py

Route testée : GET /api/v2/reservations/?event=<uuid>
Cas d'usage : un lieu récupère la liste des inscrits à un atelier, avec pour
chacun l'e-mail, le prénom, le nom, le montant payé et les réponses au
formulaire dynamique.
/ Use case: a venue fetches the attendee list of a workshop.

Chaque test crée sa réservation par une vente en espèces (POST, comme la caisse
LaBoutik) : la réservation est valide et ses lignes de vente existent vraiment.
/ Each test creates its reservation through a cash sale (POST): the reservation
is valid and its sale lines really exist.
"""

import uuid as uuidlib
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient


pytestmark = pytest.mark.django_db

PATH = "/api/v2/reservations/"
HOST = "lespass.tibillet.localhost"


def _suffixe():
    """Suffixe court unique pour éviter les collisions de noms.
    / Short unique suffix to avoid name collisions."""
    return uuidlib.uuid4().hex[:6]


@pytest.fixture
def atelier(tenant):
    """
    Crée dans le tenant 'lespass' : un atelier futur publié, un tarif à 10 €
    et une clé API avec la permission 'reservation'.
    / Creates a published future workshop, a 10 € price and an API key.
    """
    from BaseBillet.models import Event, Product, Price, ExternalApiKey
    from rest_framework_api_key.models import APIKey

    suffixe = _suffixe()

    with tenant_context(tenant):
        evenement = Event.objects.create(
            name=f"Atelier liste {suffixe}",
            datetime=timezone.now() + timedelta(days=10),
            published=True,
        )
        produit = Product.objects.create(
            name=f"Place atelier {suffixe}",
            categorie_article=Product.BILLET,
        )
        tarif = Price.objects.create(
            product=produit,
            name=f"Plein tarif {suffixe}",
            prix=Decimal("10.00"),
        )
        evenement.products.add(produit)

        objet_cle_api, cle_api_en_clair = APIKey.objects.create_key(
            name=f"liste-{suffixe}"
        )
        cle_externe = ExternalApiKey.objects.create(
            name=f"liste-{suffixe}",
            key=objet_cle_api,
            reservation=True,
        )

    yield {
        "tenant": tenant,
        "evenement": evenement,
        "tarif": tarif,
        "cle": cle_api_en_clair,
    }

    # On ne supprime ni l'événement ni le tarif : les ventes les protègent (FK PROTECT).
    # L'événement est dépublié, la clé API supprimée.
    # / Event and price are protected by the sales: unpublish, delete the key only.
    with tenant_context(tenant):
        evenement.published = False
        evenement.save(update_fields=["published"])
        cle_externe.delete()
        objet_cle_api.delete()


def _client_api(cle):
    """Client API qui résout le tenant 'lespass' et porte la clé.
    / API client resolving the 'lespass' tenant, with the key."""
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Api-Key {cle}")
    return client


def _vendre_en_especes(atelier, nombre_de_places):
    """
    Vend des places en espèces par l'API (comme la caisse) et renvoie l'uuid
    de la réservation créée.
    / Sells seats in cash through the API and returns the reservation uuid.
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "Reservation",
        "reservationFor": {
            "@type": "Event",
            "identifier": str(atelier["evenement"].uuid),
        },
        "underName": {"@type": "Person", "email": f"inscrit-{_suffixe()}@example.org"},
        "reservedTicket": [
            {
                "@type": "Ticket",
                "identifier": str(atelier["tarif"].uuid),
                "ticketQuantity": nombre_de_places,
            }
        ],
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "paymentMethod", "value": "cash"},
        ],
    }
    reponse = _client_api(atelier["cle"]).post(
        PATH, payload, format="json", SERVER_NAME=HOST
    )
    assert reponse.status_code == 201, f"{reponse.status_code} {reponse.data}"
    return reponse.data["identifier"]


def _lire_la_liste_de_l_atelier(atelier):
    """GET de la liste filtrée sur l'atelier. / GET the list filtered on the workshop."""
    reponse = _client_api(atelier["cle"]).get(
        PATH,
        {"event": str(atelier["evenement"].uuid)},
        SERVER_NAME=HOST,
    )
    assert reponse.status_code == 200, f"{reponse.status_code} {reponse.data}"
    return reponse.data["results"]


def _trouver_dans_la_liste(resultats, uuid_de_la_reservation):
    """La réservation de la liste qui porte cet uuid. / The listed reservation with this uuid."""
    for reservation in resultats:
        if reservation["identifier"] == str(uuid_de_la_reservation):
            return reservation
    raise AssertionError(f"Réservation {uuid_de_la_reservation} absente de la liste")


def test_liste_filtree_ne_renvoie_que_les_reservations_de_l_evenement(atelier):
    """
    Avec ?event=<uuid>, la liste contient la réservation de l'atelier, et
    seulement des réservations de cet atelier.
    / With ?event=<uuid>, the list holds the workshop's reservation, and only those.
    """
    uuid_de_la_reservation = _vendre_en_especes(atelier, nombre_de_places=1)

    resultats = _lire_la_liste_de_l_atelier(atelier)

    _trouver_dans_la_liste(resultats, uuid_de_la_reservation)
    for reservation in resultats:
        assert reservation["reservationFor"]["identifier"] == str(
            atelier["evenement"].uuid
        )


def test_identifiant_d_evenement_invalide_renvoie_400(atelier):
    """Un ?event= qui n'est pas un uuid est refusé. / A non-uuid ?event= is rejected."""
    reponse = _client_api(atelier["cle"]).get(
        PATH, {"event": "pas-un-uuid"}, SERVER_NAME=HOST
    )

    assert reponse.status_code == 400


def test_reservation_payee_renvoie_le_montant_paye_en_euros(atelier):
    """
    Deux places à 10 € payées en espèces : totalPrice vaut "20.00" EUR et la
    réservation ressort confirmée.
    / Two 10 € seats paid in cash: totalPrice is "20.00" EUR, status confirmed.
    """
    uuid_de_la_reservation = _vendre_en_especes(atelier, nombre_de_places=2)

    reservation = _trouver_dans_la_liste(
        _lire_la_liste_de_l_atelier(atelier), uuid_de_la_reservation
    )

    assert reservation["totalPrice"] == "20.00"
    assert reservation["priceCurrency"] == "EUR"
    assert reservation["reservationStatus"] == "https://schema.org/ReservationConfirmed"


def test_prenom_et_nom_viennent_du_compte_qui_reserve(atelier):
    """
    givenName et familyName sont ceux du compte de la personne qui réserve.
    / givenName and familyName come from the booking account.
    """
    from BaseBillet.models import Reservation

    uuid_de_la_reservation = _vendre_en_especes(atelier, nombre_de_places=1)
    with tenant_context(atelier["tenant"]):
        compte_qui_reserve = Reservation.objects.get(
            uuid=uuid_de_la_reservation
        ).user_commande
        compte_qui_reserve.first_name = "Ada"
        compte_qui_reserve.last_name = "Lovelace"
        compte_qui_reserve.save(update_fields=["first_name", "last_name"])

    reservation = _trouver_dans_la_liste(
        _lire_la_liste_de_l_atelier(atelier), uuid_de_la_reservation
    )

    assert reservation["underName"]["email"] == compte_qui_reserve.email
    assert reservation["underName"]["givenName"] == "Ada"
    assert reservation["underName"]["familyName"] == "Lovelace"


def test_reponses_du_formulaire_dynamique_dans_custom_form(atelier):
    """
    Les réponses au formulaire dynamique ressortent dans additionalProperty,
    sous le nom "customForm", rangées par libellé de question.
    / Dynamic form answers come out in additionalProperty, named "customForm".
    """
    from BaseBillet.models import Reservation

    reponses_au_formulaire = {"Régime alimentaire": "Végétarien", "Niveau": "Débutant"}
    uuid_de_la_reservation = _vendre_en_especes(atelier, nombre_de_places=1)
    with tenant_context(atelier["tenant"]):
        Reservation.objects.filter(uuid=uuid_de_la_reservation).update(
            custom_form=reponses_au_formulaire,
        )

    reservation = _trouver_dans_la_liste(
        _lire_la_liste_de_l_atelier(atelier), uuid_de_la_reservation
    )

    assert reservation["additionalProperty"] == [
        {
            "@type": "PropertyValue",
            "name": "customForm",
            "value": reponses_au_formulaire,
        },
    ]


def test_reservation_annulee_ressort_annulee(atelier):
    """
    Une réservation annulée reste dans la liste, avec le statut schema.org
    ReservationCancelled.
    / A cancelled reservation stays listed, with status ReservationCancelled.
    """
    from BaseBillet.models import Reservation

    uuid_de_la_reservation = _vendre_en_especes(atelier, nombre_de_places=1)
    with tenant_context(atelier["tenant"]):
        Reservation.objects.filter(uuid=uuid_de_la_reservation).update(
            status=Reservation.CANCELED
        )

    reservation = _trouver_dans_la_liste(
        _lire_la_liste_de_l_atelier(atelier), uuid_de_la_reservation
    )

    assert reservation["reservationStatus"] == "https://schema.org/ReservationCancelled"
