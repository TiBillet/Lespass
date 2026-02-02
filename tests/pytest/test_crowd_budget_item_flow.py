"""Create and list budget items via API v2 Crowds."""
import os
import json
import uuid

import pytest
import requests


def _ensure_initiative(base_url, api_key, request):
    cached_uuid = request.config.cache.get("api_v2_crowd_initiative_uuid", None)
    if cached_uuid:
        return cached_uuid
    payload = {
        "@context": "https://schema.org",
        "@type": "Project",
        "name": f"API v2 — Initiative {uuid.uuid4()}",
        "description": "Projet de test via API v2",
        "disambiguatingDescription": "Test court",
        "currency": "EUR",
    }
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }
    create_url = f"{base_url}/api/v2/initiatives/"
    resp = requests.post(create_url, headers=headers, data=json.dumps(payload), timeout=10, verify=False)
    assert resp.status_code == 201, f"Create failed ({resp.status_code}): {resp.text[:500]}"
    data = resp.json()
    identifier = data.get("identifier")
    assert identifier
    request.config.cache.set("api_v2_crowd_initiative_uuid", identifier)
    return identifier


@pytest.mark.integration
def test_crowd_budget_item_create_and_list(request):
    base_url = os.getenv("API_BASE_URL", "https://lespass.tibillet.localhost").rstrip("/")
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise Exception("API key not set")

    initiative_uuid = _ensure_initiative(base_url, api_key, request)

    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }
    create_url = f"{base_url}/api/v2/initiatives/{initiative_uuid}/budget-items/"
    payload = {
        "description": "Budget test API",
        "amount": "120.00",
        "actionStatus": "requested",
    }
    resp = requests.post(create_url, headers=headers, data=json.dumps(payload), timeout=10, verify=False)
    assert resp.status_code == 201, f"Create budget item failed ({resp.status_code}): {resp.text[:500]}"
    data = resp.json()
    assert data.get("name") == payload["description"]

    list_url = f"{base_url}/api/v2/initiatives/{initiative_uuid}/budget-items/"
    list_resp = requests.get(list_url, headers={"Authorization": f"Api-Key {api_key}"}, timeout=10, verify=False)
    assert list_resp.status_code == 200, f"List budget items failed ({list_resp.status_code}): {list_resp.text[:500]}"
    list_data = list_resp.json()
    assert "results" in list_data
    assert isinstance(list_data["results"], list)
