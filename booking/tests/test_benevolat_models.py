"""
Tests des modèles du planning des bénévoles, et de leur admin.
/ Tests of the volunteer planning models, and of their admin.

LOCALISATION : booking/tests/test_benevolat_models.py

Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§4, §5.6, §8)

Les données de test portent le préfixe TEST_PREFIX. Le calendrier de test est supprimé
par booking/tests/conftest.py en fin de module ; les plannings le protègent (PROTECT),
donc la fixture de ce fichier les supprime avant (elle se termine avant celle du conftest).
/ Test data carries TEST_PREFIX. This file's fixture deletes plannings before the
conftest deletes the test calendar.

Lancement / Run:
    docker exec lespass_django poetry run pytest booking/tests/test_benevolat_models.py -v
"""
import datetime
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django_tenants.utils import schema_context

TEST_PREFIX = '[test_booking_models]'
TENANT_SCHEMA = 'lespass'


@pytest.fixture(scope="module", autouse=True)
def nettoyer_le_benevolat():
    """
    Supprime les plannings et tâches de test après le module.
    Les besoins et inscriptions partent avec leur planning (CASCADE).
    / Deletes test plannings and tasks after the module (needs and sign-ups cascade).
    """
    yield
    from booking.models import PlanningBenevole, TacheBenevole

    with schema_context(TENANT_SCHEMA):
        PlanningBenevole.objects.filter(name__startswith=TEST_PREFIX).delete()
        TacheBenevole.objects.filter(name__startswith=TEST_PREFIX).delete()


@pytest.fixture
def planning_et_tache():
    """
    Un planning et une tâche neufs pour chaque test.
    / A fresh planning and task for each test.
    """
    from booking.models import PlanningBenevole, TacheBenevole
    import uuid

    with schema_context(TENANT_SCHEMA):
        suffixe = uuid.uuid4().hex[:8]
        planning = PlanningBenevole.objects.create(
            name=f"{TEST_PREFIX} planning {suffixe}",
            slug=f"test-benevolat-{suffixe}",
        )
        tache = TacheBenevole.objects.create(name=f"{TEST_PREFIX} bar {suffixe}")
        return planning, tache


# ---------------------------------------------------------------------------
# Contraintes / Constraints
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_nombre_souhaite_zero_refuse_par_la_base(planning_et_tache):
    from booking.models import BesoinBenevole

    planning, tache = planning_et_tache
    with schema_context(TENANT_SCHEMA):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                BesoinBenevole.objects.create(
                    planning=planning, tache=tache,
                    date=datetime.date(2030, 10, 2), nombre_souhaite=0,
                )


@pytest.mark.django_db
def test_une_seule_heure_refusee_par_la_base_et_par_clean(planning_et_tache):
    from booking.models import BesoinBenevole

    planning, tache = planning_et_tache
    with schema_context(TENANT_SCHEMA):
        besoin_avec_une_seule_heure = BesoinBenevole(
            planning=planning, tache=tache,
            date=datetime.date(2030, 10, 2), heure_debut=datetime.time(18, 0),
        )
        with pytest.raises(ValidationError):
            besoin_avec_une_seule_heure.clean()

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                besoin_avec_une_seule_heure.save()


@pytest.mark.django_db
def test_une_personne_ne_s_inscrit_qu_une_fois_par_besoin(planning_et_tache, test_user):
    from booking.models import BesoinBenevole, InscriptionBenevole

    planning, tache = planning_et_tache
    with schema_context(TENANT_SCHEMA):
        besoin = BesoinBenevole.objects.create(
            planning=planning, tache=tache, date=datetime.date(2030, 10, 2),
        )
        InscriptionBenevole.objects.create(besoin=besoin, user=test_user)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                InscriptionBenevole.objects.create(besoin=besoin, user=test_user)


@pytest.mark.django_db
def test_slugs_reserves_refuses_par_clean(planning_et_tache):
    planning, _tache = planning_et_tache
    for slug_reserve in ["besoin", "desistement"]:
        planning.slug = slug_reserve
        with pytest.raises(ValidationError):
            planning.clean()

    planning.slug = "lettre"
    planning.clean()


# ---------------------------------------------------------------------------
# debut() / fin() / est_passe()
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_debut_et_fin_d_une_plage_dans_la_journee(planning_et_tache):
    from BaseBillet.models import Configuration
    from booking.models import BesoinBenevole

    planning, tache = planning_et_tache
    with schema_context(TENANT_SCHEMA):
        fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        besoin = BesoinBenevole(
            planning=planning, tache=tache, date=datetime.date(2030, 10, 2),
            heure_debut=datetime.time(18, 0), heure_fin=datetime.time(21, 0),
        )
        assert besoin.debut() == datetime.datetime(2030, 10, 2, 18, 0, tzinfo=fuseau_du_lieu)
        assert besoin.fin() == datetime.datetime(2030, 10, 2, 21, 0, tzinfo=fuseau_du_lieu)


