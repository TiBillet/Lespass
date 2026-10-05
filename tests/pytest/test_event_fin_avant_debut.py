"""
Tests : un evenement ne peut pas finir avant d'avoir commence.
/ Tests: an event cannot end before it starts.

LOCALISATION : tests/pytest/test_event_fin_avant_debut.py

La regle est verifiee a trois endroits :
- Event.clean() (BaseBillet/models.py) -> utilise par l'admin (EventForm).
- EventCreateSerializer.validate (api_v2/serializers.py) -> API v2.
- EventWriteSerializer.validate (ApiBillet/serializers.py) -> API v1, creation et modification.

Les tests appellent directement le modele, le formulaire et les serializers.
Rien n'est enregistre en base.
/ Tests call the model, form and serializers directly. Nothing is saved.

Lancement / Run:
  poetry run pytest -q tests/pytest/test_event_fin_avant_debut.py
"""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from django_tenants.utils import tenant_context


DEBUT_DE_L_EVENEMENT = timezone.now() + timedelta(days=10)
FIN_AVANT_LE_DEBUT = DEBUT_DE_L_EVENEMENT - timedelta(hours=2)
FIN_APRES_LE_DEBUT = DEBUT_DE_L_EVENEMENT + timedelta(hours=2)


# --- Modele : Event.clean() ---


def test_modele_refuse_une_fin_avant_le_debut(tenant):
    from BaseBillet.models import Event

    with tenant_context(tenant):
        evenement = Event(
            name="Test fin avant debut",
            datetime=DEBUT_DE_L_EVENEMENT,
            end_datetime=FIN_AVANT_LE_DEBUT,
        )
        with pytest.raises(ValidationError) as erreur:
            evenement.clean()

    assert "end_datetime" in erreur.value.message_dict


def test_modele_accepte_une_fin_apres_le_debut(tenant):
    from BaseBillet.models import Event

    with tenant_context(tenant):
        evenement = Event(
            name="Test fin apres debut",
            datetime=DEBUT_DE_L_EVENEMENT,
            end_datetime=FIN_APRES_LE_DEBUT,
        )
        evenement.clean()


def test_modele_accepte_une_fin_egale_au_debut(tenant):
    from BaseBillet.models import Event

    with tenant_context(tenant):
        evenement = Event(
            name="Test fin egale debut",
            datetime=DEBUT_DE_L_EVENEMENT,
            end_datetime=DEBUT_DE_L_EVENEMENT,
        )
        evenement.clean()


def test_modele_accepte_un_evenement_sans_fin(tenant):
    from BaseBillet.models import Event

    with tenant_context(tenant):
        evenement = Event(
            name="Test sans fin", datetime=DEBUT_DE_L_EVENEMENT, end_datetime=None
        )
        evenement.clean()


# --- Admin : EventForm ---


def test_formulaire_admin_affiche_une_erreur_sur_la_date_de_fin(tenant):
    """
    Le ModelForm de l'admin appelle Event.clean() : l'erreur doit arriver sur le champ de fin.
    / The admin ModelForm calls Event.clean(): the error must land on the end field.
    """
    from Administration.admin_tenant import EventForm

    format_du_widget = "%Y-%m-%d %H:%M:%S"
    with tenant_context(tenant):
        formulaire = EventForm(
            data={
                "name": "Test admin fin avant debut",
                "datetime": DEBUT_DE_L_EVENEMENT.strftime(format_du_widget),
                "end_datetime": FIN_AVANT_LE_DEBUT.strftime(format_du_widget),
            }
        )
        formulaire_valide = formulaire.is_valid()

    assert not formulaire_valide
    assert "end_datetime" in formulaire.errors


# --- API v2 : EventCreateSerializer ---


def test_api_v2_refuse_une_fin_avant_le_debut(tenant):
    from api_v2.serializers import EventCreateSerializer

    with tenant_context(tenant):
        serializer = EventCreateSerializer(
            data={
                "name": "Test API v2 fin avant debut",
                "startDate": DEBUT_DE_L_EVENEMENT.isoformat(),
                "endDate": FIN_AVANT_LE_DEBUT.isoformat(),
            }
        )
        serializer_valide = serializer.is_valid()

    assert not serializer_valide
    assert "endDate" in serializer.errors


def test_api_v2_accepte_une_fin_apres_le_debut(tenant):
    from api_v2.serializers import EventCreateSerializer

    with tenant_context(tenant):
        serializer = EventCreateSerializer(
            data={
                "name": "Test API v2 fin apres debut",
                "startDate": DEBUT_DE_L_EVENEMENT.isoformat(),
                "endDate": FIN_APRES_LE_DEBUT.isoformat(),
            }
        )
        serializer_valide = serializer.is_valid()

    assert serializer_valide, serializer.errors


# --- API v1 : EventWriteSerializer ---


def test_api_v1_creation_refuse_une_fin_avant_le_debut(tenant):
    from ApiBillet.serializers import EventWriteSerializer

    with tenant_context(tenant):
        serializer = EventWriteSerializer(
            data={
                "name": "Test API v1 fin avant debut",
                "startDate": DEBUT_DE_L_EVENEMENT.isoformat(),
                "endDate": FIN_AVANT_LE_DEBUT.isoformat(),
            }
        )
        serializer_valide = serializer.is_valid()

    assert not serializer_valide
    assert "endDate" in serializer.errors


def test_api_v1_modification_partielle_compare_avec_le_debut_enregistre(tenant):
    """
    Modification partielle : seule la fin est envoyee. Le debut vient de l'evenement existant.
    / Partial update: only the end is sent. The start comes from the existing event.
    """
    from ApiBillet.serializers import EventWriteSerializer
    from BaseBillet.models import Event

    with tenant_context(tenant):
        evenement_existant = Event(
            name="Test API v1 partiel", datetime=DEBUT_DE_L_EVENEMENT
        )
        serializer = EventWriteSerializer(
            evenement_existant,
            data={"endDate": FIN_AVANT_LE_DEBUT.isoformat()},
            partial=True,
        )
        serializer_valide = serializer.is_valid()

    assert not serializer_valide
    assert "endDate" in serializer.errors


def test_api_v1_modification_partielle_accepte_une_fin_apres_le_debut_enregistre(
    tenant,
):
    from ApiBillet.serializers import EventWriteSerializer
    from BaseBillet.models import Event

    with tenant_context(tenant):
        evenement_existant = Event(
            name="Test API v1 partiel ok", datetime=DEBUT_DE_L_EVENEMENT
        )
        serializer = EventWriteSerializer(
            evenement_existant,
            data={"endDate": FIN_APRES_LE_DEBUT.isoformat()},
            partial=True,
        )
        serializer_valide = serializer.is_valid()

    assert serializer_valide, serializer.errors
