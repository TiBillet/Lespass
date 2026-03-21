"""
tests/pytest/test_discovery_pin_pairing.py — Flow PIN pairing pour terminaux.
tests/pytest/test_discovery_pin_pairing.py — PIN pairing flow for terminals.

Source PW TS : 30

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_discovery_pin_pairing.py -v
"""

import os
import sys
import json
import uuid

sys.path.insert(0, '/DjangoFiles')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

import django

django.setup()

import pytest
from django.test import Client as DjangoClient
from django_tenants.utils import schema_context

from Customers.models import Client as TenantClient
from discovery.models import PairingDevice

TENANT_SCHEMA = 'lespass'


def _public_client():
    """Client HTTP pour les routes publiques (schema public via HTTP_HOST).
    / HTTP client for public routes (public schema via HTTP_HOST)."""
    # Les routes /api/discovery/ sont dans urls_public.py (schema public)
    # Le domaine public est tibillet.localhost
    # / /api/discovery/ routes are in urls_public.py (public schema)
    # Public domain is tibillet.localhost
    return DjangoClient(HTTP_HOST='tibillet.localhost')


class TestDiscoveryPinPairing:
    """Flow d'appairage PIN pour terminaux POS.
    / PIN pairing flow for POS terminals."""

    def test_pairing_device_genere_pin(self):
        """30a — Créer un PairingDevice → PIN 6 chiffres généré.
        / Create PairingDevice → 6-digit PIN generated."""
        uid = uuid.uuid4().hex[:8]

        tenant = TenantClient.objects.get(schema_name=TENANT_SCHEMA)
        pin = PairingDevice.generate_unique_pin()

        device = PairingDevice.objects.create(
            name=f'Terminal Test {uid}',
            tenant=tenant,
            pin_code=pin,
        )

        assert device.pin_code is not None
        assert 100000 <= device.pin_code <= 999999, (
            f"Le PIN devrait être 6 chiffres, trouvé {device.pin_code}"
        )
        assert device.is_claimed is False

    def test_claim_pin_valide(self):
        """30b — POST /api/discovery/claim/ avec PIN valide → 200 + server_url + api_key.
        / POST /api/discovery/claim/ with valid PIN → 200 + server_url + api_key."""
        uid = uuid.uuid4().hex[:8]

        tenant = TenantClient.objects.get(schema_name=TENANT_SCHEMA)
        pin = PairingDevice.generate_unique_pin()

        device = PairingDevice.objects.create(
            name=f'Terminal Claim {uid}',
            tenant=tenant,
            pin_code=pin,
        )

        client = _public_client()
        resp = client.post(
            '/api/discovery/claim/',
            data=json.dumps({'pin_code': str(pin)}),
            content_type='application/json',
        )

        assert resp.status_code == 200, f"Status inattendu : {resp.status_code}, body: {resp.content.decode()}"
        data = resp.json()

        assert 'server_url' in data, "La réponse devrait contenir server_url"
        assert 'api_key' in data, "La réponse devrait contenir api_key"
        assert 'device_name' in data, "La réponse devrait contenir device_name"
        assert data['device_name'] == f'Terminal Claim {uid}'
        assert len(data['api_key']) > 0, "api_key ne devrait pas être vide"

        # Le device est marqué comme réclamé / Device is marked as claimed
        device.refresh_from_db()
        assert device.is_claimed is True
        assert device.pin_code is None, "Le PIN devrait être vidé après claim"

    def test_reclaim_pin_rejete(self):
        """30c — POST même PIN après claim → 400.
        / POST same PIN after claim → 400."""
        uid = uuid.uuid4().hex[:8]

        tenant = TenantClient.objects.get(schema_name=TENANT_SCHEMA)
        pin = PairingDevice.generate_unique_pin()

        device = PairingDevice.objects.create(
            name=f'Terminal Reclaim {uid}',
            tenant=tenant,
            pin_code=pin,
        )

        client = _public_client()

        # Premier claim → succès / First claim → success
        resp1 = client.post(
            '/api/discovery/claim/',
            data=json.dumps({'pin_code': str(pin)}),
            content_type='application/json',
        )
        assert resp1.status_code == 200

        # Deuxième claim → rejeté (PIN consommé)
        # / Second claim → rejected (PIN consumed)
        resp2 = client.post(
            '/api/discovery/claim/',
            data=json.dumps({'pin_code': str(pin)}),
            content_type='application/json',
        )
        assert resp2.status_code == 400, (
            f"Le re-claim devrait être rejeté (400), trouvé {resp2.status_code}"
        )