@pytest.mark.django_db
def test_fin_a_minuit_tombe_le_lendemain(planning_et_tache):
    from BaseBillet.models import Configuration
    from booking.models import BesoinBenevole

    planning, tache = planning_et_tache
    with schema_context(TENANT_SCHEMA):
        fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        besoin = BesoinBenevole(
            planning=planning, tache=tache, date=datetime.date(2030, 10, 2),
            heure_debut=datetime.time(21, 0), heure_fin=datetime.time(0, 0),
        )
        assert besoin.fin() == datetime.datetime(2030, 10, 3, 0, 0, tzinfo=fuseau_du_lieu)


@pytest.mark.django_db
def test_journee_entiere_va_de_minuit_a_minuit(planning_et_tache):
    from BaseBillet.models import Configuration
    from booking.models import BesoinBenevole

    planning, tache = planning_et_tache
    with schema_context(TENANT_SCHEMA):
        fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        besoin = BesoinBenevole(planning=planning, tache=tache, date=datetime.date(2030, 10, 2))
        assert besoin.est_une_journee()
        assert besoin.debut() == datetime.datetime(2030, 10, 2, 0, 0, tzinfo=fuseau_du_lieu)
        assert besoin.fin() == datetime.datetime(2030, 10, 3, 0, 0, tzinfo=fuseau_du_lieu)


@pytest.mark.django_db
def test_un_besoin_reste_ouvert_jusqu_a_sa_fin(planning_et_tache):
    """
    Un besoin 18h–21h n'est pas passé à 18h30 ; il l'est à 21h pile.
    / An 18:00–21:00 need is not past at 18:30; it is at 21:00 sharp.
    """
    from BaseBillet.models import Configuration
    from booking.models import BesoinBenevole

    planning, tache = planning_et_tache
    with schema_context(TENANT_SCHEMA):
        fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        besoin = BesoinBenevole(
            planning=planning, tache=tache, date=datetime.date(2030, 10, 2),
            heure_debut=datetime.time(18, 0), heure_fin=datetime.time(21, 0),
        )
        a_18h30 = datetime.datetime(2030, 10, 2, 18, 30, tzinfo=fuseau_du_lieu)
        with mock.patch("booking.models.timezone.now", return_value=a_18h30):
            assert not besoin.est_passe()

        a_21h = datetime.datetime(2030, 10, 2, 21, 0, tzinfo=fuseau_du_lieu)
        with mock.patch("booking.models.timezone.now", return_value=a_21h):
            assert besoin.est_passe()


# ---------------------------------------------------------------------------
# Compteurs : places couvertes, libres, renforts
# / Counters: covered places, free places, extras
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_compteurs_avec_un_renfort(planning_et_tache):
    """
    3 inscrit·es sur un besoin de 2 : 2 places couvertes, 0 libre, 1 renfort.
    / 3 sign-ups on a need of 2: 2 covered, 0 free, 1 extra.
    """
    from AuthBillet.models import TibilletUser
    from booking.models import BesoinBenevole, InscriptionBenevole

    planning, tache = planning_et_tache
    with schema_context(TENANT_SCHEMA):
        besoin = BesoinBenevole.objects.create(
            planning=planning, tache=tache, date=datetime.date(2030, 10, 2), nombre_souhaite=2,
        )
        assert besoin.places_libres() == 2
        assert besoin.places_couvertes() == 0

        trois_comptes = list(TibilletUser.objects.order_by("date_joined")[:3])
        assert len(trois_comptes) == 3
        for compte in trois_comptes:
            InscriptionBenevole.objects.create(besoin=besoin, user=compte)

        assert besoin.nombre_inscrits() == 3
        assert besoin.places_couvertes() == 2
        assert besoin.places_libres() == 0
        assert besoin.nombre_de_renforts() == 1


# ---------------------------------------------------------------------------
# Jours de fermeture / Closing days
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_date_est_fermee(planning_et_tache, test_calendar):
    """
    Jour dans une fermeture, jours au bord, jour hors fermeture, fermeture sans fin.
    / Day inside a closure, edge days, day outside, endless closure.
    """
    from booking.models import ClosedPeriod

    planning, _tache = planning_et_tache
    with schema_context(TENANT_SCHEMA):
        planning.calendrier = test_calendar
        planning.save()

        fete = ClosedPeriod.objects.create(
            calendar=test_calendar, label="Fête nationale",
            start_date=datetime.date(2031, 7, 14), end_date=datetime.date(2031, 7, 15),
        )
        sans_libelle = ClosedPeriod.objects.create(
            calendar=test_calendar,
            start_date=datetime.date(2031, 8, 10), end_date=datetime.date(2031, 8, 12),
        )
        sans_fin = ClosedPeriod.objects.create(
            calendar=test_calendar, label="Travaux", start_date=datetime.date(2032, 1, 1),
        )
        try:
            assert planning.date_est_fermee(datetime.date(2031, 7, 14)) == fete
            assert planning.date_est_fermee(datetime.date(2031, 7, 15)) == fete
            assert planning.date_est_fermee(datetime.date(2031, 7, 13)) is None
            assert planning.date_est_fermee(datetime.date(2031, 7, 16)) is None
            assert planning.date_est_fermee(datetime.date(2040, 5, 1)) == sans_fin

            assert planning.libelle_de_fermeture(datetime.date(2031, 7, 14)) == "Fête nationale"
            assert planning.libelle_de_fermeture(datetime.date(2031, 7, 16)) is None
            # Sans label : le repli écrit les deux dates.
            # / No label: the fallback writes both dates.
            libelle_de_repli = str(planning.libelle_de_fermeture(datetime.date(2031, 8, 11)))
            assert "10" in libelle_de_repli and "12" in libelle_de_repli
        finally:
            fete.delete()
            sans_libelle.delete()
            sans_fin.delete()


