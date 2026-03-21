"""
Tests d'intégration (pytest) — API v2 PostalAddress CRUD

Lancement:
    poetry run pytest -q tests/pytest/test_postal_address_crud.py
"""
import json

import pytest


@pytest.mark.integration
def test_postal_address_crud_cycle(api_client, auth_headers):
    # Create
    create_payload = {
        "@type": "PostalAddress",
        "name": "Test Address",
        "streetAddress": "123 Rue de Test",
        "addressLocality": "Testville",
        "addressRegion": "TV",
        "postalCode": "99999",
        "addressCountry": "FR",
        "geo": {"latitude": 43.7, "longitude": 7.25},
    }
    resp = api_client.post(
        '/api/v2/postal-addresses/',
        data=json.dumps(create_payload),
        content_type='application/json',
        **auth_headers,
    )
    assert resp.status_code == 201, f"Create failed: {resp.status_code} {resp.content.decode()[:300]}"
    data = resp.json()
    assert data.get("@type") == "PostalAddress"
    assert data.get("streetAddress") == create_payload["streetAddress"]
    assert data.get("name") == create_payload["name"]

    # List
    lresp = api_client.get('/api/v2/postal-addresses/', **auth_headers)
    assert lresp.status_code == 200
    ldata = lresp.json()
    assert isinstance(ldata.get("results"), list)

    # Try to find our address by fields
    found_id = None
    for idx, item in enumerate(ldata["results"]):
        if item.get("streetAddress") == create_payload["streetAddress"] and item.get("addressLocality") == create_payload["addressLocality"]:
            found_id = True
            break
    assert found_id, "Created address not found in list"
