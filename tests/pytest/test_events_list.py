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
from __future__ import annotations

import json
import os
from typing import List

import pytest
import requests
from requests import Response


EXPECTED_EVENT_NAMES = {
    # Noms d'évènements créés dans demo_data.py (valeurs stables)
    "Scène ouverte : Entrée libre",
    "Disco Caravane : Gratuit avec réservation",
    "Concert caritatif : Entrée a prix libre",
    "What the Funk ? Spectacle payant",
    "Soirée découverte avec formulaire",
    "Chantier participatif : besoin de volontaires",
    # Sous-évènements (actions)
    "Jardinage et plantation",
    "Peinture et décoration",
    "Bricolage et réparations",
}


@pytest.mark.integration
def test_events_list_contains_demo_events():
    base_url = os.getenv("API_BASE_URL", "http://lespass.tibillet.localhost").rstrip("/")
    api_key = os.getenv("API_KEY", "EX2r3lfP.WGdO7Ni6fln2KZGPoDrZmr0VUiLHOGS5")

    if not api_key:
        pytest.skip("API_KEY manquant dans l'environnement — test ignoré.")

    url = f"{base_url}/api/v2/events/"
    headers = {"Authorization": f"Api-Key {api_key}"}

    try:
        resp: Response = requests.get(url, headers=headers, timeout=10, verify=False)
    except Exception as e:
        pytest.skip(f"Impossible de joindre {url} ({e}) — test ignoré.")

    # Doit retourner 200 et un tableau JSON de schema.org/Event
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:500]}"

    try:
        data = resp.json()
    except json.JSONDecodeError:
        pytest.fail(f"Réponse non JSON: {resp.text[:500]}")

    assert isinstance(data, list), "La liste des évènements doit être un tableau JSON"

    names = {item.get("name") for item in data if isinstance(item, dict)}

    # On vérifie que tous les évènements de démo attendus sont bien présents
    missing = sorted(list(EXPECTED_EVENT_NAMES - names))
    assert not missing, f"Évènements manquants dans la liste: {missing}\nNoms retournés: {sorted(list(names))}"
