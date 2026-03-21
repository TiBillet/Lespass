"""
Test d'integration (pytest) — API v2 Crowds: Initiative create + retrieve.

Prerequis:
- Cle API avec droit "crowd".
"""
import json
import uuid

import pytest


@pytest.mark.integration
def test_crowd_initiative_create_and_retrieve(request, api_client, auth_headers):
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

    resp = api_client.post(
        '/api/v2/initiatives/',
        data=json.dumps(payload),
        content_type='application/json',
        **auth_headers,
    )
    assert resp.status_code == 201, f"Create failed ({resp.status_code}): {resp.content.decode()[:500]}"

    data = resp.json()
    identifier = data.get("identifier")
    assert identifier, f"identifier manquant dans la reponse: {data}"
    assert data.get("name") == payload["name"]

    cache = request.config.cache
    cache.set("api_v2_crowd_initiative_uuid", identifier)
    cache.set("api_v2_crowd_initiative_name", payload["name"])

    get_resp = api_client.get(f'/api/v2/initiatives/{identifier}/', **auth_headers)
    assert get_resp.status_code == 200, f"Retrieve failed ({get_resp.status_code}): {get_resp.content.decode()[:500]}"
    detail = get_resp.json()
    assert detail.get("identifier") == identifier
    assert detail.get("name") == payload["name"]
