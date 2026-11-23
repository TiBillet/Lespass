"""
API v2 : modifier un évènement (PATCH), et les deux corrections de la création (POST).
/ API v2: partially update an event (PATCH), and the two creation (POST) fixes.

LOCALISATION : tests/pytest/test_api_v2_event_patch.py

Code testé / Tested code :
- api_v2/views.py : EventViewSet.partial_update
- api_v2/serializers.py : EventPatchSerializer, EventCreateSerializer (doublon nom + date,
  nettoyage de la description), EventSchemaSerializer (blockedResource en lecture),
  PostalAddressAsSchemaSerializer (identifier)

Chaque test est marqué `django_db` : transaction annulée à la fin (clés comprises).
Les appels passent par le vrai routeur, avec `Authorization: Api-Key <clé>`.
/ Each test is rolled back; calls go through the real router with an API key.

Lancer / Run : make test ARGS="tests/pytest/test_api_v2_event_patch.py"
"""

import datetime
import io
from types import SimpleNamespace

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

from fabriques_panier import identifiant_unique

pytestmark = pytest.mark.django_db

HOTE_DU_LIEU = "lespass.tibillet.localhost"


def creer_une_cle(tenant, droit_event=True):
    """Une clé API du lieu, avec ou sans le droit « Events ». Rend la clé en clair."""
    from rest_framework_api_key.models import APIKey

    from BaseBillet.models import ExternalApiKey

    with tenant_context(tenant):
        cle_technique, cle_en_clair = APIKey.objects.create_key(
            name=f"event-patch-{identifiant_unique()}"
        )
        ExternalApiKey.objects.create(
            name=f"event-patch-{identifiant_unique()}",
            key=cle_technique,
            event=droit_event,
        )
    return cle_en_clair


class Api:
    """Un client de l'API sur le lieu, avec sa clé. / An API client on the venue, with its key."""

    def __init__(self, cle):
        self.client = APIClient()
        self.entetes = {
            "HTTP_AUTHORIZATION": f"Api-Key {cle}",
            "HTTP_HOST": HOTE_DU_LIEU,
        }

    def get(self, adresse):
        return self.client.get(f"/api/v2/{adresse}", **self.entetes)

    def post(self, adresse, corps):
        return self.client.post(
            f"/api/v2/{adresse}", corps, format="json", **self.entetes
        )

    def patch(self, adresse, corps):
        return self.client.patch(
            f"/api/v2/{adresse}", corps, format="json", **self.entetes
        )

    def patch_multipart(self, adresse, corps):
        return self.client.patch(
            f"/api/v2/{adresse}", corps, format="multipart", **self.entetes
        )


@pytest.fixture
def lieu(tenant):
    """Le lieu `lespass`, un évènement de test, et une API avec le droit « Events »."""
    from BaseBillet.models import Event

    with tenant_context(tenant):
        debut = timezone.now() + datetime.timedelta(days=30)
        evenement = Event.objects.create(
            name=f"Test PATCH {identifiant_unique()}",
            datetime=debut,
            end_datetime=debut + datetime.timedelta(hours=2),
            short_description="Description courte d'origine",
            long_description="<p>Description longue d'origine</p>",
        )
        yield SimpleNamespace(
            tenant=tenant,
            evenement=evenement,
            api=Api(creer_une_cle(tenant)),
        )


def relire(evenement):
    evenement.refresh_from_db()
    return evenement


def proprietes(representation):
    return {
        entree["name"]: entree["value"]
        for entree in representation.get("additionalProperty") or []
    }


def creer_une_salle(label):
    from booking.tests.test_booking_engine import (
        _make_calendar,
        _make_resource,
        _make_weekly_opening,
    )

    return _make_resource(label, _make_calendar(label), _make_weekly_opening(label))


def une_image_png():
    from PIL import Image

    fichier = io.BytesIO()
    Image.new("RGB", (40, 30), color=(200, 120, 40)).save(fichier, format="PNG")
    fichier.seek(0)
    fichier.name = "atelier.png"
    return fichier


# ---------------------------------------------------------------------------
# PATCH : champs modifiés / PATCH: updated fields
# ---------------------------------------------------------------------------


def test_le_patch_ne_modifie_que_les_champs_envoyes(lieu):
    reponse = lieu.api.patch(
        f"events/{lieu.evenement.uuid}/", {"name": "Nouveau titre"}
    )

    assert reponse.status_code == 200, reponse.content
    evenement = relire(lieu.evenement)
    assert evenement.name == "Nouveau titre"
    assert evenement.short_description == "Description courte d'origine"
    assert evenement.long_description == "<p>Description longue d'origine</p>"


def test_le_patch_accepte_le_slug_de_l_evenement(lieu):
    reponse = lieu.api.patch(
        f"events/{lieu.evenement.slug}/", {"maximumAttendeeCapacity": 12}
    )

    assert reponse.status_code == 200, reponse.content
    assert relire(lieu.evenement).jauge_max == 12


