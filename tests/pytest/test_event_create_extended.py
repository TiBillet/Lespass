"""
Test d'intégration (pytest) — API v2 Event create avec champs schema.org étendus

Pré‑requis:
- Clé API (ExternalApiKey) avec droit `event`
- Instance accessible via API_BASE_URL

Lancement:
    poetry run pytest -q tests/pytest/test_event_create_extended.py
"""
import os
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests


@pytest.mark.integration
def test_event_create_with_schema_org_fields(request):
    base_url = os.getenv("API_BASE_URL", "https://lespass.tibillet.localhost").rstrip("/")
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise Exception("API key not set")

    url = f"{base_url}/api/v2/events/"
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }

    start = datetime.now(timezone.utc) + timedelta(days=30)
    payload = {
        "@context": "https://schema.org",
        "name": f"API v2 — Extended Create {uuid.uuid4()}",
        "startDate": start.isoformat(),
        "@type": "MusicEvent",
        "maximumAttendeeCapacity": 123,
        "disambiguatingDescription": "Short blurb",
        "description": "Longer event description for API test.",
        "eventStatus": "https://schema.org/EventScheduled",
        "audience": {"@type": "Audience", "audienceType": "private"},
        "keywords": ["API-Test", "Integration"],
        "sameAs": "https://example.org/external-event",
        "offers": {
            "eligibleQuantity": {"maxValue": 2},
            "returnPolicy": {"merchantReturnDays": 5}
        },
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "customConfirmationMessage", "value": "Merci pour votre réservation !"}
        ]
    }

    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10, verify=False)
    assert resp.status_code == 201, f"HTTP {resp.status_code}: {resp.text[:500]}"
    data = resp.json()
    # Track for cleanup across runs
    ev_id_for_cleanup = data.get("identifier")
    if ev_id_for_cleanup:
        existing = request.config.cache.get("api_v2_event_uuids_all", []) or []
        if ev_id_for_cleanup not in existing:
            existing.append(ev_id_for_cleanup)
        request.config.cache.set("api_v2_event_uuids_all", existing)

    # Vérifications minimales sur la réponse de création
    assert data.get("@type") == "MusicEvent"
    ev_id = data.get("identifier")
    assert ev_id, "identifier manquant dans la réponse de création"

    # Champ sémantiques
    assert data.get("maximumAttendeeCapacity") == 123
    assert data.get("disambiguatingDescription") == "Short blurb"
    assert data.get("eventStatus", "").endswith("EventScheduled")
    assert data.get("audience", {}).get("audienceType") == "private"
    assert "API-Test" in (data.get("keywords") or [])
    # Offres
    offers = data.get("offers") or {}
    elig = offers.get("eligibleQuantity") or {}
    assert elig.get("maxValue") == 2
    ret = offers.get("returnPolicy") or {}
    assert ret.get("merchantReturnDays") == 5
    # SameAs
    assert data.get("sameAs") == "https://example.org/external-event"

    # Vérifier la présence du message personnalisé dans additionalProperty
    addp = data.get("additionalProperty") or []
    has_msg = any(p.get("name") == "customConfirmationMessage" for p in addp)
    assert has_msg, f"customConfirmationMessage absent: {addp}"

    # Lecture 
    detail = requests.get(f"{base_url}/api/v2/events/{ev_id}/", headers=headers, timeout=10, verify=False)
    assert detail.status_code == 200, f"HTTP {detail.status_code}: {detail.text[:500]}"
    det = detail.json()
    assert det.get("identifier") == ev_id
    assert det.get("maximumAttendeeCapacity") == 123
    assert det.get("audience", {}).get("audienceType") == "private"

    # Create an ACTION child event requiring a parent
    action_payload = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": "API v2 — Action Child",
        "startDate": (start + timedelta(days=1)).isoformat(),
        "@type": "Event",
        "superEvent": ev_id
    }
    resp2 = requests.post(url, headers=headers, data=json.dumps(action_payload), timeout=10, verify=False)
    assert resp2.status_code == 201, f"Action create failed: {resp2.status_code} {resp2.text[:300]}"
    data2 = resp2.json()
    child_id = data2.get("identifier")
    assert child_id, "identifier manquant pour l'évènement ACTION"
    # track for cleanup
    existing2 = request.config.cache.get("api_v2_event_uuids_all", []) or []
    if child_id not in existing2:
        existing2.append(child_id)
    request.config.cache.set("api_v2_event_uuids_all", existing2)
