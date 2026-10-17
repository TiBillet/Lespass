"""
Tests de la semaine type des plannings hebdomadaires de bénévoles, et de la page
« Besoins » de l'admin.
/ Tests of the weekly plannings' template week, and of the admin "Needs" page.

LOCALISATION : booking/tests/test_benevolat_semaine_type.py

Code testé / Tested code : booking/benevolat.py (besoins_de_la_semaine_type,
creer_les_besoins_de_la_semaine_type, appliquer_la_semaine_type_modifiee),
booking/models.py (PlanningBenevole.clean, LigneDeSemaineType, BesoinBenevole.save),
booking/tasks.py (creer_les_besoins_des_semaines_types),
Administration/admin/benevolat.py (PlanningBenevoleAdmin, BesoinBenevoleAdmin)
Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§11.2 à §11.4, D29 à D34)

Les tests du calcul n'ouvrent pas la base. Les autres travaillent sur la base de dev
(pas de transaction annulée dans booking/tests) : leurs données portent TEST_PREFIX et
sont supprimées à la fin du module.
/ Pure tests don't touch the DB; the others clean up their TEST_PREFIX data.

Lancement / Run:
    docker exec -w /DjangoFiles lespass_django poetry run pytest booking/tests/test_benevolat_semaine_type.py -v
"""
import datetime
import threading
import uuid
import zoneinfo
from types import SimpleNamespace
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django_tenants.utils import schema_context

TEST_PREFIX = '[test_booking_models]'
TENANT_SCHEMA = 'lespass'

LUNDI = datetime.date(2031, 10, 20)
VENDREDI = 4
SAMEDI = 5


@pytest.fixture(scope="module", autouse=True)
def nettoyer_la_semaine_type():
    """
    Supprime les plannings et tâches de test après le module. Lignes, besoins et
    inscriptions partent avec leur planning (CASCADE).
    / Deletes test plannings and tasks after the module.
    """
    yield
    from booking.models import PlanningBenevole, TacheBenevole

    with schema_context(TENANT_SCHEMA):
        PlanningBenevole.objects.filter(name__startswith=TEST_PREFIX).delete()
        TacheBenevole.objects.filter(name__startswith=TEST_PREFIX).delete()


def fausse_ligne(jour_de_la_semaine, heure_debut=None, heure_fin=None, tache_id="bar", nombre_souhaite=1):
    """Une ligne sans base : seulement ce que lit besoins_de_la_semaine_type."""
    return SimpleNamespace(
        jour_de_la_semaine=jour_de_la_semaine, tache_id=tache_id,
        heure_debut=heure_debut, heure_fin=heure_fin, nombre_souhaite=nombre_souhaite,
    )


def fausse_fermeture(debut, fin, label=""):
    return SimpleNamespace(start_date=debut, end_date=fin, label=label)


def dates(copies):
    return sorted(copie["date"] for copie in copies)


# ---------------------------------------------------------------------------
# Calcul pur / Pure computation
# ---------------------------------------------------------------------------

def test_un_mois_de_vendredis_et_samedis():
    from booking.benevolat import besoins_de_la_semaine_type

    lignes = [fausse_ligne(VENDREDI, datetime.time(18), datetime.time(21)), fausse_ligne(SAMEDI)]

    calcul = besoins_de_la_semaine_type(lignes, LUNDI, LUNDI + datetime.timedelta(days=27), [], set())

    attendu = []
    for semaine in range(4):
        attendu.append(LUNDI + datetime.timedelta(days=7 * semaine + VENDREDI))
        attendu.append(LUNDI + datetime.timedelta(days=7 * semaine + SAMEDI))
    assert dates(calcul["a_creer"]) == sorted(attendu)
    for copie in calcul["a_creer"]:
        assert copie["date"].weekday() == copie["ligne"].jour_de_la_semaine


def test_les_bornes_sont_comprises():
    from booking.benevolat import besoins_de_la_semaine_type

    calcul = besoins_de_la_semaine_type([fausse_ligne(0)], LUNDI, LUNDI + datetime.timedelta(days=7), [], set())

    assert dates(calcul["a_creer"]) == [LUNDI, LUNDI + datetime.timedelta(days=7)]


def test_un_jour_ferme_est_saute():
    from booking.benevolat import besoins_de_la_semaine_type

    samedi_ferme = LUNDI + datetime.timedelta(days=SAMEDI)
    calcul = besoins_de_la_semaine_type(
        [fausse_ligne(SAMEDI)], LUNDI, LUNDI + datetime.timedelta(days=13),
        [fausse_fermeture(samedi_ferme, samedi_ferme)], set(),
    )

    assert dates(calcul["a_creer"]) == [samedi_ferme + datetime.timedelta(days=7)]
    assert dates(calcul["sautes"]) == [samedi_ferme]


def test_un_besoin_deja_present_est_ignore():
    from booking.benevolat import besoins_de_la_semaine_type, cle_d_un_besoin

    vendredi = LUNDI + datetime.timedelta(days=VENDREDI)
    ligne = fausse_ligne(VENDREDI, datetime.time(18), datetime.time(21))
    deja_la = {cle_d_un_besoin("bar", vendredi, datetime.time(18), datetime.time(21))}

    calcul = besoins_de_la_semaine_type([ligne], LUNDI, LUNDI + datetime.timedelta(days=6), [], deja_la)

    assert calcul["a_creer"] == []
    assert dates(calcul["ignores"]) == [vendredi]


