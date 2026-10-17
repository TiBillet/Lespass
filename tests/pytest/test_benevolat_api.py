"""
Tests de l'API v2 du bénévolat (version allégée) : tâches, plannings, besoins, inscriptions.
/ Volunteering API v2 tests (light version).

LOCALISATION : tests/pytest/test_benevolat_api.py

Code testé / Tested code : api_v2/views_benevolat.py, api_v2/serializers_benevolat.py,
BaseBillet/models.py (ExternalApiKey.volunteering)
Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§6 bis, D24)

Chaque test est marqué `django_db` : transaction annulée à la fin (clés comprises).
Les appels passent par le vrai routeur, avec `Authorization: Api-Key <clé>`.
/ Each test is rolled back; calls go through the real router with an API key.

Lancer / Run : make test ARGS="tests/pytest/test_benevolat_api.py"
"""

import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

from fabriques_panier import creer_utilisateur, identifiant_unique

pytestmark = pytest.mark.django_db

ROUTES = ["volunteer-tasks", "volunteer-plannings", "volunteer-needs", "volunteer-signups"]


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    from django.utils import translation

    yield
    translation.deactivate()


def creer_une_cle(tenant, volunteering=True, user=None):
    """Une clé API du lieu, avec ou sans le droit « Bénévolat ». Rend la clé en clair."""
    from rest_framework_api_key.models import APIKey

    from BaseBillet.models import ExternalApiKey

    with tenant_context(tenant):
        cle_technique, cle_en_clair = APIKey.objects.create_key(name=f"benevolat-{identifiant_unique()}")
        ExternalApiKey.objects.create(
            name=f"benevolat-{identifiant_unique()}", key=cle_technique, volunteering=volunteering, user=user,
        )
    return cle_en_clair


class Api:
    """Un client de l'API sur un lieu, avec sa clé. / An API client on a venue, with its key."""

    def __init__(self, cle, hote="lespass.tibillet.localhost"):
        self.client = APIClient()
        self.entetes = {"HTTP_AUTHORIZATION": f"Api-Key {cle}", "HTTP_HOST": hote}

    def get(self, adresse):
        return self.client.get(f"/api/v2/{adresse}", **self.entetes)

    def post(self, adresse, corps):
        return self.client.post(f"/api/v2/{adresse}", corps, format="json", **self.entetes)

    def patch(self, adresse, corps):
        return self.client.patch(f"/api/v2/{adresse}", corps, format="json", **self.entetes)

    def delete(self, adresse):
        return self.client.delete(f"/api/v2/{adresse}", **self.entetes)


@pytest.fixture
def lieu(tenant):
    """Le lieu `lespass`, sa date du jour (fuseau du lieu), son fuseau, et une API avec le droit."""
    from BaseBillet.models import Configuration

    with tenant_context(tenant):
        fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        yield SimpleNamespace(
            tenant=tenant,
            fuseau=fuseau_du_lieu,
            aujourd_hui=timezone.now().astimezone(fuseau_du_lieu).date(),
            api=Api(creer_une_cle(tenant)),
        )


def proprietes(representation):
    return {entree["name"]: entree["value"] for entree in representation["additionalProperty"]}


def creer_planning_et_tache(lieu, publie=True):
    """Par l'API : une tâche et un planning. Rend (uuid de la tâche, uuid du planning, slug)."""
    tache = lieu.api.post("volunteer-tasks/", {"name": "Tenir le bar", "description": "Au comptoir"})
    assert tache.status_code == 201, tache.content
    slug = f"api-benevolat-{identifiant_unique()}"
    planning = lieu.api.post("volunteer-plannings/", {
        "name": "Bar : novembre",
        "additionalProperty": [
            {"name": "slug", "value": slug},
            {"name": "published", "value": publie},
        ],
    })
    assert planning.status_code == 201, planning.content
    return tache.json()["identifier"], planning.json()["identifier"], slug


def creer_un_besoin(lieu, uuid_tache, uuid_planning, debut, fin=None, nombre=2):
    corps = {
        "superEvent": {"identifier": uuid_planning},
        "about": uuid_tache,
        "startDate": debut,
        "additionalProperty": [{"name": "nombreSouhaite", "value": nombre}],
    }
    if fin is not None:
        corps["endDate"] = fin
    return lieu.api.post("volunteer-needs/", corps)


