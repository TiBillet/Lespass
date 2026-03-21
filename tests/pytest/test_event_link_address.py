"""
Test d'intégration — Lier une adresse postale à un évènement via l'endpoint dédié

Scénario:
- Récupère un UUID d'event via la liste
- Appelle POST /api/v2/events/{uuid}/link-address/ avec un payload schema.org/PostalAddress
- Vérifie que le retrieve renvoie location.address correspondant

Lancement:
  poetry run pytest -q tests/pytest/test_event_link_address.py
"""
import json

import pytest


@pytest.mark.integration
def test_link_address_to_event_then_retrieve(api_client, auth_headers):
    # 1) prendre n'importe quel event
    lst = api_client.get('/api/v2/events/', **auth_headers)
    assert lst.status_code == 200, lst.content.decode()[:300]
    results = lst.json().get("results")
    assert results and isinstance(results, list)
    event_uuid = results[0].get("identifier")
    assert event_uuid

    # 2) lier une nouvelle adresse
    address_payload = {
        "@type": "PostalAddress",
        "name": "Test 42 Address",
        "streetAddress": "42 Avenue des Tests",
        "addressLocality": "DevCity",
        "addressRegion": "DC",
        "postalCode": "42424",
        "addressCountry": "FR",
        "geo": {"latitude": 48.8566, "longitude": 2.3522},
    }
    link_resp = api_client.post(
        f'/api/v2/events/{event_uuid}/link-address/',
        data=json.dumps(address_payload),
        content_type='application/json',
        **auth_headers,
    )
    assert link_resp.status_code in (200, 201), f"Link failed: {link_resp.status_code} {link_resp.content.decode()[:300]}"

    # 3) retrieve et vérifie la location
    det = api_client.get(f'/api/v2/events/{event_uuid}/', **auth_headers)
    assert det.status_code == 200
    data = det.json()
    place = data.get("location") or {}
    addr = place.get("address") or {}
    assert addr.get("@type") == "PostalAddress"
    assert addr.get("name") == address_payload["name"]
    assert addr.get("streetAddress") == address_payload["streetAddress"]
    assert addr.get("addressLocality") == address_payload["addressLocality"]
