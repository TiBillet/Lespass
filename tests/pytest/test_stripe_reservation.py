"""
Tests pytest : reservations avec paiement Stripe (mock).
/ Pytest tests: reservations with Stripe payment (mocked).

Conversion de :
- PW 09 : anonymous-events.spec.ts (gratuit + payant + options)
- PW 10 : anonymous-event-dynamic-form.spec.ts (champs dynamiques)
"""

import json
import random
import string
from datetime import datetime, timedelta, timezone

import pytest


def _random_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _create_event_and_product(api_client, auth_headers, event_name, product_name,
                               price_name, price_amount, category="Ticket booking",
                               form_fields=None, options_radio=None, options_checkbox=None):
    """Helper : cree un evenement + produit via API v2.
    / Helper: creates an event + product via API v2.

    Retourne (event_data, product_data, price_uuid).
    """
    start_date = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    # Créer l'événement / Create event
    event_payload = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": event_name,
        "startDate": start_date,
    }
    additional_property = []
    if options_radio:
        additional_property.append({
            "@type": "PropertyValue",
            "name": "optionsRadio",
            "value": options_radio,
        })
    if options_checkbox:
        additional_property.append({
            "@type": "PropertyValue",
            "name": "optionsCheckbox",
            "value": options_checkbox,
        })
    if additional_property:
        event_payload["additionalProperty"] = additional_property

    resp_event = api_client.post(
        "/api/v2/events/",
        data=json.dumps(event_payload),
        content_type="application/json",
        **auth_headers,
    )
    assert resp_event.status_code in (200, 201), (
        f"Création événement échouée ({resp_event.status_code}): {resp_event.content[:300]}"
    )
    event_data = resp_event.json()
    event_uuid = event_data["identifier"]

    # Créer le produit / Create product
    product_payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product_name,
        "description": f"Test mock Stripe - {product_name}",
        "category": category,
        "isRelatedTo": {"@type": "Event", "identifier": event_uuid},
        "offers": [{
            "@type": "Offer",
            "name": price_name,
            "price": price_amount,
            "priceCurrency": "EUR",
        }],
    }
    if form_fields:
        product_payload["additionalProperty"] = [{
            "@type": "PropertyValue",
            "name": "formFields",
            "value": form_fields,
        }]

    resp_product = api_client.post(
        "/api/v2/products/",
        data=json.dumps(product_payload),
        content_type="application/json",
        **auth_headers,
    )
    assert resp_product.status_code in (200, 201), (
        f"Création produit échouée ({resp_product.status_code}): {resp_product.content[:300]}"
    )
    product_data = resp_product.json()
    price_uuid = product_data["offers"][0]["identifier"]

    return event_data, product_data, price_uuid