def test_une_ligne_de_nuit_garde_ses_heures():
    """21:00 → 00:00 : le besoin est créé le jour de la ligne, avec ses deux heures."""
    from booking.benevolat import besoins_de_la_semaine_type

    ligne = fausse_ligne(VENDREDI, datetime.time(21), datetime.time(0))

    calcul = besoins_de_la_semaine_type([ligne], LUNDI, LUNDI + datetime.timedelta(days=6), [], set())

    assert dates(calcul["a_creer"]) == [LUNDI + datetime.timedelta(days=VENDREDI)]
    assert calcul["a_creer"][0]["ligne"].heure_fin == datetime.time(0)


def test_le_passage_d_annee():
    from booking.benevolat import besoins_de_la_semaine_type

    calcul = besoins_de_la_semaine_type(
        [fausse_ligne(0)], datetime.date(2030, 12, 28), datetime.date(2031, 1, 13), [], set(),
    )

    assert dates(calcul["a_creer"]) == [
        datetime.date(2030, 12, 30), datetime.date(2031, 1, 6), datetime.date(2031, 1, 13),
    ]


# ---------------------------------------------------------------------------
# Création en base / Creation in the database
# ---------------------------------------------------------------------------

def aujourd_hui():
    from booking.benevolat import aujourd_hui_au_lieu

    with schema_context(TENANT_SCHEMA):
        return aujourd_hui_au_lieu()


@pytest.fixture
def hebdo():
    """
    Un planning hebdomadaire publié (début aujourd'hui, horizon 2 semaines), une tâche, et
    une ligne pour CHAQUE jour de la semaine, 18h–21h, 1 personne.
    `hebdo.creer()` lance creer_les_besoins_de_la_semaine_type et rend le nombre créé.
    / A weekly planning with one row per weekday.
    """
    from booking.benevolat import creer_les_besoins_de_la_semaine_type
    from booking.models import LigneDeSemaineType, PlanningBenevole, TacheBenevole

    with schema_context(TENANT_SCHEMA):
        suffixe = uuid.uuid4().hex[:8]
        planning = PlanningBenevole.objects.create(
            name=f"{TEST_PREFIX} hebdo {suffixe}", slug=f"test-hebdo-{suffixe}", published=True,
            type_de_planning=PlanningBenevole.HEBDOMADAIRE, date_de_debut=aujourd_hui(), horizon_en_semaines=2,
        )
        tache = TacheBenevole.objects.create(name=f"{TEST_PREFIX} bar {suffixe}")
        for jour in range(7):
            LigneDeSemaineType.objects.create(
                planning=planning, jour_de_la_semaine=jour, tache=tache,
                heure_debut=datetime.time(18), heure_fin=datetime.time(21),
            )

        def creer():
            with schema_context(TENANT_SCHEMA):
                return creer_les_besoins_de_la_semaine_type(planning)

        def relire():
            planning.refresh_from_db()
            return planning

        yield SimpleNamespace(planning=planning, tache=tache, creer=creer, relire=relire)


def dates_des_besoins(planning):
    return sorted(planning.besoins.values_list("date", flat=True))


def test_creer_ouvre_l_horizon_et_relancer_ne_cree_rien(hebdo):
    """Horizon 2 semaines : d'aujourd'hui à aujourd'hui + 14 jours, un besoin par jour."""
    with schema_context(TENANT_SCHEMA):
        nombre_cree = hebdo.creer()
        nombre_cree_en_relancant = hebdo.creer()

        debut = aujourd_hui()
        assert nombre_cree == 15
        assert nombre_cree_en_relancant == 0
        assert dates_des_besoins(hebdo.planning) == [debut + datetime.timedelta(days=k) for k in range(15)]
        assert hebdo.relire().besoins_crees_jusqu_au == debut + datetime.timedelta(days=14)
        for besoin in hebdo.planning.besoins.all():
            assert besoin.ligne_de_semaine_type.jour_de_la_semaine == besoin.date.weekday()


def test_une_date_de_debut_future_et_une_date_de_fin(hebdo):
    with schema_context(TENANT_SCHEMA):
        debut = aujourd_hui() + datetime.timedelta(days=3)
        fin = aujourd_hui() + datetime.timedelta(days=5)
        hebdo.planning.date_de_debut = debut
        hebdo.planning.date_de_fin = fin
        hebdo.planning.save()

        hebdo.creer()

        assert dates_des_besoins(hebdo.planning) == [debut, debut + datetime.timedelta(days=1), fin]
        assert hebdo.relire().besoins_crees_jusqu_au == fin


def test_un_besoin_supprime_a_la_main_n_est_jamais_recree(hebdo):
    with schema_context(TENANT_SCHEMA):
        hebdo.creer()
        demain = aujourd_hui() + datetime.timedelta(days=1)
        hebdo.planning.besoins.filter(date=demain).delete()
        # L'horizon s'allonge : la tâche de nuit repasse et ouvre de nouveaux jours.
        # relire() d'abord : besoins_crees_jusqu_au a été écrit en base par creer().
        # / The horizon grows. Reload first: creer() wrote besoins_crees_jusqu_au.
        planning = hebdo.relire()
        planning.horizon_en_semaines = 3
        planning.save()

        nombre_cree = hebdo.creer()

        assert nombre_cree == 7
        assert not hebdo.planning.besoins.filter(date=demain).exists()


