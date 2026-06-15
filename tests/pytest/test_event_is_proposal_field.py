"""
Test du champ Event.is_proposal (chantier EVENT_WIZARD).
/ Test for the Event.is_proposal field.
"""

import uuid

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context

from Customers.models import Client


@pytest.fixture(scope="session")
def django_db_setup():
    # Use the existing dev DB (do not create a fresh test DB).
    # / Utiliser la base de dev existante (pas de creation de base de test).
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access(django_db_blocker):
    django_db_blocker.unblock()


@pytest.mark.django_db
def test_is_proposal_default_false():
    from BaseBillet.models import Event
    tenant = Client.objects.get(schema_name="lespass")  # tenant EXPLICITE — .first() peut tomber sur un tenant W sans domaine / explicit tenant, .first() may hit a domainless W tenant
    with tenant_context(tenant):
        suffix = uuid.uuid4().hex[:8]
        event = Event.objects.create(
            name=f"Test default flag {suffix}",
            datetime=timezone.now() + timezone.timedelta(days=1),
        )
        assert event.is_proposal is False
        # On evite event.delete() — le signal post_delete de stdimage plante
        # quand l'image est None (queryset.delete() saute ce signal).
        # / Avoid event.delete() — stdimage post_delete crashes when img is None.
        Event.objects.filter(pk=event.pk).delete()


@pytest.mark.django_db
def test_is_proposal_can_be_set_true():
    from BaseBillet.models import Event
    tenant = Client.objects.get(schema_name="lespass")  # tenant EXPLICITE — .first() peut tomber sur un tenant W sans domaine / explicit tenant, .first() may hit a domainless W tenant
    with tenant_context(tenant):
        suffix = uuid.uuid4().hex[:8]
        event = Event.objects.create(
            name=f"Test proposal flag {suffix}",
            datetime=timezone.now() + timezone.timedelta(days=1),
            is_proposal=True,
            published=False,
        )
        assert event.is_proposal is True
        assert event.published is False
        Event.objects.filter(pk=event.pk).delete()
