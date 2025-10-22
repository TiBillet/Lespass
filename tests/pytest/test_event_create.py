"""
Test d'intégration (pytest) — API v2 Event create

Ce test poste un payload schema.org/Event minimal pour créer un évènement,
puis le récupère par son UUID via l'endpoint retrieve.

Prérequis:
- Données de démo chargées (facultatif pour ce test)
- Clé API (ExternalApiKey) avec droit "event"
- Service accessible via API_BASE_URL (ex: https://lespass.tibillet.localhost)

Lancez avec Poetry:
  poetry run pytest -q tests/pytest/test_event_create.py
"""
import os
import json
from datetime import datetime, timedelta, timezone

import pytest
import requests


@pytest.mark.integration
def test_event_create_and_retrieve(request):
    base_url = os.getenv("API_BASE_URL", "https://lespass.tibillet.localhost").rstrip("/")
    api_key = os.getenv("API_KEY", "EX2r3lfP.WGdO7Ni6fln2KZGPoDrZmr0VUiLHOGS5")
    if not api_key:
        pytest.skip("API_KEY manquant dans l'environnement — test ignoré.")

    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }

    # startDate dans ~2 jours pour éviter conflits de validation éventuels
    start = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    payload = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": "API v2 — Test create",
        "startDate": start,
        "@type": "MusicEvent"
    }

    # Create
    create_url = f"{base_url}/api/v2/events/"
    resp = requests.post(create_url, headers=headers, data=json.dumps(payload), timeout=10, verify=False)
    assert resp.status_code == 201, f"Create failed ({resp.status_code}): {resp.text[:500]}"

    data = resp.json()
    assert data.get("@type") == "Event"
    identifier = data.get("identifier")
    assert identifier, f"identifier manquant dans la réponse: {data}"
    assert data.get("name") == payload["name"]

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
    detail_url = f"{base_url}/api/v2/events/{identifier}/"
    get_resp = requests.get(detail_url, headers={"Authorization": f"Api-Key {api_key}"}, timeout=10, verify=False)
    assert get_resp.status_code == 200, f"Retrieve failed ({get_resp.status_code}): {get_resp.text[:500]}"
    detail = get_resp.json()
    assert detail.get("identifier") == identifier
    assert detail.get("name") == payload["name"]
