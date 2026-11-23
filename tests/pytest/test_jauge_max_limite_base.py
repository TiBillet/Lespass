"""
Tests de la limite de la jauge : Event.jauge_max est un « smallint » PostgreSQL.
Une jauge plus grande que Event.JAUGE_MAXIMALE_POSSIBLE (32767) doit etre refusee
par la validation, avec un message clair, et ne jamais arriver jusqu'a la base
(sinon : « DataError: smallint out of range » et une erreur 500).
/ Gauge limit tests: Event.jauge_max is a PostgreSQL smallint. A bigger gauge must be
rejected by validation with a clear message, never reaching the DB (otherwise: a 500).

LOCALISATION : tests/pytest/test_jauge_max_limite_base.py

Les deux portes d'entree d'une jauge saisie par un humain ou un script :
- WizardEventSerializer (assistant de creation d'evenement, BaseBillet/validators.py) ;
- EventCreateSerializer (API v2, champ maximumAttendeeCapacity, api_v2/serializers.py).
Le meme fichier teste aussi les deux autres colonnes smallint remplies par l'API v2
(offers.eligibleQuantity.maxValue et offers.returnPolicy.merchantReturnDays).
"""

import pytest

from BaseBillet.models import Event
from BaseBillet.validators import WizardEventSerializer
from api_v2.serializers import EventCreateSerializer


JAUGE_TROP_GRANDE = Event.JAUGE_MAXIMALE_POSSIBLE + 1


def test_la_limite_de_jauge_vaut_le_maximum_accepte_par_la_colonne():
    """
    La constante doit valoir le maximum que la colonne jauge_max accepte. Django
    deduit ce maximum du type de la colonne et le pose en MaxValueValidator sur le
    champ. Si le type de la colonne change, ce test le signale.
    / The constant must equal the column's maximum, which Django exposes as a
    MaxValueValidator on the field. If the column type changes, this test says so.
    """
    from django.core.validators import MaxValueValidator

    champ_jauge_max = Event._meta.get_field("jauge_max")
    maximums_du_champ = []
    for validateur in champ_jauge_max.validators:
        if isinstance(validateur, MaxValueValidator):
            maximums_du_champ.append(validateur.limit_value)

    assert maximums_du_champ == [Event.JAUGE_MAXIMALE_POSSIBLE]


def test_assistant_refuse_une_jauge_plus_grande_que_la_limite():
    """
    L'assistant de creation refuse une jauge de 32768 et nomme la limite dans
    son message d'erreur.
    / The wizard rejects a 32768 gauge and names the limit in its error message.
    """
    donnees_du_formulaire = {
        "name": "Soirée test jauge",
        "datetime": "2030-11-25T20:00:00+01:00",
        "jauge_max": JAUGE_TROP_GRANDE,
    }
    serializer = WizardEventSerializer(data=donnees_du_formulaire)

    assert not serializer.is_valid()
    assert "jauge_max" in serializer.errors
    assert "32767" in str(serializer.errors["jauge_max"][0])


def test_assistant_accepte_une_jauge_egale_a_la_limite():
    """
    La limite elle-meme (32767) reste acceptee.
    / The limit itself (32767) is still accepted.
    """
    donnees_du_formulaire = {
        "name": "Soirée test jauge",
        "datetime": "2030-11-25T20:00:00+01:00",
        "jauge_max": Event.JAUGE_MAXIMALE_POSSIBLE,
    }
    serializer = WizardEventSerializer(data=donnees_du_formulaire)

    assert serializer.is_valid(), serializer.errors


def test_api_v2_refuse_une_capacite_plus_grande_que_la_limite():
    """
    L'API v2 refuse maximumAttendeeCapacity = 32768 avec une erreur de champ
    (donc une reponse 400), pas une erreur de base de donnees.
    / API v2 rejects maximumAttendeeCapacity = 32768 with a field error (a 400).
    """
    donnees_json = {
        "name": "Soirée test jauge API",
        "startDate": "2030-11-25T20:00:00+01:00",
        "maximumAttendeeCapacity": JAUGE_TROP_GRANDE,
    }
    serializer = EventCreateSerializer(data=donnees_json)

    assert not serializer.is_valid()
    assert "maximumAttendeeCapacity" in serializer.errors
    assert "32767" in str(serializer.errors["maximumAttendeeCapacity"][0])


def test_api_v2_refuse_une_capacite_negative():
    """
    La colonne n'accepte pas de valeur negative non plus (smallint POSITIF).
    / The column rejects negative values too (POSITIVE smallint).
    """
    donnees_json = {
        "name": "Soirée test jauge API",
        "startDate": "2030-11-25T20:00:00+01:00",
        "maximumAttendeeCapacity": -1,
    }
    serializer = EventCreateSerializer(data=donnees_json)

    assert not serializer.is_valid()
    assert "maximumAttendeeCapacity" in serializer.errors


@pytest.mark.parametrize(
    "offres_hors_bornes",
    [
        {"eligibleQuantity": {"maxValue": 32768}},
        {"eligibleQuantity": {"maxValue": -1}},
        {"eligibleQuantity": {"maxValue": "beaucoup"}},
        {"returnPolicy": {"merchantReturnDays": 32768}},
        {"returnPolicy": {"merchantReturnDays": -1}},
    ],
)
def test_api_v2_refuse_une_offre_hors_des_bornes_d_un_smallint(offres_hors_bornes):
    """
    maxValue (-> Event.max_per_user) et merchantReturnDays (-> Event.refund_deadline)
    vont dans des colonnes smallint positif : hors de 0..32767, erreur 400 sur « offers ».
    / Both values go to positive smallint columns: out of 0..32767 -> 400 on "offers".
    """
    donnees_json = {
        "name": "Soirée test offres API",
        "startDate": "2030-11-25T20:00:00+01:00",
        "offers": offres_hors_bornes,
    }
    serializer = EventCreateSerializer(data=donnees_json)

    assert not serializer.is_valid()
    assert "offers" in serializer.errors


def test_api_v2_accepte_une_offre_dans_les_bornes():
    """
    Les valeurs limites (0 et 32767) restent acceptees.
    / The boundary values (0 and 32767) are still accepted.
    """
    donnees_json = {
        "name": "Soirée test offres API",
        "startDate": "2030-11-25T20:00:00+01:00",
        "offers": {
            "eligibleQuantity": {"maxValue": 32767},
            "returnPolicy": {"merchantReturnDays": 0},
        },
    }
    serializer = EventCreateSerializer(data=donnees_json)

    assert serializer.is_valid(), serializer.errors