def test_besoins_crees_jusqu_au_ne_recule_jamais(hebdo):
    """Date de fin avancée puis reculée : les jours entre les deux ne sont pas recréés."""
    with schema_context(TENANT_SCHEMA):
        hebdo.creer()
        planning = hebdo.relire()
        jusqu_au_avant = planning.besoins_crees_jusqu_au
        planning.date_de_fin = aujourd_hui() + datetime.timedelta(days=2)
        planning.save()

        assert hebdo.creer() == 0
        assert hebdo.relire().besoins_crees_jusqu_au == jusqu_au_avant


def test_un_planning_ponctuel_ne_cree_rien(hebdo):
    from booking.models import PlanningBenevole

    with schema_context(TENANT_SCHEMA):
        hebdo.planning.type_de_planning = PlanningBenevole.PONCTUEL
        hebdo.planning.save()

        assert hebdo.creer() == 0
        assert hebdo.planning.besoins.count() == 0


def test_un_jour_ferme_du_calendrier_est_saute(hebdo, test_calendar):
    from booking.models import ClosedPeriod

    with schema_context(TENANT_SCHEMA):
        jour_ferme = aujourd_hui() + datetime.timedelta(days=4)
        fermeture = ClosedPeriod.objects.create(calendar=test_calendar, start_date=jour_ferme, end_date=jour_ferme)
        hebdo.planning.calendrier = test_calendar
        hebdo.planning.save()
        try:
            hebdo.creer()
            assert not hebdo.planning.besoins.filter(date=jour_ferme).exists()
            assert hebdo.planning.besoins.filter(date=jour_ferme + datetime.timedelta(days=1)).exists()
        finally:
            hebdo.planning.calendrier = None
            hebdo.planning.save()
            fermeture.delete()


def test_un_lieu_en_utc_plus_4_a_22h_utc_est_deja_au_lendemain(hebdo):
    from BaseBillet.models import Configuration

    jour_utc = datetime.date(2031, 3, 10)
    a_22h_utc = datetime.datetime(2031, 3, 10, 22, 0, tzinfo=datetime.timezone.utc)
    with schema_context(TENANT_SCHEMA):
        hebdo.planning.date_de_debut = jour_utc - datetime.timedelta(days=30)
        hebdo.planning.save()
        with mock.patch("django.utils.timezone.now", return_value=a_22h_utc), \
                mock.patch.object(Configuration, "get_tzinfo", return_value=zoneinfo.ZoneInfo("Indian/Reunion")):
            hebdo.creer()

        assert dates_des_besoins(hebdo.planning)[0] == jour_utc + datetime.timedelta(days=1)


def test_deux_creations_simultanees_ne_font_aucun_doublon(hebdo):
    """
    Une première transaction tient le verrou du planning et crée ; une seconde arrive
    pendant ce temps. Elle doit attendre, relire besoins_crees_jusqu_au, et ne rien créer.
    / A second call during the first one's transaction must wait and create nothing.
    """
    from booking.benevolat import creer_les_besoins_de_la_semaine_type
    from booking.models import PlanningBenevole
    from django.db import connection as connexion_du_fil, transaction

    verrou_pris = threading.Event()
    resultats = {}

    def premiere_creation():
        try:
            with schema_context(TENANT_SCHEMA):
                with transaction.atomic():
                    PlanningBenevole.objects.select_for_update().get(pk=hebdo.planning.pk)
                    verrou_pris.set()
                    # Laisse le temps à la seconde de démarrer et de buter sur le verrou.
                    # / Give the second one time to start and hit the lock.
                    threading.Event().wait(1.5)
                    resultats["premiere"] = creer_les_besoins_de_la_semaine_type(hebdo.planning)
        finally:
            connexion_du_fil.close()

    def seconde_creation():
        try:
            with schema_context(TENANT_SCHEMA):
                resultats["seconde"] = creer_les_besoins_de_la_semaine_type(hebdo.planning)
        finally:
            connexion_du_fil.close()

    fil_premier = threading.Thread(target=premiere_creation)
    fil_premier.start()
    verrou_pris.wait(10)
    fil_second = threading.Thread(target=seconde_creation)
    fil_second.start()
    fil_premier.join(20)
    fil_second.join(20)

    with schema_context(TENANT_SCHEMA):
        assert resultats == {"premiere": 15, "seconde": 0}
        assert hebdo.planning.besoins.count() == 15


def test_la_tache_de_nuit_parcourt_les_lieux_sauf_public_et_emplacements_vides():
    from Customers.models import Client as Lieu
    from booking.tasks import creer_les_besoins_des_semaines_types

    schemas_parcourus = []
    with mock.patch(
        "booking.tasks.creer_les_besoins_des_semaines_types_du_lieu",
        side_effect=lambda: schemas_parcourus.append(connection.schema_name),
    ):
        creer_les_besoins_des_semaines_types()

    assert "public" not in schemas_parcourus
    assert "lespass" in schemas_parcourus
    emplacements_vides = set(Lieu.objects.filter(categorie=Lieu.WAITING_CONFIG).values_list("schema_name", flat=True))
    assert not emplacements_vides & set(schemas_parcourus)