# ---------------------------------------------------------------------------
# Droit de la clé / Key right
# ---------------------------------------------------------------------------

def test_le_droit_volunteering_ouvre_les_quatre_basenames():
    from BaseBillet.models import ExternalApiKey

    avec = ExternalApiKey(name="avec", volunteering=True).api_permissions()
    sans = ExternalApiKey(name="sans", volunteering=False).api_permissions()
    for basename in ["volunteertask", "volunteerplanning", "volunteerneed", "volunteersignup"]:
        assert avec[basename] is True
        assert sans[basename] is False


def test_une_cle_sans_le_droit_recoit_403_sur_les_quatre_routes(tenant):
    api_sans_droit = Api(creer_une_cle(tenant, volunteering=False))
    for route in ROUTES:
        assert api_sans_droit.get(f"{route}/").status_code == 403, route
        assert api_sans_droit.post(f"{route}/", {}).status_code == 403, route


# ---------------------------------------------------------------------------
# Tâches / Tasks
# ---------------------------------------------------------------------------

def test_crud_des_taches_et_409_si_la_tache_sert(lieu):
    uuid_tache, uuid_planning, _slug = creer_planning_et_tache(lieu)

    lue = lieu.api.get(f"volunteer-tasks/{uuid_tache}/")
    assert lue.status_code == 200
    assert lue.json()["@type"] == "DefinedTerm"
    assert lue.json()["name"] == "Tenir le bar"

    modifiee = lieu.api.patch(f"volunteer-tasks/{uuid_tache}/", {"name": "Tenir le bar (soir)"})
    assert modifiee.json()["name"] == "Tenir le bar (soir)"

    identifiants = [tache["identifier"] for tache in lieu.api.get("volunteer-tasks/").json()["results"]]
    assert uuid_tache in identifiants

    assert creer_un_besoin(lieu, uuid_tache, uuid_planning, (lieu.aujourd_hui + datetime.timedelta(days=3)).isoformat()).status_code == 201
    refus = lieu.api.delete(f"volunteer-tasks/{uuid_tache}/")
    assert refus.status_code == 409
    assert "1 besoins" in refus.json()["detail"]

    tache_libre = lieu.api.post("volunteer-tasks/", {"name": "Ménage"}).json()["identifier"]
    assert lieu.api.delete(f"volunteer-tasks/{tache_libre}/").status_code == 204
    assert lieu.api.get(f"volunteer-tasks/{tache_libre}/").status_code == 404


# ---------------------------------------------------------------------------
# Plannings
# ---------------------------------------------------------------------------

def test_planning_lu_par_uuid_et_par_slug_avec_ses_besoins(lieu):
    uuid_tache, uuid_planning, slug = creer_planning_et_tache(lieu)
    creer_un_besoin(lieu, uuid_tache, uuid_planning, (lieu.aujourd_hui + datetime.timedelta(days=3)).isoformat())

    par_uuid = lieu.api.get(f"volunteer-plannings/{uuid_planning}/")
    par_slug = lieu.api.get(f"volunteer-plannings/{slug}/")

    assert par_uuid.status_code == 200 and par_slug.status_code == 200
    assert par_uuid.json()["identifier"] == par_slug.json()["identifier"] == uuid_planning
    assert par_uuid.json()["@type"] == "EventSeries"
    assert par_uuid.json()["url"] == f"/booking/benevolat/{slug}/"
    assert len(par_uuid.json()["subEvent"]) == 1
    assert proprietes(par_uuid.json())["placesSouhaitees"] == 2
    # La liste ne porte pas les besoins / The list carries no subEvent
    plannings = lieu.api.get("volunteer-plannings/").json()["results"]
    assert "subEvent" not in [planning for planning in plannings if planning["identifier"] == uuid_planning][0]


def test_planning_patch_puis_delete(lieu):
    _uuid_tache, uuid_planning, _slug = creer_planning_et_tache(lieu, publie=False)

    modifie = lieu.api.patch(f"volunteer-plannings/{uuid_planning}/", {
        "additionalProperty": [{"name": "published", "value": True}, {"name": "delaiDesinscriptionHeures", "value": 48}],
    })
    assert modifie.status_code == 200, modifie.content
    assert proprietes(modifie.json())["published"] is True
    assert proprietes(modifie.json())["delaiDesinscriptionHeures"] == 48

    assert lieu.api.delete(f"volunteer-plannings/{uuid_planning}/").status_code == 204
    assert lieu.api.get(f"volunteer-plannings/{uuid_planning}/").status_code == 404


