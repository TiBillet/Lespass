"""
API v2 : créer un événement qui bloque une ressource du module réservation.
/ API v2: create an event that blocks a booking resource.

LOCALISATION : tests/pytest/test_api_v2_event_ressource_bloquee.py

Code testé :
- api_v2/serializers.py : EventCreateSerializer, additionalProperty "blockedResource"

Le blocage des créneaux lui-même est testé dans
booking/tests/test_ressource_bloquee_par_evenement.py.

Lancement / Run:
  poetry run pytest -q tests/pytest/test_api_v2_event_ressource_bloquee.py
"""

import datetime

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context

DEBUT_DE_L_EVENEMENT = timezone.now() + datetime.timedelta(days=10)
FIN_DE_L_EVENEMENT = DEBUT_DE_L_EVENEMENT + datetime.timedelta(hours=3)


def _creer_une_salle(label):
    from booking.tests.test_booking_engine import (
        _make_calendar,
        _make_resource,
        _make_weekly_opening,
    )

    return _make_resource(
        label,
        _make_calendar(label),
        _make_weekly_opening(label),
    )


def _donnees_de_l_evenement(identifiant_de_la_ressource, avec_une_fin=True):
    donnees = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": "Test API v2 ressource bloquee",
        "startDate": DEBUT_DE_L_EVENEMENT.isoformat(),
        "additionalProperty": [
            {
                "@type": "PropertyValue",
                "name": "blockedResource",
                "value": identifiant_de_la_ressource,
            },
        ],
    }
    if avec_une_fin:
        donnees["endDate"] = FIN_DE_L_EVENEMENT.isoformat()
    return donnees


@pytest.mark.django_db
def test_l_api_cree_un_evenement_qui_bloque_la_ressource(tenant):
    """
    blockedResource + endDate : l'événement créé pointe vers la ressource.
    La réponse ne contient pas la ressource (champ interne).
    / blockedResource + endDate: the event points to the resource; not in the response.
    """
    from api_v2.serializers import EventCreateSerializer, EventSchemaSerializer
    from booking.tests.test_booking_engine import _cleanup

    with tenant_context(tenant):
        evenement_cree = None
        try:
            salle = _creer_une_salle("api_v2_bloquee")
            serializer = EventCreateSerializer(data=_donnees_de_l_evenement(salle.pk))
            assert serializer.is_valid(), serializer.errors
            evenement_cree = serializer.save()

            evenement_cree.refresh_from_db()
            assert evenement_cree.ressource_bloquee_id == salle.pk

            reponse = EventSchemaSerializer(evenement_cree).data
            assert "blockedResource" not in str(reponse)
        finally:
            if evenement_cree is not None:
                evenement_cree.delete()
            _cleanup()


@pytest.mark.django_db
def test_l_api_refuse_de_bloquer_une_ressource_sans_date_de_fin(tenant):
    """
    Sans endDate, on ne sait pas jusqu'à quand bloquer : erreur sur endDate.
    / Without endDate we cannot know until when to block: error on endDate.
    """
    from api_v2.serializers import EventCreateSerializer
    from booking.tests.test_booking_engine import _cleanup

    with tenant_context(tenant):
        try:
            salle = _creer_une_salle("api_v2_sans_fin")
            serializer = EventCreateSerializer(
                data=_donnees_de_l_evenement(salle.pk, avec_une_fin=False)
            )
            assert not serializer.is_valid()
            assert "endDate" in serializer.errors
        finally:
            _cleanup()


@pytest.mark.django_db
def test_l_api_refuse_une_ressource_introuvable(tenant):
    """
    Un id de ressource qui n'existe pas : erreur sur additionalProperty.
    / An unknown resource id: error on additionalProperty.
    """
    from api_v2.serializers import EventCreateSerializer

    with tenant_context(tenant):
        serializer = EventCreateSerializer(data=_donnees_de_l_evenement(999999999))
        assert not serializer.is_valid()
        assert "additionalProperty" in serializer.errors