def test_la_tache_du_lieu_ne_traite_que_les_plannings_hebdomadaires(hebdo, planning_ponctuel):
    from booking.tasks import creer_les_besoins_des_semaines_types_du_lieu

    plannings_traites = []
    with schema_context(TENANT_SCHEMA):
        with mock.patch(
            "booking.benevolat.creer_les_besoins_de_la_semaine_type",
            side_effect=lambda planning: plannings_traites.append(planning.type_de_planning) or 0,
        ):
            creer_les_besoins_des_semaines_types_du_lieu()

    assert plannings_traites
    assert set(plannings_traites) == {"HEBDOMADAIRE"}


# ---------------------------------------------------------------------------
# Règles du modèle / Model rules
# ---------------------------------------------------------------------------

def test_clean_du_planning_hebdomadaire(hebdo):
    from booking.models import PlanningBenevole

    with schema_context(TENANT_SCHEMA):
        sans_debut = PlanningBenevole(name="x", slug="x", type_de_planning=PlanningBenevole.HEBDOMADAIRE)
        with pytest.raises(ValidationError) as erreur:
            sans_debut.clean()
        assert "date_de_debut" in erreur.value.message_dict

        fin_avant_debut = PlanningBenevole(
            name="x", slug="x", type_de_planning=PlanningBenevole.HEBDOMADAIRE,
            date_de_debut=LUNDI, date_de_fin=LUNDI - datetime.timedelta(days=1),
        )
        with pytest.raises(ValidationError) as erreur:
            fin_avant_debut.clean()
        assert "date_de_fin" in erreur.value.message_dict

        PlanningBenevole(name="x", slug="x").clean()  # ponctuel sans dates : accepté


@pytest.mark.parametrize("horizon", [0, 27])
def test_horizon_hors_de_1_a_26_refuse(hebdo, horizon):
    with schema_context(TENANT_SCHEMA):
        hebdo.planning.horizon_en_semaines = horizon
        with pytest.raises(ValidationError) as erreur:
            hebdo.planning.full_clean()
        assert "horizon_en_semaines" in erreur.value.message_dict


def test_la_ligne_a_les_memes_regles_d_heures(hebdo):
    from booking.models import LigneDeSemaineType

    with schema_context(TENANT_SCHEMA):
        for heure_debut, heure_fin in [(datetime.time(18), None), (datetime.time(18), datetime.time(18))]:
            ligne = LigneDeSemaineType(
                planning=hebdo.planning, jour_de_la_semaine=0, tache=hebdo.tache,
                heure_debut=heure_debut, heure_fin=heure_fin,
            )
            with pytest.raises(ValidationError):
                ligne.clean()


def test_un_besoin_modifie_un_par_un_est_detache_de_sa_ligne(hebdo):
    with schema_context(TENANT_SCHEMA):
        hebdo.creer()
        besoin_inchange, besoin_modifie = list(hebdo.planning.besoins.order_by("date")[:2])

        besoin_inchange.save()
        besoin_modifie.nombre_souhaite = 4
        besoin_modifie.save()

        besoin_inchange.refresh_from_db()
        besoin_modifie.refresh_from_db()
        assert besoin_inchange.ligne_de_semaine_type_id is not None
        assert besoin_modifie.ligne_de_semaine_type_id is None


# ---------------------------------------------------------------------------
# Admin : la fiche du planning hebdomadaire (D30) / Admin: weekly planning page
# ---------------------------------------------------------------------------

@pytest.fixture
def hebdo_du_lendemain():
    """
    Un planning hebdomadaire (début aujourd'hui, horizon 2 semaines) avec UNE ligne : le
    jour de la semaine de demain, 18h–21h, 1 personne. Après création : deux besoins
    (demain et dans 8 jours), le premier avec une inscription.
    / A weekly planning with one row (tomorrow's weekday); two needs, the first signed up.
    """
    from booking.benevolat import creer_les_besoins_de_la_semaine_type
    from booking.models import InscriptionBenevole, LigneDeSemaineType, PlanningBenevole, TacheBenevole

    with schema_context(TENANT_SCHEMA):
        suffixe = uuid.uuid4().hex[:8]
        demain = aujourd_hui() + datetime.timedelta(days=1)
        planning = PlanningBenevole.objects.create(
            name=f"{TEST_PREFIX} lendemain {suffixe}", slug=f"test-lendemain-{suffixe}",
            type_de_planning=PlanningBenevole.HEBDOMADAIRE, date_de_debut=aujourd_hui(), horizon_en_semaines=2,
        )
        bar = TacheBenevole.objects.create(name=f"{TEST_PREFIX} bar {suffixe}")
        menage = TacheBenevole.objects.create(name=f"{TEST_PREFIX} menage {suffixe}")
        ligne = LigneDeSemaineType.objects.create(
            planning=planning, jour_de_la_semaine=demain.weekday(), tache=bar,
            heure_debut=datetime.time(18), heure_fin=datetime.time(21),
        )
        creer_les_besoins_de_la_semaine_type(planning)
        besoin_avec_inscrit = planning.besoins.get(date=demain)
        besoin_sans_inscrit = planning.besoins.get(date=demain + datetime.timedelta(days=7))
        InscriptionBenevole.objects.create(besoin=besoin_avec_inscrit, user=_un_utilisateur())

        yield SimpleNamespace(
            planning=planning, ligne=ligne, bar=bar, menage=menage, demain=demain,
            besoin_avec_inscrit=besoin_avec_inscrit, besoin_sans_inscrit=besoin_sans_inscrit,
        )