def test_planning_sans_slug_ou_slug_reserve_refuse(lieu):
    sans_slug = lieu.api.post("volunteer-plannings/", {"name": "X"})
    reserve = lieu.api.post("volunteer-plannings/", {
        "name": "X", "additionalProperty": [{"name": "slug", "value": "desistement"}],
    })

    assert sans_slug.status_code == 400
    assert "slug" in sans_slug.json()
    assert reserve.status_code == 400


def test_adhesions_et_calendrier_sont_en_lecture_seule(lieu):
    """API allégée : envoyer requiredMembershipPlans ou closingCalendar ne change rien."""
    from booking.models import PlanningBenevole

    _uuid_tache, uuid_planning, _slug = creer_planning_et_tache(lieu)
    lieu.api.patch(f"volunteer-plannings/{uuid_planning}/", {
        "additionalProperty": [
            {"name": "requiredMembershipPlans", "value": ["00000000-0000-0000-0000-000000000000"]},
            {"name": "closingCalendar", "value": 1},
        ],
    })

    planning = PlanningBenevole.objects.get(pk=uuid_planning)
    assert planning.calendrier_id is None
    assert planning.adhesions_requises.count() == 0


# ---------------------------------------------------------------------------
# Besoins : les dates / Needs: dates
# ---------------------------------------------------------------------------

def test_date_seule_donne_une_journee(lieu):
    uuid_tache, uuid_planning, _slug = creer_planning_et_tache(lieu)
    jour = (lieu.aujourd_hui + datetime.timedelta(days=4)).isoformat()

    reponse = creer_un_besoin(lieu, uuid_tache, uuid_planning, jour)

    assert reponse.status_code == 201, reponse.content
    assert reponse.json()["startDate"] == jour
    assert "endDate" not in reponse.json()
    assert reponse.json()["additionalType"] == "Volunteering"


def test_heure_sans_decalage_est_l_heure_locale_et_fin_a_minuit_le_lendemain(lieu):
    from booking.models import BesoinBenevole

    uuid_tache, uuid_planning, _slug = creer_planning_et_tache(lieu)
    jour = lieu.aujourd_hui + datetime.timedelta(days=4)
    lendemain = jour + datetime.timedelta(days=1)

    reponse = creer_un_besoin(lieu, uuid_tache, uuid_planning, f"{jour}T21:00:00", f"{lendemain}T00:00:00")

    assert reponse.status_code == 201, reponse.content
    besoin = BesoinBenevole.objects.get(pk=reponse.json()["identifier"])
    assert (besoin.date, besoin.heure_debut, besoin.heure_fin) == (jour, datetime.time(21), datetime.time(0))
    debut_attendu = datetime.datetime.combine(jour, datetime.time(21), tzinfo=lieu.fuseau)
    assert reponse.json()["startDate"] == debut_attendu.isoformat()


def test_heure_avec_decalage_est_convertie_dans_le_fuseau_du_lieu(lieu):
    from booking.models import BesoinBenevole

    uuid_tache, uuid_planning, _slug = creer_planning_et_tache(lieu)
    jour = lieu.aujourd_hui + datetime.timedelta(days=4)
    debut_utc = datetime.datetime.combine(jour, datetime.time(16), tzinfo=datetime.timezone.utc)
    fin_utc = debut_utc + datetime.timedelta(hours=3)

    reponse = creer_un_besoin(lieu, uuid_tache, uuid_planning, debut_utc.isoformat(), fin_utc.isoformat())

    assert reponse.status_code == 201, reponse.content
    besoin = BesoinBenevole.objects.get(pk=reponse.json()["identifier"])
    debut_local = debut_utc.astimezone(lieu.fuseau)
    assert besoin.heure_debut == debut_local.time().replace(tzinfo=None)


@pytest.mark.parametrize("decalage_de_fin, heure_de_fin", [
    (2, "20:00:00"),   # J+2 : plus de 24 h / more than 24 h
    (0, "18:00:00"),   # fin = début / end == start
    (0, "17:00:00"),   # fin avant début le même jour / end before start, same day
    (1, "19:00:00"),   # lendemain mais plus de 24 h / next day but over 24 h
])
def test_fins_impossibles_refusees(lieu, decalage_de_fin, heure_de_fin):
    uuid_tache, uuid_planning, _slug = creer_planning_et_tache(lieu)
    jour = lieu.aujourd_hui + datetime.timedelta(days=4)
    fin = jour + datetime.timedelta(days=decalage_de_fin)

    reponse = creer_un_besoin(lieu, uuid_tache, uuid_planning, f"{jour}T18:00:00", f"{fin}T{heure_de_fin}")

    assert reponse.status_code == 400


