"""Read votes count and participations list via API v2 Crowds."""
import os
import uuid
import json

import pytest
import requests


def _ensure_initiative(base_url, api_key, request):
    cached_uuid = request.config.cache.get("api_v2_crowd_initiative_uuid", None)
    if cached_uuid:
        return cached_uuid
    payload = {
        "@context": "https://schema.org",
        "@type": "Project",
        "name": f"API v2 — Initiative {uuid.uuid4()}",
        "description": "Projet de test via API v2",
        "disambiguatingDescription": "Test court",
        "currency": "EUR",
    }
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }
    create_url = f"{base_url}/api/v2/initiatives/"
    resp = requests.post(create_url, headers=headers, data=json.dumps(payload), timeout=10, verify=False)
    assert resp.status_code == 201, f"Create failed ({resp.status_code}): {resp.text[:500]}"
    data = resp.json()
    identifier = data.get("identifier")
    assert identifier
    request.config.cache.set("api_v2_crowd_initiative_uuid", identifier)
    return identifier


@pytest.mark.integration
def test_crowd_votes_and_participations(request):
    base_url = os.getenv("API_BASE_URL", "https://lespass.tibillet.localhost").rstrip("/")
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise Exception("API key not set")

    initiative_uuid = _ensure_initiative(base_url, api_key, request)
    headers = {"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json"}

    votes_url = f"{base_url}/api/v2/initiatives/{initiative_uuid}/votes/"
    vote_post = requests.post(votes_url, headers=headers, timeout=10, verify=False)
    assert vote_post.status_code == 201, f"Vote post failed ({vote_post.status_code}): {vote_post.text[:500]}"
    vote_data = vote_post.json()
    assert isinstance(vote_data.get("count"), int)

    votes_resp = requests.get(votes_url, headers={"Authorization": f"Api-Key {api_key}"}, timeout=10, verify=False)
    assert votes_resp.status_code == 200, f"Votes failed ({votes_resp.status_code}): {votes_resp.text[:500]}"
    votes_data = votes_resp.json()
    assert isinstance(votes_data.get("count"), int)
    assert votes_data.get("count") >= 1

    parts_url = f"{base_url}/api/v2/initiatives/{initiative_uuid}/participations/"
    part_payload = {"description": "Participation API v2", "amount": "45.00"}
    part_post = requests.post(parts_url, headers=headers, data=json.dumps(part_payload), timeout=10, verify=False)
    assert part_post.status_code == 201, f"Participation post failed ({part_post.status_code}): {part_post.text[:500]}"
    part_data = part_post.json()
    assert part_data.get("description") == part_payload["description"]

    parts_resp = requests.get(parts_url, headers={"Authorization": f"Api-Key {api_key}"}, timeout=10, verify=False)
    assert parts_resp.status_code == 200, f"Participations failed ({parts_resp.status_code}): {parts_resp.text[:500]}"
    parts_data = parts_resp.json()
    assert "results" in parts_data
    assert isinstance(parts_data["results"], list)
