"""
Test d'intégration (pytest) — API v2 Events list

Ce test est volontairement en dehors du framework de tests Django pour éviter
la gestion de base de données/tenants. Il interroge l'API HTTP en boîte noire.

Prerequis côté environnement d'exécution du test:
- Un tenant de démo peuplé avec la commande Administration.demo_data
- Une clé API (ExternalApiKey) avec le droit « event »
- L'instance Django en cours d'exécution et accessible via un host du tenant

Variables d'environnement utilisées:
- API_BASE_URL (ex: https://letierslustre.tibillet.localhost)
  -> si non défini, défaut sur http://lespass.tibillet.localhost
- API_KEY (clé pour l'en-tête Authorization: Api-Key <key>)

Pour lancer: pytest -q tests/test_events_list.py
"""
import json
import os
from typing import List

import pytest
import requests
from requests import Response


@pytest.mark.integration
def test_events_list_contains_created_event(request):
    base_url = os.getenv("API_BASE_URL", "https://lespass.tibillet.localhost").rstrip("/")
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise Exception("API key not set")


    url = f"{base_url}/api/v2/events/"
    headers = {"Authorization": f"Api-Key {api_key}"}

    resp: Response = requests.get(url, headers=headers, timeout=10, verify=False)
    # Doit retourner 200 et un tableau JSON de schema.org/Event
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:500]}"

    try:
        data = resp.json()
    except json.JSONDecodeError:
        pytest.fail(f"Réponse non JSON: {resp.text[:500]}")

    assert isinstance(data['results'], list), "La liste des évènements doit être un tableau JSON"

    names = {item.get("name") for item in data['results'] if isinstance(item, dict)}

    # On vérifie uniquement la présence de l'évènement créé juste avant (via pytest cache)
    created_name = request.config.cache.get("api_v2_event_name", None)
    assert created_name, "Nom de l'évènement créé introuvable dans le cache de test (create doit s'exécuter avant)."
    assert created_name in names, f"L'évènement créé ('{created_name}') n'apparaît pas dans la liste. Noms: {sorted(list(names))}"