def _un_utilisateur():
    from AuthBillet.models import TibilletUser

    email = f"test+semainetype{uuid.uuid4().hex[:8]}@mock.test"
    return TibilletUser.objects.create(email=email, username=email, first_name="Camille", last_name="Test")


def donnees_de_la_fiche(planning, lignes, **champs_du_planning):
    """
    Le POST de la fiche d'un planning hebdomadaire, avec ses lignes.
    :param lignes: liste de dicts {uuid (vide = nouvelle), jour, tache, debut, fin, nombre, supprimer}
    / The POST data of a weekly planning page, with its rows.
    """
    def heure(valeur):
        return valeur.strftime("%H:%M") if valeur else ""

    donnees = {
        "name": planning.name,
        "slug": planning.slug,
        "description": planning.description,
        "calendrier": planning.calendrier_id or "",
        "delai_desinscription_heures": planning.delai_desinscription_heures,
        "type_de_planning": planning.type_de_planning,
        "date_de_debut": planning.date_de_debut.isoformat() if planning.date_de_debut else "",
        "date_de_fin": planning.date_de_fin.isoformat() if planning.date_de_fin else "",
        "horizon_en_semaines": planning.horizon_en_semaines,
        "semaine_type-TOTAL_FORMS": str(len(lignes)),
        "semaine_type-INITIAL_FORMS": str(len([ligne for ligne in lignes if ligne.get("uuid")])),
        "semaine_type-MIN_NUM_FORMS": "0",
        "semaine_type-MAX_NUM_FORMS": "1000",
    }
    if planning.published:
        donnees["published"] = "on"
    for numero, ligne in enumerate(lignes):
        prefixe = f"semaine_type-{numero}-"
        donnees[prefixe + "uuid"] = str(ligne.get("uuid") or "")
        donnees[prefixe + "planning"] = str(planning.pk)
        donnees[prefixe + "jour_de_la_semaine"] = str(ligne["jour"])
        donnees[prefixe + "tache"] = str(ligne["tache"].pk)
        donnees[prefixe + "heure_debut"] = heure(ligne.get("debut"))
        donnees[prefixe + "heure_fin"] = heure(ligne.get("fin"))
        donnees[prefixe + "nombre_souhaite"] = str(ligne.get("nombre", 1))
        if ligne.get("supprimer"):
            donnees[prefixe + "DELETE"] = "on"
    for champ, valeur in champs_du_planning.items():
        donnees[champ] = valeur
    return donnees


def la_ligne(contexte, **changements):
    """La ligne du fixture, en dict pour donnees_de_la_fiche, avec des changements."""
    ligne = {
        "uuid": contexte.ligne.pk, "jour": contexte.ligne.jour_de_la_semaine, "tache": contexte.bar,
        "debut": datetime.time(18), "fin": datetime.time(21), "nombre": 1,
    }
    ligne.update(changements)
    return ligne


def poster_la_fiche(admin_client, planning, donnees):
    reponse = admin_client.post(f"/admin/booking/planningbenevole/{planning.pk}/change/", donnees, follow=True)
    assert reponse.status_code == 200
    assert reponse.redirect_chain, _erreurs_du_formulaire(reponse)
    return reponse.content.decode()


def _erreurs_du_formulaire(reponse):
    contexte = reponse.context
    if contexte is None or "adminform" not in contexte:
        return "pas de redirection"
    erreurs = [contexte["adminform"].form.errors]
    for formset in contexte.get("inline_admin_formsets", []):
        erreurs.append(formset.formset.errors)
        erreurs.append(formset.formset.non_form_errors())
    return erreurs


def test_ligne_modifiee_met_a_jour_les_besoins_sans_inscrit_seulement(admin_client, hebdo_du_lendemain):
    contexte = hebdo_du_lendemain
    with schema_context(TENANT_SCHEMA):
        html = poster_la_fiche(admin_client, contexte.planning, donnees_de_la_fiche(
            contexte.planning, [la_ligne(contexte, tache=contexte.menage, debut=datetime.time(9),
                                         fin=datetime.time(12), nombre=3)],
        ))

        contexte.besoin_sans_inscrit.refresh_from_db()
        contexte.besoin_avec_inscrit.refresh_from_db()
        assert contexte.besoin_sans_inscrit.tache_id == contexte.menage.pk
        assert contexte.besoin_sans_inscrit.heure_debut == datetime.time(9)
        assert contexte.besoin_sans_inscrit.nombre_souhaite == 3
        assert contexte.besoin_sans_inscrit.ligne_de_semaine_type_id == contexte.ligne.pk
        assert contexte.besoin_avec_inscrit.tache_id == contexte.bar.pk
        assert contexte.besoin_avec_inscrit.nombre_souhaite == 1
        assert "0 besoins créés, 1 mis à jour, 0 supprimés." in html
        assert "1 besoins avec des inscrits n&#x27;ont pas été modifiés" in html
        assert f"?planning__uuid__exact={contexte.planning.pk}" in html


def test_ligne_supprimee_supprime_les_sans_inscrit_et_detache_les_autres(admin_client, hebdo_du_lendemain):
    from booking.models import BesoinBenevole

    contexte = hebdo_du_lendemain
    with schema_context(TENANT_SCHEMA):
        poster_la_fiche(admin_client, contexte.planning, donnees_de_la_fiche(
            contexte.planning, [la_ligne(contexte, supprimer=True)],
        ))

        assert not BesoinBenevole.objects.filter(pk=contexte.besoin_sans_inscrit.pk).exists()
        contexte.besoin_avec_inscrit.refresh_from_db()
        assert contexte.besoin_avec_inscrit.ligne_de_semaine_type_id is None


