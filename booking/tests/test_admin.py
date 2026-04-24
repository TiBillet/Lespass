"""
Smoke tests for the Django admin pages of the booking module.
Verifies that admin URLs are registered and return 200 for staff.
Does not test Django's own admin behaviour.

LOCALISATION : booking/tests/test_admin.py

Run:
    docker exec lespass_django poetry run pytest booking/tests/test_admin.py -v
"""
import os
import sys

sys.path.insert(0, '/DjangoFiles')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

import django
django.setup()

import pytest
from django_tenants.utils import schema_context

TENANT_SCHEMA = 'lespass'

ADMIN_LIST_URLS = [
    '/admin/booking/resource/',
    '/admin/booking/weeklyopening/',
    '/admin/booking/calendar/',
    '/admin/booking/booking/',
]


class TestAdminSmoke:

    @pytest.mark.parametrize('url', ADMIN_LIST_URLS)
    def test_admin_list_page_returns_200(self, admin_client, url):
        """
        Every booking admin list page is accessible to staff (HTTP 200).
        """
        with schema_context(TENANT_SCHEMA):
            response = admin_client.get(url)
            assert response.status_code == 200, (
                f"{url} — expected 200, got {response.status_code}"
            )

    def test_admin_booking_list_filter_by_date(self, admin_client):
        with schema_context(TENANT_SCHEMA):
            response = admin_client.get(
                '/admin/booking/booking/?start_datetime__date__gte=2026-01-01'
            )
            assert response.status_code == 200

    def test_admin_booking_list_filter_by_status(self, admin_client):
        with schema_context(TENANT_SCHEMA):
            response = admin_client.get('/admin/booking/booking/?status=new')
            assert response.status_code == 200
