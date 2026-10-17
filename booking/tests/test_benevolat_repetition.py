"""
Tests de « Répéter des besoins » : le calcul pur, puis la page de l'admin.
/ "Repeat needs" tests: the pure computation, then the admin page.

LOCALISATION : booking/tests/test_benevolat_repetition.py

Code testé / Tested code : booking/benevolat.py (calculer_repetitions),
Administration/admin/benevolat.py (PlanningBenevoleAdmin.repeter)
Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§5.7)

Les tests du calcul n'ouvrent pas la base : les besoins et les fermetures sont de
simples objets. Ceux de l'admin créent leurs données avec le préfixe TEST_PREFIX et les
suppriment à la fin.
/ Computation tests don't touch the DB; admin tests clean up after themselves.

Lancement / Run:
    docker exec -w /DjangoFiles lespass_django poetry run pytest booking/tests/test_benevolat_repetition.py -v
"""
import datetime
import uuid
from types import SimpleNamespace

import pytest
from django_tenants.utils import schema_context

TEST_PREFIX = '[test_booking_models]'
TENANT_SCHEMA = 'lespass'

VENDREDI = datetime.date(2031, 10, 3)
SAMEDI = datetime.date(2031, 10, 4)


def faux_besoin(une_date, heure_debut=None, heure_fin=None, tache_id="bar", nombre_souhaite=2):
    """Un besoin sans base : seulement ce que lit calculer_repetitions."""
    return SimpleNamespace(
        tache_id=tache_id, tache=SimpleNamespace(name=tache_id), date=une_date,
        heure_debut=heure_debut, heure_fin=heure_fin, nombre_souhaite=nombre_souhaite,
    )


def fausse_fermeture(debut, fin, label=""):
    return SimpleNamespace(start_date=debut, end_date=fin, label=label)


def dates(copies):
    return [copie["date"] for copie in copies]


# ---------------------------------------------------------------------------
# Calcul pur / Pure computation
# ---------------------------------------------------------------------------

def test_repeter_un_week_end_toutes_les_semaines_4_fois():
    """Modèle ven.–sam., tous les 1 semaine, 4 fois → 8 copies, les 4 week-ends suivants."""
    from booking.benevolat import calculer_repetitions

    modele = [faux_besoin(VENDREDI, datetime.time(18), datetime.time(21)), faux_besoin(SAMEDI)]

    apercu = calculer_repetitions(modele, 7, 4, [], set())

    assert len(apercu["a_creer"]) == 8
    assert sorted(dates(apercu["a_creer"])) == sorted(
        [VENDREDI + datetime.timedelta(days=7 * k) for k in range(1, 5)]
        + [SAMEDI + datetime.timedelta(days=7 * k) for k in range(1, 5)]
    )
    assert apercu["sautes"] == [] and apercu["ignores"] == []


def test_repeter_tous_les_jours():
    from booking.benevolat import calculer_repetitions

    apercu = calculer_repetitions([faux_besoin(SAMEDI)], 1, 6, [], set())

    assert dates(apercu["a_creer"]) == [SAMEDI + datetime.timedelta(days=k) for k in range(1, 7)]


def test_un_week_end_sur_deux():
    from booking.benevolat import calculer_repetitions

    apercu = calculer_repetitions([faux_besoin(SAMEDI)], 14, 3, [], set())

    assert dates(apercu["a_creer"]) == [SAMEDI + datetime.timedelta(days=14 * k) for k in range(1, 4)]


def test_la_copie_garde_tache_heures_et_nombre():
    from booking.benevolat import calculer_repetitions

    modele = faux_besoin(VENDREDI, datetime.time(21), datetime.time(0), tache_id="menage", nombre_souhaite=3)

    copie = calculer_repetitions([modele], 7, 1, [], set())["a_creer"][0]

    assert copie["modele"] is modele
    assert copie["date"] == VENDREDI + datetime.timedelta(days=7)


