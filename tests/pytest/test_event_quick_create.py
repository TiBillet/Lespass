"""
tests/pytest/test_event_quick_create.py — Création rapide d'événement + doublon.
tests/pytest/test_event_quick_create.py — Quick event creation + duplicate rejection.

Source PW TS : 21

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_event_quick_create.py -v
"""

import os
import sys
import uuid

sys.path.insert(0, '/DjangoFiles')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

import django

django.setup()

import pytest
from datetime import timedelta
from django.utils import timezone
from django_tenants.utils import schema_context

from BaseBillet.models import Event

TENANT_SCHEMA = 'lespass'


class TestEventQuickCreate:
    """Création rapide d'événement via formulaire offcanvas HTMX.
    / Quick event creation via HTMX offcanvas form."""

    def test_creation_reussie(self, admin_client):
        """21a — POST simple_create_event → Event créé en base.
        / POST simple_create_event → Event created in DB."""
        uid = uuid.uuid4().hex[:8]
        event_name = f'QuickEvent {uid}'
        dt_start = (timezone.now() + timedelta(days=60)).strftime('%Y-%m-%dT%H:%M')
        dt_end = (timezone.now() + timedelta(days=60, hours=3)).strftime('%Y-%m-%dT%H:%M')

        with schema_context(TENANT_SCHEMA):
            count_before = Event.objects.count()

            resp = admin_client.post('/event/simple_create_event/', {
                'name': event_name,
                'datetime_start': dt_start,
                'datetime_end': dt_end,
                'short_description': f'Test rapide {uid}',
                'long_description': '',
            })

            # Le succès redirige vers /event/ (302 ou HX-Redirect)
            # / Success redirects to /event/ (302 or HX-Redirect)
            assert resp.status_code in (200, 301, 302), f"Status inattendu : {resp.status_code}"

            # Vérifier que l'événement existe en base
            # / Verify event exists in DB
            assert Event.objects.filter(name=event_name).exists(), (
                f"L'événement '{event_name}' devrait exister en base"
            )
            assert Event.objects.count() == count_before + 1

    def test_doublon_rejete(self, admin_client):
        """21b — POST identique → erreur de doublon.
        / Identical POST → duplicate error."""
        uid = uuid.uuid4().hex[:8]
        event_name = f'DoublonEvent {uid}'
        dt_start = (timezone.now() + timedelta(days=61)).strftime('%Y-%m-%dT%H:%M')
        dt_end = (timezone.now() + timedelta(days=61, hours=2)).strftime('%Y-%m-%dT%H:%M')

        with schema_context(TENANT_SCHEMA):
            # Première création → succès
            # / First creation → success
            admin_client.post('/event/simple_create_event/', {
                'name': event_name,
                'datetime_start': dt_start,
                'datetime_end': dt_end,
                'long_description': '',
            })
            assert Event.objects.filter(name=event_name).exists()

            count_after_first = Event.objects.count()

            # Deuxième création identique → erreur
            # / Second identical creation → error
            resp = admin_client.post('/event/simple_create_event/', {
                'name': event_name,
                'datetime_start': dt_start,
                'datetime_end': dt_end,
                'long_description': '',
            })

            # Le formulaire est re-rendu avec une erreur (status 200, pas de redirect)
            # / Form is re-rendered with an error (status 200, no redirect)
            content = resp.content.decode()
            # Le message d'erreur contient "existe déjà" ou "already exists"
            # / Error message contains "existe déjà" or "already exists"
            assert 'existe' in content.lower() or 'already' in content.lower() or 'alert-danger' in content, (
                "Le formulaire devrait afficher une erreur de doublon"
            )

            # Pas de nouvel événement créé
            # / No new event created
            assert Event.objects.count() == count_after_first, (
                "Aucun nouvel événement ne devrait être créé"
            )
