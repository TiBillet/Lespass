"""
Tests des exports CSV et PDF du bilan de billetterie.
/ Tests for CSV and PDF exports of the ticketing report.
LOCALISATION : tests/pytest/test_bilan_exports.py
"""

import pytest


@pytest.mark.django_db
class TestBilanExports:
    def _get_event_with_data(self, tenant):
        """Retourne un event ayant des LigneArticle VALID. / Returns an event with VALID LigneArticle."""
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Event
        from django.db.models import Count, Q

        with tenant_context(tenant):
            event = (
                Event.objects.annotate(
                    nb_lignes=Count(
                        "reservation__lignearticles",
                        filter=Q(reservation__lignearticles__status="V"),
                    )
                )
                .filter(nb_lignes__gt=0)
                .first()
            )
            return event

    def test_export_csv(self, admin_client, tenant):
        """Export CSV retourne un fichier CSV valide. / CSV export returns a valid CSV file."""
        event = self._get_event_with_data(tenant)
        if event is None:
            pytest.skip("Pas d'event avec des ventes dans la DB dev")
        url = f"/admin/BaseBillet/event/{event.pk}/bilan/csv/"
        response = admin_client.get(url)
        assert response.status_code == 200
        assert "text/csv" in response["Content-Type"]
        content = response.content.decode("utf-8-sig")
        assert "SYNTHESE" in content
        assert "VENTES PAR TARIF" in content
        assert ";" in content

    def test_export_csv_event_vide(self, admin_client, tenant):
        """Export CSV fonctionne sur un event sans reservations. / CSV export works on event without reservations."""
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Event

        with tenant_context(tenant):
            event = Event.objects.filter(reservation__isnull=True).first()
        if event is None:
            pytest.skip("Pas d'event sans reservations")
        url = f"/admin/BaseBillet/event/{event.pk}/bilan/csv/"
        response = admin_client.get(url)
        assert response.status_code == 200

    def test_export_pdf(self, admin_client, tenant):
        """Export PDF retourne un fichier PDF valide. / PDF export returns a valid PDF file."""
        event = self._get_event_with_data(tenant)
        if event is None:
            pytest.skip("Pas d'event avec des ventes dans la DB dev")
        url = f"/admin/BaseBillet/event/{event.pk}/bilan/pdf/"
        response = admin_client.get(url)
        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert len(response.content) > 500

    def test_export_pdf_event_vide(self, admin_client, tenant):
        """Export PDF fonctionne sur un event sans reservations. / PDF export works on event without reservations."""
        from django_tenants.utils import tenant_context
        from BaseBillet.models import Event

        with tenant_context(tenant):
            event = Event.objects.filter(reservation__isnull=True).first()
        if event is None:
            pytest.skip("Pas d'event sans reservations")
        url = f"/admin/BaseBillet/event/{event.pk}/bilan/pdf/"
        response = admin_client.get(url)
        assert response.status_code == 200
