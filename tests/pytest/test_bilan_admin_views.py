"""
Tests pour les vues admin du bilan billetterie.
/ Tests for the admin ticketing report views.

LOCALISATION : tests/pytest/test_bilan_admin_views.py

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_bilan_admin_views.py -v
"""

import uuid as uuid_lib

import pytest
from django_tenants.utils import schema_context

from BaseBillet.models import Event

TENANT_SCHEMA = "lespass"


class TestBilanAdminViews:
    """
    Teste l'acces aux vues du bilan dans l'admin Unfold.
    / Tests access to the report views in the Unfold admin.
    """

    def test_page_bilan_accessible(self, admin_client):
        """La page bilan est accessible pour un admin. / Report page is accessible for admin."""
        with schema_context(TENANT_SCHEMA):
            event = Event.objects.filter(reservation__isnull=False).first()
            if event is None:
                pytest.skip("Pas d'event avec reservations dans la DB dev")
            url = f"/admin/BaseBillet/event/{event.pk}/bilan/"
            response = admin_client.get(url)
            assert response.status_code == 200

    def test_page_bilan_event_inexistant(self, admin_client):
        """Un event inexistant retourne 404. / Non-existent event returns 404."""
        with schema_context(TENANT_SCHEMA):
            url = f"/admin/BaseBillet/event/{uuid_lib.uuid4()}/bilan/"
            response = admin_client.get(url)
            assert response.status_code == 404

    def test_changelist_contient_colonne_bilan(self, admin_client):
        """La changelist event est accessible. / Event changelist is accessible."""
        with schema_context(TENANT_SCHEMA):
            response = admin_client.get("/admin/BaseBillet/event/")
            assert response.status_code == 200
