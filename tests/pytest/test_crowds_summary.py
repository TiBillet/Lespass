"""
tests/pytest/test_crowds_summary.py — Page résumé crowds avec data-testid.
tests/pytest/test_crowds_summary.py — Crowds summary page with data-testid.

Source PW TS : 24

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_crowds_summary.py -v
"""

import os
import sys

sys.path.insert(0, '/DjangoFiles')

import django

django.setup()

import pytest
from django_tenants.utils import schema_context

TENANT_SCHEMA = 'lespass'


class TestCrowdsSummary:
    """Vérification de la page résumé crowds.
    / Crowds summary page verification."""

    def test_page_crowds_contient_data_testid(self, api_client):
        """24 — GET /crowd/ → HTML contient les data-testid du résumé.
        / GET /crowd/ → HTML contains summary data-testid."""
        with schema_context(TENANT_SCHEMA):
            resp = api_client.get('/crowd/')

            # La page crowds peut ne pas exister si le module n'est pas activé
            # / Crowds page may not exist if module is not enabled
            if resp.status_code == 404:
                pytest.skip("Module crowds non activé sur ce tenant")

            assert resp.status_code == 200, f"Status inattendu : {resp.status_code}"
            content = resp.content.decode()

            # Vérifier les data-testid du résumé
            # / Verify summary data-testid attributes
            expected_testids = [
                'crowds-summary-bar',
                'crowds-summary-contributors',
                'crowds-summary-time',
                'crowds-summary-funding',
            ]
            for testid in expected_testids:
                assert testid in content, (
                    f"La page crowds devrait contenir data-testid='{testid}'"
                )
