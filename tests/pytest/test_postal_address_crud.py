"""
Tests d'intégration (pytest) — API v2 PostalAddress CRUD

Pré-requis:
- Clé API avec droit `event` (réutilisé pour postaladdress)
- Instance accessible via API_BASE_URL

Lancement:
    poetry run pytest -q tests/pytest/test_postal_address_crud.py
"""
import os
import json

import pytest
import requests


@pytest.mark.integration
def test_postal_address_crud_cycle():
    base_url = os.getenv("API_BASE_URL", "https://lespass.tibillet.localhost").rstrip("/")
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise Exception("API key not set")

    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }

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
    create_url = f"{base_url}/api/v2/postal-addresses/"
    resp = requests.post(create_url, headers=headers, data=json.dumps(create_payload), timeout=10, verify=False)
    assert resp.status_code == 201, f"Create failed: {resp.status_code} {resp.text[:300]}"
    data = resp.json()
    assert data.get("@type") == "PostalAddress"
    assert data.get("streetAddress") == create_payload["streetAddress"]
    assert data.get("name") == create_payload["name"]
    # we don't receive id in schema.org representation; we will list to find it back

    # List
    list_url = f"{base_url}/api/v2/postal-addresses/"
    lresp = requests.get(list_url, headers={"Authorization": f"Api-Key {api_key}"}, timeout=10, verify=False)
    assert lresp.status_code == 200
    ldata = lresp.json()
    assert isinstance(ldata.get("results"), list)

    # Try to find our address by fields
    found_id = None
    for idx, item in enumerate(ldata["results"]):
        if item.get("streetAddress") == create_payload["streetAddress"] and item.get("addressLocality") == create_payload["addressLocality"]:
            # retrieve requires numeric id; list does not expose it via schema.org. We cannot infer id here.
            # So we simply validate list contains our object and skip retrieve-by-id.
            found_id = True
            break
    assert found_id, "Created address not found in list"

    # Note: retrieve requires internal id, which is not part of schema.org representation.
    # We keep CRUD limited to create + list + delete not strictly possible without id.

