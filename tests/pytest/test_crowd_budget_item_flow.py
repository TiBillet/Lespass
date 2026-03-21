"""Create and list budget items via API v2 Crowds."""
import json
import uuid

import pytest


def _ensure_initiative(api_client, auth_headers, request):
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
    resp = api_client.post(
        '/api/v2/initiatives/',
        data=json.dumps(payload),
        content_type='application/json',
        **auth_headers,
    )
    assert resp.status_code == 201, f"Create failed ({resp.status_code}): {resp.content.decode()[:500]}"
    data = resp.json()
    identifier = data.get("identifier")
    assert identifier
    request.config.cache.set("api_v2_crowd_initiative_uuid", identifier)
    return identifier


@pytest.mark.integration
def test_crowd_budget_item_create_and_list(request, api_client, auth_headers):
    initiative_uuid = _ensure_initiative(api_client, auth_headers, request)

    payload = {
        "description": "Budget test API",
        "amount": "120.00",
        "actionStatus": "requested",
    }
    resp = api_client.post(
        f'/api/v2/initiatives/{initiative_uuid}/budget-items/',
        data=json.dumps(payload),
        content_type='application/json',
        **auth_headers,
    )
    assert resp.status_code == 201, f"Create budget item failed ({resp.status_code}): {resp.content.decode()[:500]}"
    data = resp.json()
    assert data.get("name") == payload["description"]

    list_resp = api_client.get(f'/api/v2/initiatives/{initiative_uuid}/budget-items/', **auth_headers)
    assert list_resp.status_code == 200, f"List budget items failed ({list_resp.status_code}): {list_resp.content.decode()[:500]}"
    list_data = list_resp.json()
    assert "results" in list_data
    assert isinstance(list_data["results"], list)