def test_un_jour_ferme_est_saute_avec_son_libelle():
    from booking.benevolat import calculer_repetitions

    semaine_2 = SAMEDI + datetime.timedelta(days=14)
    fermetures = [fausse_fermeture(semaine_2, semaine_2, label="Fête du quartier")]

    apercu = calculer_repetitions([faux_besoin(SAMEDI)], 7, 3, fermetures, set())

    assert dates(apercu["a_creer"]) == [SAMEDI + datetime.timedelta(days=7), SAMEDI + datetime.timedelta(days=21)]
    assert dates(apercu["sautes"]) == [semaine_2]
    assert apercu["sautes"][0]["fermeture"] == "Fête du quartier"


def test_une_fermeture_sans_label_donne_le_libelle_de_repli():
    from booking.benevolat import calculer_repetitions

    debut = SAMEDI + datetime.timedelta(days=6)
    fermetures = [fausse_fermeture(debut, debut + datetime.timedelta(days=2))]

    apercu = calculer_repetitions([faux_besoin(SAMEDI)], 7, 1, fermetures, set())

    libelle = str(apercu["sautes"][0]["fermeture"])
    assert str(debut.day) in libelle and str((debut + datetime.timedelta(days=2)).day) in libelle


def test_une_fermeture_sans_fin_saute_tout_ce_qui_suit():
    from booking.benevolat import calculer_repetitions

    fermetures = [fausse_fermeture(SAMEDI + datetime.timedelta(days=10), None, label="Travaux")]

    apercu = calculer_repetitions([faux_besoin(SAMEDI)], 7, 4, fermetures, set())

    assert dates(apercu["a_creer"]) == [SAMEDI + datetime.timedelta(days=7)]
    assert len(apercu["sautes"]) == 3


def test_un_besoin_deja_present_est_ignore_et_relancer_ne_double_rien():
    from booking.benevolat import calculer_repetitions, cle_d_un_besoin

    modele = faux_besoin(SAMEDI, datetime.time(10), datetime.time(12))
    deja_la = SAMEDI + datetime.timedelta(days=7)
    existants = {cle_d_un_besoin("bar", deja_la, datetime.time(10), datetime.time(12))}

    apercu = calculer_repetitions([modele], 7, 2, [], existants)

    assert dates(apercu["ignores"]) == [deja_la]
    assert dates(apercu["a_creer"]) == [SAMEDI + datetime.timedelta(days=14)]
    # L'ensemble reçu n'est pas modifié / The given set is untouched
    assert len(existants) == 1


def test_deux_besoins_modele_identiques_ne_donnent_qu_une_copie_par_date():
    """
    Deux besoins identiques dans le modèle (saisis deux fois) : chaque date n'est créée
    qu'une fois, l'autre copie est ignorée.
    / Two identical model needs: each date is created once, the other copy is ignored.
    """
    from booking.benevolat import calculer_repetitions

    modele = [faux_besoin(SAMEDI), faux_besoin(SAMEDI)]

    apercu = calculer_repetitions(modele, 7, 2, [], set())

    assert len(apercu["a_creer"]) == 2
    assert len(apercu["ignores"]) == 2


def test_meme_jour_mais_autres_heures_n_est_pas_un_doublon():
    from booking.benevolat import calculer_repetitions, cle_d_un_besoin

    copie_prevue = SAMEDI + datetime.timedelta(days=7)
    existants = {cle_d_un_besoin("bar", copie_prevue, datetime.time(18), datetime.time(21))}

    apercu = calculer_repetitions(
        [faux_besoin(SAMEDI, datetime.time(21), datetime.time(0))], 7, 1, [], existants,
    )

    assert dates(apercu["a_creer"]) == [copie_prevue]


# ---------------------------------------------------------------------------
# Page de l'admin / Admin page
# ---------------------------------------------------------------------------

