"""
Integration test (pytest) - API v2 Reservation create + retrieve.

Run:
  poetry run pytest -q tests/pytest/test_reservation_create.py
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.integration
def test_reservation_create_and_retrieve(api_client, auth_headers):
    # Create Event (unique name + startDate)
    start = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    event_payload = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": f"API v2 Reservation Event {uuid.uuid4()}",
        "startDate": start,
    }
    event_resp = api_client.post(
        '/api/v2/events/',
        data=json.dumps(event_payload),
        content_type='application/json',
        **auth_headers,
    )
    assert event_resp.status_code == 201, f"Event create failed: {event_resp.status_code} {event_resp.content.decode()[:300]}"
    event_data = event_resp.json()
    event_uuid = event_data.get("identifier")
    assert event_uuid, f"Event identifier missing: {event_data}"

    # Create Product + Offer (free) linked to Event
    product_payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": f"API v2 Reservation Product {uuid.uuid4()}",
        "description": "Product for reservation test",
        "category": "Free booking",
        "isRelatedTo": {"@type": "Event", "identifier": event_uuid},
        "offers": [
            {
                "@type": "Offer",
                "name": "Free rate",
                "price": "0.00",
                "priceCurrency": "EUR",
            }
        ],
    }
    product_resp = api_client.post(
        '/api/v2/products/',
        data=json.dumps(product_payload),
        content_type='application/json',
        **auth_headers,
    )
    assert product_resp.status_code == 201, f"Product create failed: {product_resp.status_code} {product_resp.content.decode()[:300]}"
    product_data = product_resp.json()
    offers = product_data.get("offers") or []
    price_uuid = offers[0].get("identifier") if offers else None
    assert price_uuid, f"Offer identifier missing: {product_data}"

    # Create Reservation
    reservation_payload = {
        "@context": "https://schema.org",
        "@type": "Reservation",
        "reservationFor": {"@type": "Event", "identifier": event_uuid},
        "underName": {"@type": "Person", "email": f"resa-{uuid.uuid4()}@example.org"},
        "reservedTicket": [
            {
                "@type": "Ticket",
                "identifier": price_uuid,
                "ticketQuantity": 1,
            }
        ],
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "confirmed", "value": True}
        ],
    }
    res_resp = api_client.post(
        '/api/v2/reservations/',
        data=json.dumps(reservation_payload),
        content_type='application/json',
        **auth_headers,
    )
    assert res_resp.status_code == 201, f"Reservation create failed: {res_resp.status_code} {res_resp.content.decode()[:300]}"
    res_data = res_resp.json()
    reservation_uuid = res_data.get("identifier")
    assert reservation_uuid, f"Reservation identifier missing: {res_data}"
    assert res_data.get("reservationFor", {}).get("identifier") == event_uuid
    assert res_data.get("reservationStatus", "").endswith("ReservationConfirmed")

    # Retrieve Reservation
    det_resp = api_client.get(f'/api/v2/reservations/{reservation_uuid}/', **auth_headers)
    assert det_resp.status_code == 200, f"Reservation retrieve failed: {det_resp.status_code} {det_resp.content.decode()[:300]}"
    det_data = det_resp.json()
    assert det_data.get("identifier") == reservation_uuid
    assert det_data.get("reservationFor", {}).get("identifier") == event_uuid