def test_ligne_modifiee_et_changee_de_jour_en_un_seul_enregistrement(admin_client, hebdo_du_lendemain):
    """
    La ligne passe au surlendemain et à 3 personnes : l'ancien besoin sans inscrit est
    supprimé, les nouveaux jours sont créés jusqu'à besoins_crees_jusqu_au, l'ancien besoin
    avec inscrit ne bouge pas.
    """
    from booking.models import BesoinBenevole

    contexte = hebdo_du_lendemain
    surlendemain = contexte.demain + datetime.timedelta(days=1)
    with schema_context(TENANT_SCHEMA):
        html = poster_la_fiche(admin_client, contexte.planning, donnees_de_la_fiche(
            contexte.planning, [la_ligne(contexte, jour=surlendemain.weekday(), nombre=3)],
        ))

        assert not BesoinBenevole.objects.filter(pk=contexte.besoin_sans_inscrit.pk).exists()
        contexte.besoin_avec_inscrit.refresh_from_db()
        assert contexte.besoin_avec_inscrit.date == contexte.demain
        assert contexte.besoin_avec_inscrit.nombre_souhaite == 1
        besoins_du_nouveau_jour = contexte.planning.besoins.filter(
            ligne_de_semaine_type=contexte.ligne,
        ).exclude(pk=contexte.besoin_avec_inscrit.pk)
        assert sorted(besoins_du_nouveau_jour.values_list("date", flat=True)) == [
            surlendemain, surlendemain + datetime.timedelta(days=7),
        ]
        assert set(besoins_du_nouveau_jour.values_list("nombre_souhaite", flat=True)) == {3}
        assert "2 besoins créés, 0 mis à jour, 1 supprimés." in html


def test_nouvelle_ligne_cree_ses_besoins(admin_client, hebdo_du_lendemain):
    contexte = hebdo_du_lendemain
    aujourdhui = aujourd_hui()
    with schema_context(TENANT_SCHEMA):
        poster_la_fiche(admin_client, contexte.planning, donnees_de_la_fiche(
            contexte.planning, [
                la_ligne(contexte),
                {"jour": aujourdhui.weekday(), "tache": contexte.menage},
            ],
        ))

        besoins_du_menage = contexte.planning.besoins.filter(tache=contexte.menage)
        assert sorted(besoins_du_menage.values_list("date", flat=True)) == [
            aujourdhui, aujourdhui + datetime.timedelta(days=7), aujourdhui + datetime.timedelta(days=14),
        ]


def test_date_de_fin_avancee_supprime_les_besoins_hors_periode_sans_inscrit(admin_client, hebdo_du_lendemain):
    """Hors de la nouvelle période : le besoin de la ligne sans inscrit part ; celui avec
    inscrit et le besoin saisi à la main restent."""
    from booking.models import BesoinBenevole

    contexte = hebdo_du_lendemain
    with schema_context(TENANT_SCHEMA):
        besoin_manuel = BesoinBenevole.objects.create(
            planning=contexte.planning, tache=contexte.menage, date=aujourd_hui() + datetime.timedelta(days=5),
        )
        poster_la_fiche(admin_client, contexte.planning, donnees_de_la_fiche(
            contexte.planning, [la_ligne(contexte)], date_de_fin=aujourd_hui().isoformat(),
        ))

        assert not BesoinBenevole.objects.filter(pk=contexte.besoin_sans_inscrit.pk).exists()
        assert BesoinBenevole.objects.filter(pk=contexte.besoin_avec_inscrit.pk).exists()
        assert BesoinBenevole.objects.filter(pk=besoin_manuel.pk).exists()


def test_premier_jour_avance_cree_les_jours_ajoutes(admin_client, hebdo_du_lendemain):
    """
    Le planning commençait dans 3 jours (rien avant). Le premier jour est avancé à
    aujourd'hui : le besoin de demain est créé, alors que besoins_crees_jusqu_au est
    déjà plus loin.
    / First day moved earlier: the added days are created.
    """
    from booking.models import PlanningBenevole

    contexte = hebdo_du_lendemain
    with schema_context(TENANT_SCHEMA):
        ancien_debut = aujourd_hui() + datetime.timedelta(days=3)
        PlanningBenevole.objects.filter(pk=contexte.planning.pk).update(date_de_debut=ancien_debut)
        contexte.planning.besoins.filter(date__lt=ancien_debut).delete()
        # Supprimé à la main après l'ancien premier jour : il ne doit pas revenir.
        # / Deleted by hand after the old first day: must not come back.
        contexte.planning.besoins.filter(pk=contexte.besoin_sans_inscrit.pk).delete()
        contexte.planning.refresh_from_db()

        html = poster_la_fiche(admin_client, contexte.planning, donnees_de_la_fiche(
            contexte.planning, [la_ligne(contexte)], date_de_debut=aujourd_hui().isoformat(),
        ))

        besoin_de_demain = contexte.planning.besoins.get(date=contexte.demain)
        assert besoin_de_demain.ligne_de_semaine_type_id == contexte.ligne.pk
        assert not contexte.planning.besoins.filter(date=contexte.besoin_sans_inscrit.date).exists()
        assert "1 besoins créés, 0 mis à jour, 0 supprimés." in html


