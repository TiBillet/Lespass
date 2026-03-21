"""
Test d'intégration (pytest) — API v2 Events list

Lancez avec Poetry:
  poetry run pytest -q tests/pytest/test_events_list.py
"""
import json

import pytest


@pytest.mark.integration
def test_events_list_contains_created_event(request, api_client, auth_headers):
    resp = api_client.get('/api/v2/events/', **auth_headers)
    # Doit retourner 200 et un tableau JSON de schema.org/Event
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.content.decode()[:500]}"

    try:
        data = resp.json()
    except json.JSONDecodeError:
        pytest.fail(f"Réponse non JSON: {resp.content.decode()[:500]}")

    assert isinstance(data['results'], list), "La liste des évènements doit être un tableau JSON"

    names = {item.get("name") for item in data['results'] if isinstance(item, dict)}

    # On vérifie uniquement la présence de l'évènement créé juste avant (via pytest cache)
    created_name = request.config.cache.get("api_v2_event_name", None)
    assert created_name, "Nom de l'évènement créé introuvable dans le cache de test (create doit s'exécuter avant)."
    assert created_name in names, f"L'évènement créé ('{created_name}') n'apparaît pas dans la liste. Noms: {sorted(list(names))}"
