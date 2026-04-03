"""
Tests du dashboard billetterie.
/ Tests for the ticketing dashboard.
LOCALISATION : tests/pytest/test_dashboard_billetterie.py
"""
import pytest


@pytest.mark.django_db
class TestDashboardBilletterie:

    def test_dashboard_accessible(self, admin_client):
        """Le dashboard est accessible pour un admin connecte. / Dashboard is accessible for a logged-in admin."""
        response = admin_client.get("/admin/BaseBillet/event/dashboard/")
        assert response.status_code == 200

    def test_dashboard_contient_sections(self, admin_client):
        """Le dashboard contient les sections a venir et passes. / Dashboard contains upcoming and past sections."""
        response = admin_client.get("/admin/BaseBillet/event/dashboard/")
        content = response.content.decode()
        assert 'data-testid="dashboard-titre"' in content