def test_heure_sans_fin_ou_journee_avec_fin_refusees(lieu):
    uuid_tache, uuid_planning, _slug = creer_planning_et_tache(lieu)
    jour = lieu.aujourd_hui + datetime.timedelta(days=4)

    sans_fin = creer_un_besoin(lieu, uuid_tache, uuid_planning, f"{jour}T18:00:00")
    assert sans_fin.status_code == 400
    assert "obligatoire" in str(sans_fin.json()["endDate"])
    assert creer_un_besoin(lieu, uuid_tache, uuid_planning, jour.isoformat(), f"{jour}T20:00:00").status_code == 400


def test_un_besoin_un_jour_ferme_est_accepte_avec_fermeture(lieu):
    from booking.models import Calendar, ClosedPeriod, PlanningBenevole

    uuid_tache, uuid_planning, _slug = creer_planning_et_tache(lieu)
    jour = lieu.aujourd_hui + datetime.timedelta(days=6)
    calendrier = Calendar.objects.create(name=f"TEST_benevolat api {identifiant_unique()}")
    ClosedPeriod.objects.create(calendar=calendrier, label="Inventaire", start_date=jour, end_date=jour)
    PlanningBenevole.objects.filter(pk=uuid_planning).update(calendrier=calendrier)

    reponse = creer_un_besoin(lieu, uuid_tache, uuid_planning, jour.isoformat())

    assert reponse.status_code == 201
    assert proprietes(reponse.json())["fermeture"] == "Inventaire"


def test_filtres_de_la_liste_des_besoins_et_patch(lieu):
    uuid_tache, uuid_planning, _slug = creer_planning_et_tache(lieu)
    jour_1 = lieu.aujourd_hui + datetime.timedelta(days=3)
    jour_2 = lieu.aujourd_hui + datetime.timedelta(days=10)
    besoin_1 = creer_un_besoin(lieu, uuid_tache, uuid_planning, jour_1.isoformat()).json()["identifier"]
    besoin_2 = creer_un_besoin(lieu, uuid_tache, uuid_planning, jour_2.isoformat()).json()["identifier"]

    du_planning = lieu.api.get(f"volunteer-needs/?planning={uuid_planning}").json()["results"]
    jusqu_au_jour_1 = lieu.api.get(f"volunteer-needs/?planning={uuid_planning}&dateTo={jour_1}").json()["results"]

    assert {besoin["identifier"] for besoin in du_planning} == {besoin_1, besoin_2}
    assert [besoin["identifier"] for besoin in jusqu_au_jour_1] == [besoin_1]

    modifie = lieu.api.patch(f"volunteer-needs/{besoin_2}/", {"additionalProperty": [{"name": "nombreSouhaite", "value": 5}]})
    assert proprietes(modifie.json())["nombreSouhaite"] == 5
    assert lieu.api.delete(f"volunteer-needs/{besoin_2}/").status_code == 204


# ---------------------------------------------------------------------------
# Inscriptions / Sign-ups
# ---------------------------------------------------------------------------

def test_inscrire_rend_201_puis_200_sans_second_mail(lieu, django_capture_on_commit_callbacks):
    from booking.models import InscriptionBenevole

    uuid_tache, uuid_planning, _slug = creer_planning_et_tache(lieu)
    besoin = creer_un_besoin(lieu, uuid_tache, uuid_planning, (lieu.aujourd_hui + datetime.timedelta(days=3)).isoformat()).json()["identifier"]
    email = f"camille.{identifiant_unique()}@mock.test"
    corps = {"object": {"identifier": besoin}, "agent": {"email": email, "givenName": "Camille", "familyName": "Martin"}}

    with patch("api_v2.views_benevolat.envoyer_confirmation_benevole") as tache_de_confirmation:
        with django_capture_on_commit_callbacks(execute=True):
            premiere = lieu.api.post("volunteer-signups/", corps)
        with django_capture_on_commit_callbacks(execute=True):
            seconde = lieu.api.post("volunteer-signups/", corps)

    assert premiere.status_code == 201, premiere.content
    assert seconde.status_code == 200
    assert premiere.json()["@type"] == "RsvpAction"
    assert premiere.json()["agent"]["familyName"] == "Martin"
    assert InscriptionBenevole.objects.filter(besoin_id=besoin, user__email=email).count() == 1
    tache_de_confirmation.delay.assert_called_once_with(premiere.json()["identifier"], par_l_equipe=True)