@pytest.mark.django_db
def test_planning_sans_calendrier_n_est_jamais_ferme(planning_et_tache):
    planning, _tache = planning_et_tache
    with schema_context(TENANT_SCHEMA):
        assert planning.calendrier is None
        assert planning.date_est_fermee(datetime.date(2031, 7, 14)) is None


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_les_listes_de_l_admin_repondent(admin_client, planning_et_tache):
    for nom_du_modele in ["planningbenevole", "tachebenevole", "inscriptionbenevole"]:
        reponse = admin_client.get(f"/admin/booking/{nom_du_modele}/")
        assert reponse.status_code == 200, nom_du_modele


@pytest.mark.django_db
def test_l_admin_n_ajoute_pas_d_inscription(admin_client):
    reponse = admin_client.get("/admin/booking/inscriptionbenevole/add/")
    assert reponse.status_code == 403


@pytest.mark.django_db
def test_la_fiche_planning_signale_un_besoin_un_jour_ferme(admin_client, planning_et_tache, test_calendar):
    """
    Un besoin saisi un jour fermé est enregistré, et sa ligne affiche « Fermé : <label> ».
    / A need on a closed day is saved, and its row shows "Fermé : <label>".
    """
    from booking.models import BesoinBenevole, ClosedPeriod

    planning, tache = planning_et_tache
    with schema_context(TENANT_SCHEMA):
        planning.calendrier = test_calendar
        planning.save()
        fermeture = ClosedPeriod.objects.create(
            calendar=test_calendar, label="Inventaire annuel",
            start_date=datetime.date(2033, 3, 1), end_date=datetime.date(2033, 3, 1),
        )
        BesoinBenevole.objects.create(planning=planning, tache=tache, date=datetime.date(2033, 3, 1))
        try:
            reponse = admin_client.get(f"/admin/booking/planningbenevole/{planning.pk}/change/")
            assert reponse.status_code == 200
            assert "Inventaire annuel" in reponse.content.decode()
        finally:
            BesoinBenevole.objects.filter(planning=planning).delete()
            fermeture.delete()


@pytest.mark.django_db
def test_debut_egal_fin_refuse_par_clean(planning_et_tache):
    """Début = fin ferait un créneau de 24 h : presque toujours une faute de frappe."""
    from booking.models import BesoinBenevole

    planning, tache = planning_et_tache
    besoin = BesoinBenevole(
        planning=planning, tache=tache, date=datetime.date(2030, 10, 2),
        heure_debut=datetime.time(18, 0), heure_fin=datetime.time(18, 0),
    )
    with pytest.raises(ValidationError):
        besoin.clean()


@pytest.mark.django_db
def test_la_fiche_planning_ne_fait_pas_une_requete_par_besoin(admin_client, planning_et_tache, test_calendar, test_user):
    """
    10 besoins ou 30 : le même nombre de requêtes (préchargement de l'inline).
    / 10 needs or 30: same query count (inline prefetch).
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    from booking.models import BesoinBenevole, InscriptionBenevole

    planning, tache = planning_et_tache
    with schema_context(TENANT_SCHEMA):
        planning.calendrier = test_calendar
        planning.save()

        def requetes_pour(nombre_de_besoins):
            BesoinBenevole.objects.filter(planning=planning).delete()
            for jour in range(nombre_de_besoins):
                besoin = BesoinBenevole.objects.create(
                    planning=planning, tache=tache, date=datetime.date(2034, 1, 1) + datetime.timedelta(days=jour),
                )
                InscriptionBenevole.objects.create(besoin=besoin, user=test_user)
            with CaptureQueriesContext(connection) as requetes:
                reponse = admin_client.get(f"/admin/booking/planningbenevole/{planning.pk}/change/")
            assert reponse.status_code == 200
            return len(requetes)

        try:
            assert requetes_pour(30) == requetes_pour(10)
        finally:
            BesoinBenevole.objects.filter(planning=planning).delete()
