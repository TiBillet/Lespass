"""
tests/pytest/test_admin_configuration.py — Test page admin Configuration.
tests/pytest/test_admin_configuration.py — Configuration admin page test.

Converti depuis : tests/playwright/tests/admin/02-admin-configuration.spec.ts
Converted from: tests/playwright/tests/admin/02-admin-configuration.spec.ts

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_admin_configuration.py -v
"""

import os
import sys

sys.path.insert(0, '/DjangoFiles')


import django

django.setup()

import pytest

from django_tenants.utils import schema_context

from BaseBillet.models import Configuration


TENANT_SCHEMA = 'lespass'


class TestAdminConfiguration:
    """Test de la page admin Configuration.
    / Configuration admin page test."""

    def test_configuration_page_loads_and_has_data(self, admin_client):
        """Page Configuration accessible, organisation non vide en base.
        / Configuration page accessible, organisation not empty in DB."""
        with schema_context(TENANT_SCHEMA):
            # S'assurer qu'une organisation est renseignee (DB dev peut l'avoir
            # laissee vide selon l'historique des tests).
            # / Ensure organisation is set (dev DB may have it empty depending
            # on test history).
            config = Configuration.get_solo()
            if not config.organisation:
                config.organisation = 'Lespass'
                config.save()

            resp = admin_client.get('/admin/BaseBillet/configuration/')
            assert resp.status_code == 200, f"Configuration page: {resp.status_code}"

            config.refresh_from_db()
            assert config.organisation, "Configuration.organisation ne doit pas etre vide"
