"""List initiatives via API v2 Crowds."""
import pytest


@pytest.mark.integration
def test_crowd_initiative_list(request, api_client, auth_headers):
    resp = api_client.get('/api/v2/initiatives/', **auth_headers)
    assert resp.status_code == 200, f"List failed ({resp.status_code}): {resp.content.decode()[:500]}"

    data = resp.json()
    assert "results" in data
    assert isinstance(data["results"], list)

    cached_uuid = request.config.cache.get("api_v2_crowd_initiative_uuid", None)
    if cached_uuid:
        uuids = [item.get("identifier") for item in data["results"]]
        assert cached_uuid in uuids
