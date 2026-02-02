"""
Test d'integration (pytest) — API v2 Crowds: Initiative create + retrieve.

Prerequis:
- Cle API avec droit "crowd".
- API accessible via API_BASE_URL (ex: https://lespass.tibillet.localhost)
"""
import os
import json
import uuid

import pytest
import requests


@pytest.mark.integration
def test_crowd_initiative_create_and_retrieve(request):
    base_url = os.getenv("API_BASE_URL", "https://lespass.tibillet.localhost").rstrip("/")
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise Exception("API key not set")

    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "@context": "https://schema.org",
        "@type": "Project",
        "name": f"API v2 — Initiative {uuid.uuid4()}",
        "description": "Projet de test via API v2",
        "disambiguatingDescription": "Test court",
        "keywords": ["API-Test", "Crowds"],
        "currency": "EUR",
        "voteEnabled": True,
        "budgetContributif": True,
        "directDebit": False,
    }

    create_url = f"{base_url}/api/v2/initiatives/"
    resp = requests.post(create_url, headers=headers, data=json.dumps(payload), timeout=10, verify=False)
    assert resp.status_code == 201, f"Create failed ({resp.status_code}): {resp.text[:500]}"

    data = resp.json()
    identifier = data.get("identifier")
    assert identifier, f"identifier manquant dans la reponse: {data}"
    assert data.get("name") == payload["name"]

    cache = request.config.cache
    cache.set("api_v2_crowd_initiative_uuid", identifier)
    cache.set("api_v2_crowd_initiative_name", payload["name"])

    detail_url = f"{base_url}/api/v2/initiatives/{identifier}/"
    get_resp = requests.get(detail_url, headers={"Authorization": f"Api-Key {api_key}"}, timeout=10, verify=False)
    assert get_resp.status_code == 200, f"Retrieve failed ({get_resp.status_code}): {get_resp.text[:500]}"
    detail = get_resp.json()
    assert detail.get("identifier") == identifier
    assert detail.get("name") == payload["name"]
