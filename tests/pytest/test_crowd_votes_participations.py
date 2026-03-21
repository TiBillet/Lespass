"""Read votes count and participations list via API v2 Crowds."""
import json
import uuid

import pytest


def _ensure_initiative(api_client, auth_headers, request):
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
    resp = api_client.post(
        '/api/v2/initiatives/',
        data=json.dumps(payload),
        content_type='application/json',
        **auth_headers,
    )
    assert resp.status_code == 201, f"Create failed ({resp.status_code}): {resp.content.decode()[:500]}"
    data = resp.json()
    identifier = data.get("identifier")
    assert identifier
    request.config.cache.set("api_v2_crowd_initiative_uuid", identifier)
    return identifier


@pytest.mark.integration
def test_crowd_votes_and_participations(request, api_client, auth_headers):
    initiative_uuid = _ensure_initiative(api_client, auth_headers, request)

    votes_url = f'/api/v2/initiatives/{initiative_uuid}/votes/'
    vote_post = api_client.post(votes_url, content_type='application/json', **auth_headers)
    assert vote_post.status_code == 201, f"Vote post failed ({vote_post.status_code}): {vote_post.content.decode()[:500]}"
    vote_data = vote_post.json()
    assert isinstance(vote_data.get("count"), int)

    votes_resp = api_client.get(votes_url, **auth_headers)
    assert votes_resp.status_code == 200, f"Votes failed ({votes_resp.status_code}): {votes_resp.content.decode()[:500]}"
    votes_data = votes_resp.json()
    assert isinstance(votes_data.get("count"), int)
    assert votes_data.get("count") >= 1

    parts_url = f'/api/v2/initiatives/{initiative_uuid}/participations/'
    part_payload = {"description": "Participation API v2", "amount": "45.00"}
    part_post = api_client.post(
        parts_url,
        data=json.dumps(part_payload),
        content_type='application/json',
        **auth_headers,
    )
    assert part_post.status_code == 201, f"Participation post failed ({part_post.status_code}): {part_post.content.decode()[:500]}"
    part_data = part_post.json()
    assert part_data.get("description") == part_payload["description"]

    parts_resp = api_client.get(parts_url, **auth_headers)
    assert parts_resp.status_code == 200, f"Participations failed ({parts_resp.status_code}): {parts_resp.content.decode()[:500]}"
    parts_data = parts_resp.json()
    assert "results" in parts_data
    assert isinstance(parts_data["results"], list)