def test_premier_jour_recule_supprime_les_besoins_d_avant_sans_inscrit(admin_client, hebdo_du_lendemain):
    from booking.models import BesoinBenevole, InscriptionBenevole

    contexte = hebdo_du_lendemain
    with schema_context(TENANT_SCHEMA):
        InscriptionBenevole.objects.filter(besoin=contexte.besoin_avec_inscrit).delete()

        poster_la_fiche(admin_client, contexte.planning, donnees_de_la_fiche(
            contexte.planning, [la_ligne(contexte)],
            date_de_debut=(contexte.demain + datetime.timedelta(days=1)).isoformat(),
        ))

        assert not BesoinBenevole.objects.filter(pk=contexte.besoin_avec_inscrit.pk).exists()
        assert BesoinBenevole.objects.filter(pk=contexte.besoin_sans_inscrit.pk).exists()


def test_repasser_en_ponctuel_par_la_fiche_garde_les_besoins_et_ne_cree_rien(admin_client, hebdo_du_lendemain):
    from booking.models import PlanningBenevole

    contexte = hebdo_du_lendemain
    with schema_context(TENANT_SCHEMA):
        besoins_avant = set(contexte.planning.besoins.values_list("pk", flat=True))
        jusqu_au_avant = PlanningBenevole.objects.get(pk=contexte.planning.pk).besoins_crees_jusqu_au

        poster_la_fiche(admin_client, contexte.planning, donnees_de_la_fiche(
            contexte.planning, [la_ligne(contexte)], type_de_planning=PlanningBenevole.PONCTUEL,
            horizon_en_semaines="6",
        ))

        contexte.planning.refresh_from_db()
        assert contexte.planning.type_de_planning == PlanningBenevole.PONCTUEL
        assert set(contexte.planning.besoins.values_list("pk", flat=True)) == besoins_avant
        assert contexte.planning.besoins_crees_jusqu_au == jusqu_au_avant


def test_une_exception_manuelle_n_est_pas_ecrasee_par_la_ligne(admin_client, hebdo_du_lendemain):
    """
    Le besoin sans inscrit est modifié à la main sur la page « Besoins » (2 personnes) :
    il se détache. Puis la ligne passe à 5 personnes : l'exception garde 2.
    """
    contexte = hebdo_du_lendemain
    besoin = contexte.besoin_sans_inscrit
    with schema_context(TENANT_SCHEMA):
        reponse = admin_client.post(f"/admin/booking/besoinbenevole/{besoin.pk}/change/", {
            "planning": str(contexte.planning.pk), "tache": str(contexte.bar.pk),
            "date": besoin.date.isoformat(), "heure_debut": "18:00", "heure_fin": "21:00",
            "nombre_souhaite": "2",
        })
        assert reponse.status_code == 302
        besoin.refresh_from_db()
        assert besoin.ligne_de_semaine_type_id is None

        poster_la_fiche(admin_client, contexte.planning, donnees_de_la_fiche(
            contexte.planning, [la_ligne(contexte, nombre=5)],
        ))

        besoin.refresh_from_db()
        assert besoin.nombre_souhaite == 2


def test_les_inlines_suivent_le_type_enregistre(admin_client, hebdo_du_lendemain):
    """Hebdomadaire : la semaine type, pas les besoins. Ponctuel : les besoins À VENIR."""
    from booking.models import BesoinBenevole, PlanningBenevole

    contexte = hebdo_du_lendemain
    with schema_context(TENANT_SCHEMA):
        html_hebdo = admin_client.get(f"/admin/booking/planningbenevole/{contexte.planning.pk}/change/").content.decode()
        assert "semaine_type-TOTAL_FORMS" in html_hebdo
        assert "besoins-TOTAL_FORMS" not in html_hebdo

        contexte.planning.type_de_planning = PlanningBenevole.PONCTUEL
        contexte.planning.save()
        besoin_passe = BesoinBenevole.objects.create(
            planning=contexte.planning, tache=contexte.bar, date=aujourd_hui() - datetime.timedelta(days=3),
        )
        html_ponctuel = admin_client.get(f"/admin/booking/planningbenevole/{contexte.planning.pk}/change/").content.decode()
        assert "besoins-TOTAL_FORMS" in html_ponctuel
        assert "semaine_type-TOTAL_FORMS" not in html_ponctuel
        assert str(contexte.besoin_sans_inscrit.pk) in html_ponctuel
        assert str(besoin_passe.pk) not in html_ponctuel


def test_passer_un_planning_ponctuel_en_hebdomadaire_s_enregistre(admin_client, planning_ponctuel):
    """
    La fiche d'un planning ponctuel envoie l'inline des besoins. Le POST qui passe le type
    à « Chaque semaine » doit être accepté : les inlines suivent le type ENREGISTRÉ.
    / Switching a one-off planning to weekly must save (inlines follow the SAVED type).
    """
    from booking.models import PlanningBenevole

    planning = planning_ponctuel
    with schema_context(TENANT_SCHEMA):
        donnees = {
            "name": planning.name, "slug": planning.slug, "description": "", "calendrier": "",
            "delai_desinscription_heures": "24", "type_de_planning": PlanningBenevole.HEBDOMADAIRE,
            "date_de_debut": aujourd_hui().isoformat(), "date_de_fin": "", "horizon_en_semaines": "4",
            "besoins-TOTAL_FORMS": "0", "besoins-INITIAL_FORMS": "0",
            "besoins-MIN_NUM_FORMS": "0", "besoins-MAX_NUM_FORMS": "1000",
        }
        reponse = admin_client.post(f"/admin/booking/planningbenevole/{planning.pk}/change/", donnees)

        assert reponse.status_code == 302
        planning.refresh_from_db()
        assert planning.type_de_planning == PlanningBenevole.HEBDOMADAIRE