@pytest.fixture
def planning_avec_un_week_end(test_calendar):
    """
    Un planning avec un week-end modèle : ven. bar 18h–21h et sam. ménage journée.
    Le calendrier de test ferme le 3e samedi suivant.
    """
    from booking.models import BesoinBenevole, ClosedPeriod, PlanningBenevole, TacheBenevole

    with schema_context(TENANT_SCHEMA):
        suffixe = uuid.uuid4().hex[:8]
        planning = PlanningBenevole.objects.create(
            name=f"{TEST_PREFIX} repeter {suffixe}", slug=f"test-repeter-{suffixe}", calendrier=test_calendar,
        )
        bar = TacheBenevole.objects.create(name=f"{TEST_PREFIX} bar {suffixe}")
        menage = TacheBenevole.objects.create(name=f"{TEST_PREFIX} menage {suffixe}")
        BesoinBenevole.objects.create(
            planning=planning, tache=bar, date=VENDREDI,
            heure_debut=datetime.time(18), heure_fin=datetime.time(21), nombre_souhaite=2,
        )
        BesoinBenevole.objects.create(planning=planning, tache=menage, date=SAMEDI, nombre_souhaite=1)
        samedi_ferme = SAMEDI + datetime.timedelta(days=21)
        fermeture = ClosedPeriod.objects.create(
            calendar=test_calendar, label="Fête du quartier", start_date=samedi_ferme, end_date=samedi_ferme,
        )
        yield planning
        planning.delete()
        bar.delete()
        menage.delete()
        fermeture.delete()


def donnees_du_formulaire(**autres):
    donnees = {
        "debut_du_modele": VENDREDI.isoformat(),
        "fin_du_modele": SAMEDI.isoformat(),
        "repeter_tous_les": "1",
        "unite": "semaines",
        "nombre_de_fois": "4",
    }
    donnees.update(autres)
    return donnees


@pytest.mark.django_db
def test_la_page_repeter_s_ouvre_preremplie(admin_client, planning_avec_un_week_end):
    reponse = admin_client.get(f"/admin/booking/planningbenevole/{planning_avec_un_week_end.pk}/repeter/")

    assert reponse.status_code == 200
    html = reponse.content.decode()
    assert VENDREDI.isoformat() in html
    assert (VENDREDI + datetime.timedelta(days=6)).isoformat() in html


@pytest.mark.django_db
def test_l_apercu_n_ecrit_rien_puis_confirmer_cree_tout(admin_client, planning_avec_un_week_end):
    """
    4 week-ends × 2 besoins = 8 copies, dont 1 sautée (samedi fermé) → 7 à créer.
    L'aperçu n'écrit rien ; « Confirmer » crée les 7 et revient à la fiche avec le message.
    Relancer ensuite : tout est ignoré, rien n'est créé.
    """
    planning = planning_avec_un_week_end
    adresse = f"/admin/booking/planningbenevole/{planning.pk}/repeter/"

    with schema_context(TENANT_SCHEMA):
        reponse_apercu = admin_client.post(adresse, donnees_du_formulaire())
        assert reponse_apercu.status_code == 200
        html = reponse_apercu.content.decode()
        assert 'data-testid="benevolat-repeter-confirmer"' in html
        assert "Fête du quartier" in html
        assert planning.besoins.count() == 2

        reponse_confirmee = admin_client.post(adresse, donnees_du_formulaire(confirmer="1"), follow=True)
        assert reponse_confirmee.status_code == 200
        assert planning.besoins.count() == 9
        assert "7 besoins créés, 1 sautés (fermeture), 0 ignorés" in reponse_confirmee.content.decode()

        copie_du_bar = planning.besoins.get(date=VENDREDI + datetime.timedelta(days=7))
        assert copie_du_bar.heure_debut == datetime.time(18)
        assert copie_du_bar.nombre_souhaite == 2
        assert copie_du_bar.inscriptions.count() == 0

        admin_client.post(adresse, donnees_du_formulaire(confirmer="1"))
        assert planning.besoins.count() == 9


