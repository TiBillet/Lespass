"""
Integration test (pytest) - API v2 Membership create + retrieve.

This test creates:
- a Membership Product (schema.org/Product)
- a ProgramMembership (schema.org/ProgramMembership)
Then it retrieves the membership by UUID.

Prerequisites:
- API_KEY with permission "product" and "membership"
- API_BASE_URL reachable (default https://lespass.tibillet.localhost)

Run:
  poetry run pytest -q tests/pytest/test_membership_create.py
"""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests


@pytest.mark.integration
def test_membership_create_and_retrieve():
    base_url = os.getenv("API_BASE_URL", "https://lespass.tibillet.localhost").rstrip("/")
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise Exception("API key not set")

    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }

    # Create Membership Product + Offer
    product_payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": f"API v2 Membership Product {uuid.uuid4()}",
        "description": "Membership product for API test",
        "category": "Membership",
        "offers": [
            {
                "@type": "Offer",
                "name": "Membership rate",
                "price": "10.00",
                "priceCurrency": "EUR",
            }
        ],
    }
    product_resp = requests.post(
        f"{base_url}/api/v2/products/",
        headers=headers,
        data=json.dumps(product_payload),
        timeout=10,
        verify=False,
    )
    assert product_resp.status_code == 201, f"Product create failed: {product_resp.status_code} {product_resp.text[:300]}"
    product_data = product_resp.json()
    offers = product_data.get("offers") or []
    price_uuid = offers[0].get("identifier") if offers else None
    assert price_uuid, f"Offer identifier missing: {product_data}"

    # Create Membership
    valid_until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    membership_payload = {
        "@context": "https://schema.org",
        "@type": "ProgramMembership",
        "member": {
            "@type": "Person",
            "email": f"member-{uuid.uuid4()}@example.org",
            "givenName": "API",
            "familyName": "Test",
        },
        "membershipPlan": {
            "@type": "Offer",
            "identifier": price_uuid,
        },
        "validUntil": valid_until,
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "paymentMode", "value": "FREE"}
        ],
    }
    membership_resp = requests.post(
        f"{base_url}/api/v2/memberships/",
        headers=headers,
        data=json.dumps(membership_payload),
        timeout=10,
        verify=False,
    )
    assert membership_resp.status_code == 201, (
        f"Membership create failed: {membership_resp.status_code} {membership_resp.text[:300]}"
    )
    membership_data = membership_resp.json()
    membership_uuid = membership_data.get("identifier")
    assert membership_uuid, f"Membership identifier missing: {membership_data}"
    assert membership_data.get("membershipPlan", {}).get("identifier") == price_uuid

    # Retrieve Membership
    det_resp = requests.get(
        f"{base_url}/api/v2/memberships/{membership_uuid}/",
        headers=headers,
        timeout=10,
        verify=False,
    )
    assert det_resp.status_code == 200, f"Membership retrieve failed: {det_resp.status_code} {det_resp.text[:300]}"
    det_data = det_resp.json()
    assert det_data.get("identifier") == membership_uuid
    assert det_data.get("membershipPlan", {}).get("identifier") == price_uuid
