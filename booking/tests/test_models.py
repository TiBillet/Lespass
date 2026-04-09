"""
Tests des modèles booking — règles métier de base.
/ booking model tests — core business rules.

LOCALISATION : booking/tests/test_models.py

Lancement / Run:
    docker exec lespass_django poetry run pytest booking/tests/test_models.py -v
"""
import datetime

import pytest
from django.core.exceptions import ValidationError
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


@pytest.mark.django_db
def test_closed_period_rejects_end_date_before_start_date():
    """
    Un ClosedPeriod dont end_date est antérieure à start_date est refusé.
    / A ClosedPeriod with end_date before start_date is rejected.

    LOCALISATION : booking/tests/test_models.py

    Deux niveaux de protection (decisions §8) :
    - clean() lève ValidationError avant tout accès à la base.
    - CheckConstraint garantit l'intégrité même hors de Django.
    / Two levels of protection (decisions §8):
    - clean() raises ValidationError before any DB access.
    - CheckConstraint enforces integrity even outside Django.
    """
    from booking.models import Calendar, ClosedPeriod

    with schema_context(TENANT_SCHEMA):
        calendar = Calendar.objects.create(name=f'{TEST_PREFIX} end_before_start')
        try:
            period = ClosedPeriod(
                calendar=calendar,
                start_date=datetime.date(2026, 6, 10),
                end_date=datetime.date(2026, 6, 8),   # antérieure / before start
                label='Invalide',
            )
            with pytest.raises(ValidationError):
                period.full_clean()
        finally:
            ClosedPeriod.objects.filter(calendar=calendar).delete()
            calendar.delete()


@pytest.mark.django_db
def test_closed_period_accepts_end_date_equal_to_start_date():
    """
    Un ClosedPeriod avec end_date == start_date est accepté (fermeture d'un jour).
    / A ClosedPeriod with end_date == start_date is accepted (single-day closure).

    LOCALISATION : booking/tests/test_models.py
    """
    from booking.models import Calendar, ClosedPeriod

    with schema_context(TENANT_SCHEMA):
        calendar = Calendar.objects.create(name=f'{TEST_PREFIX} same_day')
        try:
            period = ClosedPeriod(
                calendar=calendar,
                start_date=datetime.date(2026, 6, 10),
                end_date=datetime.date(2026, 6, 10),
                label='Jour férié',
            )
            period.full_clean()   # ne doit pas lever / must not raise
        finally:
            ClosedPeriod.objects.filter(calendar=calendar).delete()
            calendar.delete()


@pytest.mark.django_db
def test_closed_period_accepts_null_end_date():
    """
    Un ClosedPeriod avec end_date null est accepté (fermeture sans fin).
    / A ClosedPeriod with null end_date is accepted (endless closure).

    LOCALISATION : booking/tests/test_models.py
    """
    from booking.models import Calendar, ClosedPeriod

    with schema_context(TENANT_SCHEMA):
        calendar = Calendar.objects.create(name=f'{TEST_PREFIX} null_end_date')
        try:
            period = ClosedPeriod(
                calendar=calendar,
                start_date=datetime.date(2026, 6, 10),
                end_date=None,
                label='Fermeture indéfinie',
            )
            period.full_clean()   # ne doit pas lever / must not raise
        finally:
            ClosedPeriod.objects.filter(calendar=calendar).delete()
            calendar.delete()
