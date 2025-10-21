"""
Test d'intégration (pytest) — API v2 Event delete

Pré‑requis:
- API_KEY avec droit `event`
- L'évènement a été créé par le test de création précédent (UUID en cache)

Lancement:
    poetry run pytest -q tests/pytest/test_event_delete.py
"""
import os

import pytest
import requests


@pytest.mark.integration
def test_event_delete_then_404_on_retrieve(request):
    base_url = os.getenv("API_BASE_URL", "https://lespass.tibillet.localhost").rstrip("/")
    api_key = os.getenv("API_KEY", "EX2r3lfP.WGdO7Ni6fln2KZGPoDrZmr0VUiLHOGS5")
    if not api_key:
        pytest.skip("API_KEY manquant — test ignoré.")

    headers = {"Authorization": f"Api-Key {api_key}"}

    # Récupérer tous les UUID créés auparavant (liste) et fallback sur l'unitaire
    cache = request.config.cache
    uuids = cache.get("api_v2_event_uuids_all", []) or []
    single_uuid = cache.get("api_v2_event_uuid", None)
    if single_uuid and single_uuid not in uuids:
        uuids.append(single_uuid)
    assert uuids, "Aucun UUID d'évènement trouvé dans le cache (les tests de création doivent s'exécuter avant)."

    # Supprimer chaque évènement créé par l'API de test
    for uid in set(uuids):
        del_url = f"{base_url}/api/v2/events/{uid}/"
        del_resp = requests.delete(del_url, headers=headers, timeout=10, verify=False)
        assert del_resp.status_code == 204, f"Delete failed for {uid}: {del_resp.status_code} {del_resp.text[:300]}"
        # GET doit renvoyer 404 après suppression
        det_resp = requests.get(del_url, headers=headers, timeout=10, verify=False)
        assert det_resp.status_code == 404, (
            f"Après suppression de {uid}, le GET devrait renvoyer 404 (reçu {det_resp.status_code})."
        )

    # Nettoyage du cache de tests
    cache.set("api_v2_event_uuids_all", [])
    cache.set("api_v2_event_uuid", None)
    cache.set("api_v2_event_name", None)