def test_le_patch_nettoie_la_description_longue(lieu):
    reponse = lieu.api.patch(
        f"events/{lieu.evenement.uuid}/",
        {
            "description": "<p>Atelier</p><script>alert(1)</script>",
        },
    )

    assert reponse.status_code == 200, reponse.content
    description = relire(lieu.evenement).long_description
    assert "<script>" not in description
    assert "Atelier" in description


def test_le_patch_vide_la_description_courte(lieu):
    reponse = lieu.api.patch(
        f"events/{lieu.evenement.uuid}/", {"disambiguatingDescription": ""}
    )

    assert reponse.status_code == 200, reponse.content
    assert relire(lieu.evenement).short_description == ""


def test_le_patch_remplace_tous_les_tags(lieu):
    lieu.api.patch(f"events/{lieu.evenement.uuid}/", {"keywords": ["ancien"]})

    reponse = lieu.api.patch(
        f"events/{lieu.evenement.uuid}/", {"keywords": ["atelier", "plantes"]}
    )

    assert reponse.status_code == 200, reponse.content
    noms_des_tags = sorted(tag.name for tag in relire(lieu.evenement).tag.all())
    assert noms_des_tags == ["atelier", "plantes"]


def test_le_patch_rend_l_evenement_non_federable(lieu):
    reponse = lieu.api.patch(
        f"events/{lieu.evenement.uuid}/",
        {
            "audience": {"@type": "Audience", "audienceType": "private"},
        },
    )

    assert reponse.status_code == 200, reponse.content
    assert relire(lieu.evenement).private is True


def test_le_patch_depublie_l_evenement(lieu):
    reponse = lieu.api.patch(
        f"events/{lieu.evenement.uuid}/",
        {
            "eventStatus": "https://schema.org/EventCancelled",
        },
    )

    assert reponse.status_code == 200, reponse.content
    assert relire(lieu.evenement).published is False


def test_le_patch_modifie_le_delai_de_remboursement(lieu):
    reponse = lieu.api.patch(
        f"events/{lieu.evenement.uuid}/",
        {
            "offers": {"returnPolicy": {"merchantReturnDays": 3}},
        },
    )

    assert reponse.status_code == 200, reponse.content
    assert relire(lieu.evenement).refund_deadline == 3


def test_le_patch_change_la_categorie_par_son_libelle(lieu):
    from BaseBillet.models import Event
    from api_v2.serializers import DISPLAY_TO_CATEGORY

    libelle_de_la_categorie_chantier = None
    for libelle, code in DISPLAY_TO_CATEGORY.items():
        if code == Event.CHANTIER:
            libelle_de_la_categorie_chantier = libelle

    reponse = lieu.api.patch(
        f"events/{lieu.evenement.uuid}/",
        {
            "additionalType": libelle_de_la_categorie_chantier,
        },
    )

    assert reponse.status_code == 200, reponse.content
    assert relire(lieu.evenement).categorie == Event.CHANTIER


def test_le_patch_pose_une_image_en_multipart(lieu):
    reponse = lieu.api.patch_multipart(
        f"events/{lieu.evenement.uuid}/", {"img": une_image_png()}
    )

    assert reponse.status_code == 200, reponse.content
    assert relire(lieu.evenement).img


# ---------------------------------------------------------------------------
# PATCH : ressource bloquée / PATCH: blocked resource
# ---------------------------------------------------------------------------


def test_le_patch_bloque_une_ressource_et_la_reponse_la_montre(lieu):
    with tenant_context(lieu.tenant):
        salle = creer_une_salle("api_v2_patch_bloque")

    reponse = lieu.api.patch(
        f"events/{lieu.evenement.uuid}/",
        {
            "additionalProperty": [{"name": "blockedResource", "value": salle.pk}],
        },
    )

    assert reponse.status_code == 200, reponse.content
    assert relire(lieu.evenement).ressource_bloquee_id == salle.pk
    assert proprietes(reponse.json())["blockedResource"] == salle.pk


def test_le_patch_libere_la_ressource_avec_null(lieu):
    with tenant_context(lieu.tenant):
        salle = creer_une_salle("api_v2_patch_libere")
        lieu.evenement.ressource_bloquee = salle
        lieu.evenement.save()

    reponse = lieu.api.patch(
        f"events/{lieu.evenement.uuid}/",
        {
            "additionalProperty": [{"name": "blockedResource", "value": None}],
        },
    )

    assert reponse.status_code == 200, reponse.content
    assert relire(lieu.evenement).ressource_bloquee_id is None


def test_le_patch_bloque_une_ressource_en_multipart(lieu):
    with tenant_context(lieu.tenant):
        salle = creer_une_salle("api_v2_patch_multipart")

    reponse = lieu.api.patch_multipart(
        f"events/{lieu.evenement.uuid}/",
        {
            "additionalProperty[0].name": "blockedResource",
            "additionalProperty[0].value": str(salle.pk),
        },
    )

    assert reponse.status_code == 200, reponse.content
    assert relire(lieu.evenement).ressource_bloquee_id == salle.pk