def test_inscrit_par_est_le_compte_de_la_cle(tenant, lieu):
    from booking.models import InscriptionBenevole

    compte_de_la_cle = creer_utilisateur()
    api_avec_compte = Api(creer_une_cle(tenant, user=compte_de_la_cle))
    uuid_tache, uuid_planning, _slug = creer_planning_et_tache(lieu)
    besoin = creer_un_besoin(lieu, uuid_tache, uuid_planning, (lieu.aujourd_hui + datetime.timedelta(days=3)).isoformat()).json()["identifier"]

    with patch("api_v2.views_benevolat.envoyer_confirmation_benevole"):
        reponse = api_avec_compte.post("volunteer-signups/", {
            "object": {"identifier": besoin},
            "agent": {"email": f"x.{identifiant_unique()}@mock.test", "givenName": "X", "familyName": "Y"},
        })

    assert reponse.status_code == 201, reponse.content
    assert InscriptionBenevole.objects.get(pk=reponse.json()["identifier"]).inscrit_par == compte_de_la_cle
    assert proprietes(reponse.json())["inscritPar"] == compte_de_la_cle.email


def test_compte_sans_nom_et_familyname_absent_rend_400_sans_rien_creer(lieu):
    from AuthBillet.models import TibilletUser

    uuid_tache, uuid_planning, _slug = creer_planning_et_tache(lieu)
    besoin = creer_un_besoin(lieu, uuid_tache, uuid_planning, (lieu.aujourd_hui + datetime.timedelta(days=3)).isoformat()).json()["identifier"]
    email = f"sansnom.{identifiant_unique()}@mock.test"

    reponse = lieu.api.post("volunteer-signups/", {"object": {"identifier": besoin}, "agent": {"email": email, "givenName": "Nina"}})

    assert reponse.status_code == 400
    assert not TibilletUser.objects.filter(email=email).exists()


def test_besoin_passe_ou_planning_non_publie_rend_400(lieu):
    from booking.models import BesoinBenevole, TacheBenevole

    uuid_tache, uuid_planning, _slug = creer_planning_et_tache(lieu)
    _t, uuid_planning_brouillon, _s = creer_planning_et_tache(lieu, publie=False)
    besoin_passe = BesoinBenevole.objects.create(
        planning_id=uuid_planning, tache=TacheBenevole.objects.get(pk=uuid_tache),
        date=lieu.aujourd_hui - datetime.timedelta(days=2),
    )
    besoin_brouillon = creer_un_besoin(lieu, uuid_tache, uuid_planning_brouillon, (lieu.aujourd_hui + datetime.timedelta(days=3)).isoformat()).json()["identifier"]
    agent = {"email": f"a.{identifiant_unique()}@mock.test", "givenName": "A", "familyName": "B"}

    assert lieu.api.post("volunteer-signups/", {"object": {"identifier": str(besoin_passe.pk)}, "agent": agent}).status_code == 400
    assert lieu.api.post("volunteer-signups/", {"object": {"identifier": besoin_brouillon}, "agent": agent}).status_code == 400


def test_delete_d_une_inscription_sans_mail_et_filtre_par_besoin(lieu, django_capture_on_commit_callbacks):
    from booking.models import InscriptionBenevole

    uuid_tache, uuid_planning, _slug = creer_planning_et_tache(lieu)
    besoin = creer_un_besoin(lieu, uuid_tache, uuid_planning, (lieu.aujourd_hui + datetime.timedelta(days=3)).isoformat()).json()["identifier"]
    with patch("api_v2.views_benevolat.envoyer_confirmation_benevole"):
        inscription = lieu.api.post("volunteer-signups/", {
            "object": {"identifier": besoin},
            "agent": {"email": f"d.{identifiant_unique()}@mock.test", "givenName": "D", "familyName": "E"},
        }).json()["identifier"]

    du_besoin = lieu.api.get(f"volunteer-signups/?need={besoin}").json()["results"]
    assert [entree["identifier"] for entree in du_besoin] == [inscription]

    with patch("booking.tasks.prevenir_l_equipe_d_un_desistement") as alerte_equipe:
        with django_capture_on_commit_callbacks(execute=True):
            assert lieu.api.delete(f"volunteer-signups/{inscription}/").status_code == 204
    alerte_equipe.delay.assert_not_called()
    assert not InscriptionBenevole.objects.filter(pk=inscription).exists()


