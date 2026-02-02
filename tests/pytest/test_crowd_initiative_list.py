"""List initiatives via API v2 Crowds."""
import os

import pytest
import requests


@pytest.mark.integration
def test_crowd_initiative_list(request):
    base_url = os.getenv("API_BASE_URL", "https://lespass.tibillet.localhost").rstrip("/")
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise Exception("API key not set")

    headers = {"Authorization": f"Api-Key {api_key}"}
    list_url = f"{base_url}/api/v2/initiatives/"
    resp = requests.get(list_url, headers=headers, timeout=10, verify=False)
    assert resp.status_code == 200, f"List failed ({resp.status_code}): {resp.text[:500]}"

    data = resp.json()
    assert "results" in data
    assert isinstance(data["results"], list)

    cached_uuid = request.config.cache.get("api_v2_crowd_initiative_uuid", None)
    if cached_uuid:
        uuids = [item.get("identifier") for item in data["results"]]
        assert cached_uuid in uuids