# ---------------------------------------------------------------------------
# PATCH : refus / PATCH: rejections
# ---------------------------------------------------------------------------


def test_le_patch_refuse_une_fin_avant_le_debut_deja_en_base(lieu):
    fin_avant_le_debut = lieu.evenement.datetime - datetime.timedelta(hours=1)

    reponse = lieu.api.patch(
        f"events/{lieu.evenement.uuid}/", {"endDate": fin_avant_le_debut.isoformat()}
    )

    assert reponse.status_code == 400
    assert "endDate" in reponse.json()


def test_le_patch_refuse_de_retirer_la_fin_d_un_evenement_qui_bloque_une_ressource(
    lieu,
):
    with tenant_context(lieu.tenant):
        salle = creer_une_salle("api_v2_patch_sans_fin")
        lieu.evenement.ressource_bloquee = salle
        lieu.evenement.save()

    reponse = lieu.api.patch(f"events/{lieu.evenement.uuid}/", {"endDate": None})

    assert reponse.status_code == 400
    assert "endDate" in reponse.json()


def test_le_patch_refuse_une_ressource_introuvable(lieu):
    reponse = lieu.api.patch(
        f"events/{lieu.evenement.uuid}/",
        {
            "additionalProperty": [{"name": "blockedResource", "value": 999999999}],
        },
    )

    assert reponse.status_code == 400
    assert "additionalProperty" in reponse.json()


def test_le_patch_refuse_un_nom_et_une_date_deja_pris(lieu):
    from BaseBillet.models import Event

    with tenant_context(lieu.tenant):
        autre_evenement = Event.objects.create(
            name=f"Autre {identifiant_unique()}",
            datetime=lieu.evenement.datetime,
        )

    reponse = lieu.api.patch(
        f"events/{lieu.evenement.uuid}/", {"name": autre_evenement.name}
    )

    assert reponse.status_code == 400
    assert "name" in reponse.json()


def test_le_patch_refuse_une_propriete_inconnue(lieu):
    reponse = lieu.api.patch(
        f"events/{lieu.evenement.uuid}/",
        {
            "additionalProperty": [{"name": "jaugeSecrete", "value": 3}],
        },
    )

    assert reponse.status_code == 400
    assert "additionalProperty" in reponse.json()


def test_le_patch_refuse_une_categorie_inconnue(lieu):
    reponse = lieu.api.patch(
        f"events/{lieu.evenement.uuid}/", {"additionalType": "Atelier imaginaire"}
    )

    assert reponse.status_code == 400
    assert "additionalType" in reponse.json()


def test_le_patch_refuse_audience_envoyee_en_multipart(lieu):
    reponse = lieu.api.patch_multipart(
        f"events/{lieu.evenement.uuid}/",
        {
            "audience.audienceType": "private",
        },
    )

    assert reponse.status_code == 400
    assert "audience" in reponse.json()
    assert relire(lieu.evenement).private is False


def test_le_patch_sans_le_droit_event_recoit_403(lieu):
    api_sans_droit = Api(creer_une_cle(lieu.tenant, droit_event=False))

    reponse = api_sans_droit.patch(
        f"events/{lieu.evenement.uuid}/", {"name": "Interdit"}
    )

    assert reponse.status_code == 403
    assert relire(lieu.evenement).name != "Interdit"


# ---------------------------------------------------------------------------
# POST : corrections de la création / POST: creation fixes
# ---------------------------------------------------------------------------


def test_le_post_refuse_un_nom_et_une_date_deja_pris_par_une_400(lieu):
    reponse = lieu.api.post(
        "events/",
        {
            "@context": "https://schema.org",
            "@type": "Event",
            "name": lieu.evenement.name,
            "startDate": lieu.evenement.datetime.isoformat(),
        },
    )

    assert reponse.status_code == 400
    assert "name" in reponse.json()


def test_le_post_nettoie_la_description_longue(lieu):
    reponse = lieu.api.post(
        "events/",
        {
            "@context": "https://schema.org",
            "@type": "Event",
            "name": f"Test POST {identifiant_unique()}",
            "startDate": (timezone.now() + datetime.timedelta(days=40)).isoformat(),
            "description": "<p>Concert</p><script>alert(1)</script>",
        },
    )

    assert reponse.status_code == 201, reponse.content
    assert "<script>" not in reponse.json()["description"]


# ---------------------------------------------------------------------------
# Adresses postales / Postal addresses
# ---------------------------------------------------------------------------


def test_la_liste_des_adresses_donne_l_identifiant_attendu_par_link_address(lieu):
    from BaseBillet.models import PostalAddress

    with tenant_context(lieu.tenant):
        adresse = PostalAddress.objects.create(
            name=f"Adresse {identifiant_unique()}",
            street_address="1 rue du Test",
            address_locality="Testville",
            postal_code="00000",
            address_country="France",
        )

    reponse = lieu.api.get("postal-addresses/")

    assert reponse.status_code == 200, reponse.content
    identifiants = [entree.get("identifier") for entree in reponse.json()["results"]]
    assert adresse.pk in identifiants