@pytest.fixture
def planning_ponctuel():
    from booking.models import PlanningBenevole

    with schema_context(TENANT_SCHEMA):
        suffixe = uuid.uuid4().hex[:8]
        yield PlanningBenevole.objects.create(name=f"{TEST_PREFIX} ponctuel {suffixe}", slug=f"test-ponctuel-{suffixe}")


def test_repeter_masque_et_refuse_pour_un_planning_hebdomadaire(admin_client, hebdo_du_lendemain):
    contexte = hebdo_du_lendemain
    with schema_context(TENANT_SCHEMA):
        html = admin_client.get(f"/admin/booking/planningbenevole/{contexte.planning.pk}/change/").content.decode()
        reponse_de_la_page = admin_client.get(f"/admin/booking/planningbenevole/{contexte.planning.pk}/repeter/")

    assert "ouvrir-repeter" not in html
    assert reponse_de_la_page.status_code == 403


# ---------------------------------------------------------------------------
# Admin : la page « Besoins » / Admin: the "Needs" page
# ---------------------------------------------------------------------------

def adresse_des_besoins(planning, **filtres):
    parametres = [f"planning__uuid__exact={planning.pk}"]
    for nom, valeur in filtres.items():
        parametres.append(f"{nom}={valeur}")
    return "/admin/booking/besoinbenevole/?" + "&".join(parametres)


def test_page_besoins_a_venir_par_defaut_et_filtres(admin_client, hebdo_du_lendemain):
    from booking.models import BesoinBenevole

    contexte = hebdo_du_lendemain
    with schema_context(TENANT_SCHEMA):
        besoin_passe = BesoinBenevole.objects.create(
            planning=contexte.planning, tache=contexte.menage, date=aujourd_hui() - datetime.timedelta(days=3),
        )

        def uuids_affiches(**filtres):
            reponse = admin_client.get(adresse_des_besoins(contexte.planning, **filtres))
            assert reponse.status_code == 200
            return {str(besoin.pk) for besoin in reponse.context["cl"].result_list}

        a_venir = {str(contexte.besoin_avec_inscrit.pk), str(contexte.besoin_sans_inscrit.pk)}
        assert uuids_affiches() == a_venir
        assert uuids_affiches(quand="passes") == {str(besoin_passe.pk)}
        assert uuids_affiches(quand="tous") == a_venir | {str(besoin_passe.pk)}
        assert uuids_affiches(inscrits="avec") == {str(contexte.besoin_avec_inscrit.pk)}
        assert uuids_affiches(inscrits="sans") == {str(contexte.besoin_sans_inscrit.pk)}
        assert uuids_affiches(quand="tous", tache__uuid__exact=contexte.menage.pk) == {str(besoin_passe.pk)}


def test_page_besoins_nombre_de_requetes_constant(admin_client, hebdo, test_calendar):
    """10 ou 300 besoins (100 par page), planning avec calendrier : le même nombre de requêtes."""
    from booking.models import BesoinBenevole, InscriptionBenevole

    utilisateur = None
    with schema_context(TENANT_SCHEMA):
        utilisateur = _un_utilisateur()
        hebdo.planning.calendrier = test_calendar
        hebdo.planning.save()

    def requetes_pour(nombre_de_besoins):
        with schema_context(TENANT_SCHEMA):
            BesoinBenevole.objects.filter(planning=hebdo.planning).delete()
            nouveaux_besoins = [
                BesoinBenevole(planning=hebdo.planning, tache=hebdo.tache,
                               date=aujourd_hui() + datetime.timedelta(days=numero))
                for numero in range(nombre_de_besoins)
            ]
            BesoinBenevole.objects.bulk_create(nouveaux_besoins)
            InscriptionBenevole.objects.bulk_create(
                [InscriptionBenevole(besoin=besoin, user=utilisateur) for besoin in nouveaux_besoins]
            )
            with CaptureQueriesContext(connection) as requetes:
                reponse = admin_client.get(adresse_des_besoins(hebdo.planning))
            assert reponse.status_code == 200
            return len(requetes)

    requetes_pour(10)  # chauffe les caches / warms the caches
    assert requetes_pour(300) == requetes_pour(10)


# ---------------------------------------------------------------------------
# Bloc d'accueil / Home block
# ---------------------------------------------------------------------------

def test_la_carte_d_un_planning_hebdomadaire_dit_chaque_semaine(hebdo):
    from booking.benevolat import resumes_des_plannings_a_venir

    with schema_context(TENANT_SCHEMA):
        hebdo.creer()
        resumes = resumes_des_plannings_a_venir(200)

    resume_du_planning = [resume for resume in resumes if resume["planning"].pk == hebdo.planning.pk]
    assert resume_du_planning and resume_du_planning[0]["chaque_semaine"] is True
    assert all(not resume["chaque_semaine"] for resume in resumes if resume["planning"].type_de_planning == "PONCTUEL")