def _create_reservation(api_client, auth_headers, event_uuid, price_uuid, email,
                          qty=1, options=None, custom_form=None):
    """Helper : cree une reservation via API v2.
    / Helper: creates a reservation via API v2.
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "Reservation",
        "reservationFor": {"@type": "Event", "identifier": event_uuid},
        "underName": {"@type": "Person", "email": email},
        "reservedTicket": [{
            "@type": "Ticket",
            "identifier": price_uuid,
            "ticketQuantity": qty,
        }],
    }
    additional_property = []
    if options:
        additional_property.append({
            "@type": "PropertyValue",
            "name": "options",
            "value": options,
        })
    if custom_form:
        additional_property.append({
            "@type": "PropertyValue",
            "name": "customForm",
            "value": custom_form,
        })
    if additional_property:
        payload["additionalProperty"] = additional_property

    return api_client.post(
        "/api/v2/reservations/",
        data=json.dumps(payload),
        content_type="application/json",
        **auth_headers,
    )


class TestStripeReservation:
    """Reservations avec mock Stripe / Reservations with mocked Stripe."""

    def test_anonymous_booking_free(self, api_client, auth_headers, mock_stripe):
        """PW 09 test 1 : reservation gratuite → pas de Stripe.
        / PW 09 test 1: free booking → no Stripe.
        """
        from django_tenants.utils import schema_context
        from BaseBillet.models import Reservation

        rid = _random_id()
        email = f"test+freebook{rid}@mock.test"

        event_data, _, price_uuid = _create_event_and_product(
            api_client, auth_headers,
            event_name=f"Free Event {rid}",
            product_name=f"Billets Free {rid}",
            price_name="Gratuit",
            price_amount="0.00",
            category="Free booking",
        )

        resp = _create_reservation(
            api_client, auth_headers,
            event_uuid=event_data["identifier"],
            price_uuid=price_uuid,
            email=email,
        )
        assert resp.status_code in (200, 201), (
            f"Réservation échouée ({resp.status_code}): {resp.content[:300]}"
        )

        # Pas de Stripe pour gratuit / No Stripe for free
        assert not mock_stripe.mock_create.called, (
            "Stripe ne devrait pas être appelé pour une réservation gratuite"
        )

        with schema_context("lespass"):
            reservation = Reservation.objects.filter(
                user_commande__email=email,
            ).order_by("-datetime").first()
            assert reservation is not None, f"Réservation non trouvée pour {email}"

    def test_anonymous_booking_paid(self, api_client, auth_headers, mock_stripe):
        """PW 09 test 2 : reservation payante → Stripe → Paiement_stripe cree.
        / PW 09 test 2: paid booking → Stripe → Paiement_stripe created.
        """
        from django_tenants.utils import schema_context
        from BaseBillet.models import Reservation, Paiement_stripe

        rid = _random_id()
        email = f"test+paidbook{rid}@mock.test"

        event_data, _, price_uuid = _create_event_and_product(
            api_client, auth_headers,
            event_name=f"Paid Event {rid}",
            product_name=f"Billets Paid {rid}",
            price_name="Plein tarif",
            price_amount="10.00",
        )

        resp = _create_reservation(
            api_client, auth_headers,
            event_uuid=event_data["identifier"],
            price_uuid=price_uuid,
            email=email,
        )
        assert resp.status_code in (200, 201), (
            f"Réservation échouée ({resp.status_code}): {resp.content[:300]}"
        )

        # Stripe doit avoir été appelé / Stripe should have been called
        assert mock_stripe.mock_create.called, (
            "Stripe Session.create devrait être appelé pour réservation payante"
        )

        with schema_context("lespass"):
            paiement = Paiement_stripe.objects.filter(
                checkout_session_id_stripe="cs_test_mock_session",
            ).order_by("-datetime").first()
            assert paiement is not None, "Paiement_stripe non trouvé"

    def test_anonymous_booking_with_options(self, api_client, auth_headers, mock_stripe):
        """PW 09 test 3 : reservation gratuite avec options creees sur l'evenement.
        / PW 09 test 3: free booking with options created on the event.

        Les options sont des OptionGenerale (UUID). On cree l'evenement avec options,
        puis on recupere les UUID pour les passer a la reservation.
        """
        from django_tenants.utils import schema_context
        from BaseBillet.models import Reservation, Event

        rid = _random_id()
        email = f"test+optbook{rid}@mock.test"

        event_data, _, price_uuid = _create_event_and_product(
            api_client, auth_headers,
            event_name=f"Options Event {rid}",
            product_name=f"Billets Options {rid}",
            price_name="Gratuit",
            price_amount="0.00",
            category="Free booking",
            options_radio=["Option A", "Option B"],
            options_checkbox=["Extra 1", "Extra 2"],
        )

        # Recuperer les UUID des options creees / Get created option UUIDs
        with schema_context("lespass"):
            event = Event.objects.get(uuid=event_data["identifier"])
            radio_opts = list(event.options_radio.values_list("uuid", flat=True))
            checkbox_opts = list(event.options_checkbox.values_list("uuid", flat=True))
            option_uuids = []
            if radio_opts:
                option_uuids.append(str(radio_opts[0]))
            if checkbox_opts:
                option_uuids.append(str(checkbox_opts[0]))

        if not option_uuids:
            pytest.skip("Aucune option creee sur l'evenement")

        resp = _create_reservation(
            api_client, auth_headers,
            event_uuid=event_data["identifier"],
            price_uuid=price_uuid,
            email=email,
            options=option_uuids,
        )
        assert resp.status_code in (200, 201), (
            f"Réservation échouée ({resp.status_code}): {resp.content[:300]}"
        )

        with schema_context("lespass"):
            reservation = Reservation.objects.filter(
                user_commande__email=email,
            ).order_by("-datetime").first()
            assert reservation is not None

    def test_anonymous_booking_dynamic_form(self, api_client, auth_headers, mock_stripe):
        """PW 10 : reservation payante + champs dynamiques.
        / PW 10: paid booking + dynamic form fields.
        """
        from django_tenants.utils import schema_context
        from BaseBillet.models import Reservation

        rid = _random_id()
        email = f"test+formbook{rid}@mock.test"

        event_data, _, price_uuid = _create_event_and_product(
            api_client, auth_headers,
            event_name=f"Form Event {rid}",
            product_name=f"Billets Form {rid}",
            price_name="Tarif Soutien",
            price_amount="10.00",
            form_fields=[
                {"label": "Nom", "fieldType": "shortText", "required": True, "order": 1},
                {"label": "Telephone", "fieldType": "shortText", "required": True, "order": 2},
            ],
        )

        resp = _create_reservation(
            api_client, auth_headers,
            event_uuid=event_data["identifier"],
            price_uuid=price_uuid,
            email=email,
            custom_form={"nom": "Adams", "telephone": "0612345678"},
        )
        assert resp.status_code in (200, 201), (
            f"Réservation échouée ({resp.status_code}): {resp.content[:300]}"
        )

        assert mock_stripe.mock_create.called

        with schema_context("lespass"):
            reservation = Reservation.objects.filter(
                user_commande__email=email,
            ).order_by("-datetime").first()
            assert reservation is not None
