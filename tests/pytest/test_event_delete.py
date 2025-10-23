"""
Test d'intégration (pytest) — API v2 Event delete

Pré‑requis:
- API_KEY avec droit `event`
- L'évènement a été créé par le test de création précédent (UUID en cache)

Lancement:
    poetry run pytest -q tests/pytest/test_event_delete.py
"""
import json
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests


@pytest.mark.integration
def test_event_delete_then_404_on_retrieve(request):
    base_url = os.getenv("API_BASE_URL", "https://lespass.tibillet.localhost").rstrip("/")
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise Exception("API key not set")

    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }

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
    create_url = f"{base_url}/api/v2/events/"
    resp = requests.post(create_url, headers=headers, data=json.dumps(payload), timeout=10, verify=False)
    assert resp.status_code == 201, f"Create failed ({resp.status_code}): {resp.text[:500]}"

    uid = resp.json().get('identifier')
    # Supprimer chaque évènement créé par l'API de test
    del_url = f"{base_url}/api/v2/events/{uid}/"
    del_resp = requests.delete(del_url, headers=headers, timeout=10, verify=False)
    assert del_resp.status_code == 204, f"Delete failed for {uid}: {del_resp.status_code} {del_resp.text[:300]}"
    # GET doit renvoyer 404 après suppression
    det_resp = requests.get(del_url, headers=headers, timeout=10, verify=False)
    assert det_resp.status_code == 404, (
        f"Après suppression de {uid}, le GET devrait renvoyer 404 (reçu {det_resp.status_code})."
    )

