"""
Test d'intégration (pytest) — API v2 Event create

Ce test poste un payload schema.org/Event minimal pour créer un évènement,
puis le récupère par son UUID via l'endpoint retrieve.

Prérequis:
- Données de démo chargées (facultatif pour ce test)
- Clé API (ExternalApiKey) avec droit "event"

Lancez avec Poetry:
  poetry run pytest -q tests/pytest/test_event_create.py
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.integration
def test_event_create_and_retrieve(request, api_client, auth_headers):
    # startDate dans ~2 jours pour éviter conflits de validation éventuels
    start = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    payload = {
        "@context": "https://schema.org",
        "@type": "MusicEvent",
        "name": f"API v2 — Test create {uuid.uuid4()}",
        "startDate": start,
        "keywords": ["API-Test", "Integration"],
    }

    # Create
    resp = api_client.post(
        '/api/v2/events/',
        data=json.dumps(payload),
        content_type='application/json',
        **auth_headers,
    )
    assert resp.status_code == 201, f"Create failed ({resp.status_code}): {resp.content.decode()[:500]}"

    data = resp.json()
    assert data.get("@type") == "MusicEvent"
    identifier = data.get("identifier")
    assert identifier, f"identifier manquant dans la réponse: {data}"
    assert data.get("name") == payload["name"]
    assert "API-Test" in (data.get("keywords") or [])

    # Persist for subsequent tests (ordered via conftest)
    cache = request.config.cache
    cache.set("api_v2_event_uuid", identifier)
    cache.set("api_v2_event_name", payload["name"])
    # Append to list of created events for cleanup
    existing = cache.get("api_v2_event_uuids_all", []) or []
    if identifier not in existing:
        existing.append(identifier)
    cache.set("api_v2_event_uuids_all", existing)

    # Retrieve (sanity check)
    get_resp = api_client.get(f'/api/v2/events/{identifier}/', **auth_headers)
    assert get_resp.status_code == 200, f"Retrieve failed ({get_resp.status_code}): {get_resp.content.decode()[:500]}"
    detail = get_resp.json()
    assert detail.get("identifier") == identifier
    assert detail.get("name") == payload["name"]
