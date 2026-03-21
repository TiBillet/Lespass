"""
tests/pytest/test_user_account_summary.py — Test page "Mes reservations" du compte utilisateur.
tests/pytest/test_user_account_summary.py — Test "My reservations" user account page.

Cree un event + product + reservation via API, puis verifie que la page
/my_account/my_reservations/ affiche le nom de l'event.

Converti depuis : tests/playwright/tests/admin/16-user-account-summary.spec.ts
Converted from: tests/playwright/tests/admin/16-user-account-summary.spec.ts

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_user_account_summary.py -v
"""

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, '/DjangoFiles')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

import django

django.setup()

import pytest

from django.test import Client as DjangoClient
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser, Wallet
from Customers.models import Client


TENANT_SCHEMA = 'lespass'


class TestUserAccountSummary:
    """Test de la page 'Mes reservations' pour un utilisateur connecte.
    / Test of the 'My reservations' page for a logged-in user."""

    def test_reservation_visible_in_my_account(self, api_client, auth_headers):
        """Cree event + product + reservation, puis verifie /my_account/my_reservations/.
        / Creates event + product + reservation, then checks /my_account/my_reservations/."""

        # 1. Creer un event via API v2
        # / Create an event via API v2
        start = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        event_name = f"Account Summary Test {uuid.uuid4()}"
        event_resp = api_client.post(
            '/api/v2/events/',
            data=json.dumps({
                "@context": "https://schema.org",
                "@type": "Event",
                "name": event_name,
                "startDate": start,
            }),
            content_type='application/json',
            **auth_headers,
        )
        assert event_resp.status_code == 201, f"Event create: {event_resp.status_code}"
        event_uuid = event_resp.json().get("identifier")

        # 2. Creer un product (Free booking) lie a l'event
        # / Create a product (Free booking) linked to the event
        product_resp = api_client.post(
            '/api/v2/products/',
            data=json.dumps({
                "@context": "https://schema.org",
                "@type": "Product",
                "name": f"Free ticket {uuid.uuid4()}",
                "category": "Free booking",
                "isRelatedTo": {"@type": "Event", "identifier": event_uuid},
                "offers": [{
                    "@type": "Offer",
                    "name": "Gratuit",
                    "price": "0.00",
                    "priceCurrency": "EUR",
                }],
            }),
            content_type='application/json',
            **auth_headers,
        )
        assert product_resp.status_code == 201, f"Product create: {product_resp.status_code}"
        price_uuid = product_resp.json()["offers"][0]["identifier"]

        # 3. Creer une reservation pour un utilisateur de test
        # / Create a reservation for a test user
        user_email = f"account-test-{uuid.uuid4()}@example.org"
        resa_resp = api_client.post(
            '/api/v2/reservations/',
            data=json.dumps({
                "@context": "https://schema.org",
                "@type": "Reservation",
                "reservationFor": {"@type": "Event", "identifier": event_uuid},
                "underName": {"@type": "Person", "email": user_email},
                "reservedTicket": [{
                    "@type": "Ticket",
                    "identifier": price_uuid,
                    "ticketQuantity": 1,
                }],
                "additionalProperty": [
                    {"@type": "PropertyValue", "name": "confirmed", "value": True},
                ],
            }),
            content_type='application/json',
            **auth_headers,
        )
        assert resa_resp.status_code == 201, f"Reservation create: {resa_resp.status_code}"

        # 4. Se connecter en tant que cet utilisateur et verifier la page
        # / Log in as this user and check the page
        with schema_context(TENANT_SCHEMA):
            user = TibilletUser.objects.get(email=user_email)
            # Le user cree par l'API a is_active=False — l'activer pour le test
            # / User created by API has is_active=False — activate for the test
            if not user.is_active:
                user.is_active = True
            # S'assurer que le user a un wallet (sinon dispatch appelle FedowAPI)
            # / Ensure the user has a wallet (otherwise dispatch calls FedowAPI)
            if not user.wallet:
                tenant = Client.objects.get(schema_name=TENANT_SCHEMA)
                wallet = Wallet.objects.create(origin=tenant)
                user.wallet = wallet
            user.save()

        # force_login et get() hors schema_context — le middleware gere le tenant via HTTP_HOST
        # / force_login and get() outside schema_context — middleware handles tenant via HTTP_HOST
        client = DjangoClient(HTTP_HOST='lespass.tibillet.localhost')
        client.force_login(user)

        resp = client.get('/my_account/my_reservations/')
        assert resp.status_code == 200, f"My reservations: {resp.status_code}"
        html = resp.content.decode()
        assert event_name in html, (
            f"Le nom de l'event '{event_name}' doit apparaitre dans la page mes reservations"
        )
