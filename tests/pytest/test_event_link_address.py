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
import os

import pytest
import requests


@pytest.mark.integration
def test_link_address_to_event_then_retrieve():
    base_url = os.getenv("API_BASE_URL", "https://lespass.tibillet.localhost").rstrip("/")
    api_key = os.getenv("API_KEY", "EX2r3lfP.WGdO7Ni6fln2KZGPoDrZmr0VUiLHOGS5")
    if not api_key:
        pytest.skip("API_KEY manquant — test ignoré.")

    headers = {"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json"}

    # 1) prendre n'importe quel event
    lst = requests.get(f"{base_url}/api/v2/events/", headers={"Authorization": f"Api-Key {api_key}"}, timeout=10, verify=False)
    assert lst.status_code == 200, lst.text[:300]
    results = lst.json().get("results")
    assert results and isinstance(results, list)
    event_uuid = results[0].get("identifier")
    assert event_uuid

    # 2) lier une nouvelle adresse
    address_payload = {
        "@type": "PostalAddress",
        "streetAddress": "42 Avenue des Tests",
        "addressLocality": "DevCity",
        "addressRegion": "DC",
        "postalCode": "42424",
        "addressCountry": "FR",
        "geo": {"latitude": 48.8566, "longitude": 2.3522},
    }
    link_url = f"{base_url}/api/v2/events/{event_uuid}/link-address/"
    link_resp = requests.post(link_url, headers=headers, data=json.dumps(address_payload), timeout=10, verify=False)
    assert link_resp.status_code in (200, 201), f"Link failed: {link_resp.status_code} {link_resp.text[:300]}"

    # 3) retrieve et vérifie la location
    det = requests.get(f"{base_url}/api/v2/events/{event_uuid}/", headers={"Authorization": f"Api-Key {api_key}"}, timeout=10, verify=False)
    assert det.status_code == 200
    data = det.json()
    place = data.get("location") or {}
    addr = place.get("address") or {}
    assert addr.get("@type") == "PostalAddress"
    assert addr.get("streetAddress") == address_payload["streetAddress"]
    assert addr.get("addressLocality") == address_payload["addressLocality"]