@pytest.mark.django_db
def test_une_periode_modele_vide_est_refusee(admin_client, planning_avec_un_week_end):
    planning = planning_avec_un_week_end
    vide = (VENDREDI + datetime.timedelta(days=100)).isoformat()

    with schema_context(TENANT_SCHEMA):
        reponse = admin_client.post(
            f"/admin/booking/planningbenevole/{planning.pk}/repeter/",
            donnees_du_formulaire(debut_du_modele=vide, fin_du_modele=vide, confirmer="1"),
        )
        assert reponse.status_code == 200
        assert "Aucun besoin dans cette période" in reponse.content.decode()
        assert planning.besoins.count() == 2


@pytest.mark.django_db
def test_la_fin_du_modele_avant_le_debut_est_refusee(admin_client, planning_avec_un_week_end):
    planning = planning_avec_un_week_end

    with schema_context(TENANT_SCHEMA):
        reponse = admin_client.post(
            f"/admin/booking/planningbenevole/{planning.pk}/repeter/",
            donnees_du_formulaire(debut_du_modele=SAMEDI.isoformat(), fin_du_modele=VENDREDI.isoformat(), confirmer="1"),
        )
        assert reponse.status_code == 200
        assert "La fin du modèle doit être" in reponse.content.decode()
        assert planning.besoins.count() == 2


@pytest.mark.django_db
def test_la_fiche_du_planning_porte_le_bouton_repeter(admin_client, planning_avec_un_week_end):
    reponse = admin_client.get(f"/admin/booking/planningbenevole/{planning_avec_un_week_end.pk}/change/")

    assert reponse.status_code == 200
    assert "ouvrir-repeter" in reponse.content.decode()


# ---------------------------------------------------------------------------
# Relecture du 2026-10-16 / 2026-10-16 review
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_une_periode_modele_de_plus_de_31_jours_est_refusee(admin_client, planning_avec_un_week_end):
    planning = planning_avec_un_week_end
    with schema_context(TENANT_SCHEMA):
        reponse = admin_client.post(
            f"/admin/booking/planningbenevole/{planning.pk}/repeter/",
            donnees_du_formulaire(fin_du_modele=(VENDREDI + datetime.timedelta(days=40)).isoformat(), confirmer="1"),
        )
        assert "ne peut pas dépasser 31 jours" in reponse.content.decode()
        assert planning.besoins.count() == 2


@pytest.mark.django_db
def test_une_adresse_bricolee_rend_404(admin_client):
    assert admin_client.get("/admin/booking/planningbenevole/pas-un-uuid/repeter/").status_code == 404


@pytest.mark.django_db
def test_un_besoin_ajoute_entre_l_apercu_et_la_confirmation_est_ignore(admin_client, planning_avec_un_week_end):
    """La confirmation recalcule l'aperçu : un besoin ajouté entre-temps n'est pas doublé."""
    from booking.models import BesoinBenevole

    planning = planning_avec_un_week_end
    adresse = f"/admin/booking/planningbenevole/{planning.pk}/repeter/"
    with schema_context(TENANT_SCHEMA):
        admin_client.post(adresse, donnees_du_formulaire())
        modele_du_bar = planning.besoins.get(date=VENDREDI)
        BesoinBenevole.objects.create(
            planning=planning, tache=modele_du_bar.tache, date=VENDREDI + datetime.timedelta(days=7),
            heure_debut=modele_du_bar.heure_debut, heure_fin=modele_du_bar.heure_fin,
        )

        admin_client.post(adresse, donnees_du_formulaire(confirmer="1"))

        assert planning.besoins.filter(date=VENDREDI + datetime.timedelta(days=7), tache=modele_du_bar.tache).count() == 1
        assert planning.besoins.count() == 9
