"""
Tests de l'interface d'administration Django pour le module booking.
/ Django admin interface tests for the booking module.

LOCALISATION : booking/tests/test_admin.py

Lancement / Run:
    docker exec lespass_django poetry run pytest booking/tests/test_admin.py -v
"""
import os
import sys

sys.path.insert(0, '/DjangoFiles')

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')
django.setup()

import pytest
from django_tenants.utils import schema_context

TENANT_SCHEMA = 'lespass'


class TestAdminBookingPages:

    def test_admin_resource_list_accessible_to_staff(self, admin_client):
        """
        La liste des ressources dans l'admin est accessible (200).
        / Resource list in admin is accessible (200).
        """
        with schema_context(TENANT_SCHEMA):
            response = admin_client.get('/admin/booking/resource/')
            assert response.status_code == 200, (
                f"Liste des ressources : attendu 200, obtenu {response.status_code}"
            )

    def test_admin_weekly_opening_shows_opening_entries_inline(self, admin_client):
        """
        La page de modification d'un WeeklyOpening affiche les OpeningEntry
        en inline (préfixe de formset présent dans le HTML).
        / WeeklyOpening change page shows OpeningEntry inline
        (formset prefix present in HTML).
        """
        from booking.models import WeeklyOpening

        with schema_context(TENANT_SCHEMA):
            weekly_opening = WeeklyOpening.objects.get(name='Coworking weekdays')
            url = f'/admin/booking/weeklyopening/{weekly_opening.pk}/change/'
            response = admin_client.get(url)

            assert response.status_code == 200, (
                f"Page WeeklyOpening : attendu 200, obtenu {response.status_code}"
            )
            assert b'opening_entries' in response.content, (
                "L'inline OpeningEntry (préfixe 'opening_entries') est absent de la page"
            )

    def test_admin_calendar_shows_closed_periods_inline(self, admin_client):
        """
        La page de modification d'un Calendar affiche les ClosedPeriod
        en inline (préfixe de formset présent dans le HTML).
        / Calendar change page shows ClosedPeriod inline
        (formset prefix present in HTML).
        """
        from booking.models import Calendar

        with schema_context(TENANT_SCHEMA):
            calendrier = Calendar.objects.get(name='Calendrier 2026')
            url = f'/admin/booking/calendar/{calendrier.pk}/change/'
            response = admin_client.get(url)

            assert response.status_code == 200, (
                f"Page Calendar : attendu 200, obtenu {response.status_code}"
            )
            assert b'closed_periods' in response.content, (
                "L'inline ClosedPeriod (préfixe 'closed_periods') est absent de la page"
            )

    def test_admin_booking_list_filterable_by_date(self, admin_client):
        """
        La liste des réservations accepte le filtre par date (200).
        / Booking list accepts date filter parameter (200).
        """
        with schema_context(TENANT_SCHEMA):
            url = '/admin/booking/booking/?start_datetime__date__gte=2026-01-01'
            response = admin_client.get(url)
            assert response.status_code == 200, (
                f"Filtre booking par date : attendu 200, obtenu {response.status_code}"
            )

    def test_admin_booking_list_filterable_by_status(self, admin_client):
        """
        La liste des réservations accepte le filtre par statut (200).
        / Booking list accepts status filter parameter (200).
        """
        with schema_context(TENANT_SCHEMA):
            url = '/admin/booking/booking/?status=new'
            response = admin_client.get(url)
            assert response.status_code == 200, (
                f"Filtre booking par statut : attendu 200, obtenu {response.status_code}"
            )