# ---------------------------------------------------------------------------
# Isolation entre lieux / Tenant isolation
# ---------------------------------------------------------------------------

def test_la_cle_d_un_autre_lieu_ne_voit_pas_le_planning(lieu):
    from Customers.models import Client

    _uuid_tache, uuid_planning, slug = creer_planning_et_tache(lieu)
    autre_lieu = Client.objects.exclude(schema_name__in=["lespass", "public"]).exclude(
        categorie=Client.WAITING_CONFIG,
    ).order_by("schema_name").first()
    assert autre_lieu is not None, "Il faut un second lieu pour ce test"
    api_de_l_autre_lieu = Api(creer_une_cle(autre_lieu), hote=f"{autre_lieu.schema_name}.tibillet.localhost")

    assert api_de_l_autre_lieu.get(f"volunteer-plannings/{uuid_planning}/").status_code == 404
    assert api_de_l_autre_lieu.get(f"volunteer-plannings/{slug}/").status_code == 404


# ---------------------------------------------------------------------------
# Relecture du 2026-10-16 / 2026-10-16 review
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("debut, fin", [("2030-02-30", None), ("2030-02-30T10:00:00", "2030-02-30T12:00:00")])
def test_une_date_impossible_rend_400(lieu, debut, fin):
    uuid_tache, uuid_planning, _slug = creer_planning_et_tache(lieu)

    assert creer_un_besoin(lieu, uuid_tache, uuid_planning, debut, fin).status_code == 400


def test_un_nom_de_tache_sur_deux_lignes_est_refuse(lieu):
    assert lieu.api.post("volunteer-tasks/", {"name": "Bar\nCc: x@y.z"}).status_code == 400


# ---------------------------------------------------------------------------
# Planning hebdomadaire (§11.2) / Weekly planning
# ---------------------------------------------------------------------------

def test_un_besoin_cree_ou_modifie_par_l_api_sur_un_planning_hebdomadaire_est_manuel(lieu):
    """
    POST sur un planning hebdomadaire : un besoin manuel (sans ligne de semaine type).
    PATCH d'un besoin créé par la semaine type : il s'en détache (exception manuelle).
    / POST gives a manual need; PATCH detaches a template-week need.
    """
    from booking.benevolat import creer_les_besoins_de_la_semaine_type
    from booking.models import BesoinBenevole, LigneDeSemaineType, PlanningBenevole

    uuid_tache, uuid_planning, _slug = creer_planning_et_tache(lieu)
    planning = PlanningBenevole.objects.get(pk=uuid_planning)
    planning.type_de_planning = PlanningBenevole.HEBDOMADAIRE
    planning.date_de_debut = lieu.aujourd_hui
    planning.horizon_en_semaines = 1
    planning.save()
    LigneDeSemaineType.objects.create(
        planning=planning, jour_de_la_semaine=lieu.aujourd_hui.weekday(), tache_id=uuid_tache,
    )
    creer_les_besoins_de_la_semaine_type(planning)
    besoin_de_la_semaine_type = planning.besoins.get(date=lieu.aujourd_hui)

    reponse = creer_un_besoin(lieu, uuid_tache, uuid_planning, (lieu.aujourd_hui + datetime.timedelta(days=2)).isoformat())
    modifie = lieu.api.patch(
        f"volunteer-needs/{besoin_de_la_semaine_type.pk}/",
        {"additionalProperty": [{"name": "nombreSouhaite", "value": 5}]},
    )

    assert reponse.status_code == 201, reponse.content
    assert BesoinBenevole.objects.get(pk=reponse.json()["identifier"]).ligne_de_semaine_type_id is None
    assert modifie.status_code == 200, modifie.content
    besoin_de_la_semaine_type.refresh_from_db()
    assert besoin_de_la_semaine_type.ligne_de_semaine_type_id is None
