"""
Test d'intégration (pytest) — API v2 Event delete

Lancement:
    poetry run pytest -q tests/pytest/test_event_delete.py
"""
import json
import uuid
from datetime import datetime, timezone, timedelta

import pytest


@pytest.mark.integration
def test_event_delete_then_404_on_retrieve(api_client, auth_headers):
    # startDate dans ~2 jours pour éviter conflits de validation éventuels
    start = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()

    payload = {
        "@context": "https://schema.org",
        "@type": "MusicEvent",
        "name": f"API v2 — Test create delete {uuid.uuid4()}",
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

    uid = resp.json().get('identifier')
    # Supprimer chaque évènement créé par l'API de test
    del_resp = api_client.delete(f'/api/v2/events/{uid}/', **auth_headers)
    assert del_resp.status_code == 204, f"Delete failed for {uid}: {del_resp.status_code} {del_resp.content.decode()[:300]}"
    # GET doit renvoyer 404 après suppression
    det_resp = api_client.get(f'/api/v2/events/{uid}/', **auth_headers)
    assert det_resp.status_code == 404, (
        f"Après suppression de {uid}, le GET devrait renvoyer 404 (reçu {det_resp.status_code})."
    )
