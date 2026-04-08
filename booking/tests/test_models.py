"""
Tests des modèles booking — règles métier de base.
/ booking model tests — core business rules.

LOCALISATION : booking/tests/test_models.py

Lancement / Run:
    docker exec lespass_django poetry run pytest booking/tests/test_models.py -v
"""
import pytest
from django.utils import timezone
from django_tenants.utils import schema_context

TEST_PREFIX = '[test_booking_models]'
TENANT_SCHEMA = 'lespass'


@pytest.mark.django_db
def test_booking_default_status_is_new(test_resource, test_user):
    """
    Une Booking créée sans status explicite a le statut 'new'.
    / A Booking created without explicit status has status 'new'.

    LOCALISATION : booking/tests/test_models.py

    'new' = dans le panier, en attente de validation par le membre.
    / 'new' = in basket, pending validation by the member.
    """
    from booking.models import Booking

    with schema_context(TENANT_SCHEMA):
        booking = Booking.objects.create(
            resource=test_resource,
            user=test_user,
            start_datetime=timezone.now(),
            slot_duration_minutes=60,
            slot_count=1,
        )
        assert booking.status == 'new'
        booking.delete()
