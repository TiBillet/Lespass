"""
Test d'intégration (pytest) — API v2 Event retrieve par UUID

Lancement:
    poetry run pytest -q tests/pytest/test_event_retrieve.py
"""
import json

import pytest


@pytest.mark.integration
def test_event_retrieve_by_uuid_from_list(request, api_client, auth_headers):
    # Essayez d'abord de récupérer l'UUID depuis le cache de test
    event_uuid = request.config.cache.get("api_v2_event_uuid", None)

    if not event_uuid:
        # Fallback: lister et prendre le premier
        list_resp = api_client.get('/api/v2/events/', **auth_headers)
        assert list_resp.status_code == 200, f"HTTP {list_resp.status_code}: {list_resp.content.decode()[:500]}"

        try:
            list_data = list_resp.json()
        except json.JSONDecodeError:
            pytest.fail(f"Réponse non JSON pour la liste: {list_resp.content.decode()[:500]}")

        results = list_data.get("results")
        assert isinstance(results, list) and len(results) > 0, "Aucun évènement retourné par la liste"

        # La sérialisation renvoie 'identifier' (uuid sous forme de str) dans le JSON-LD
        first = results[0]
        event_uuid = first.get("identifier")
        assert event_uuid, "Aucun identifiant (identifier) trouvé dans la liste"

    # Récupération détaillée
    detail_resp = api_client.get(f'/api/v2/events/{event_uuid}/', **auth_headers)
    assert detail_resp.status_code == 200, f"HTTP {detail_resp.status_code}: {detail_resp.content.decode()[:500]}"

    try:
        detail_data = detail_resp.json()
    except json.JSONDecodeError:
        pytest.fail(f"Réponse non JSON pour le détail: {detail_resp.content.decode()[:500]}")

    # Vérifications minimales du schéma Event (schema.org)
    assert detail_data.get("@type") == "MusicEvent"
    assert detail_data.get("identifier") == event_uuid
    assert "name" in detail_data and isinstance(detail_data["name"], str) and detail_data["name"].strip()
