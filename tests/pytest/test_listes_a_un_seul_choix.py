"""
Pages liste des ressources et des plannings de bénévoles : avec un seul choix,
on ouvre directement sa page.
/ Resource and volunteer planning lists: with a single choice, open its page directly.

LOCALISATION : tests/pytest/test_listes_a_un_seul_choix.py

Vues testées :
- BookingViewSet.list (booking/views.py), GET /booking/ ;
- BenevolatViewSet.list (booking/views_benevolat.py), GET /booking/benevolat/.

La base de dev contient déjà des ressources et des plannings. Pour maîtriser le
nombre de choix, on remplace la fonction qui les charge par une version qui ne
garde que les objets créés par le test.
/ The dev database already holds resources and plannings: the loading function is
replaced by one that only keeps the objects created by the test.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_listes_a_un_seul_choix.py -v
"""

import datetime
from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context

from fabriques_panier import creer_ressource_avec_tarif, identifiant_unique

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les tâches et signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5)."""
    from django.utils import translation

    yield
    translation.deactivate()


def navigateur():
    """Client anonyme sur le lieu `lespass`, en français. / Anonymous client on `lespass`."""
    return Client(HTTP_HOST="lespass.tibillet.localhost", HTTP_ACCEPT_LANGUAGE="fr")


def creer_un_planning_avec_un_besoin_a_venir():
    """Un planning publié avec un besoin dans trois jours. / A published planning with a need in 3 days."""
    from booking.models import BesoinBenevole, PlanningBenevole, TacheBenevole

    identifiant = identifiant_unique()
    planning = PlanningBenevole.objects.create(
        name=f"TEST_benevolat planning {identifiant}",
        slug=f"test-benevolat-{identifiant}",
        published=True,
    )
    tache = TacheBenevole.objects.create(name=f"TEST_benevolat bar {identifiant}")
    BesoinBenevole.objects.create(
        planning=planning,
        tache=tache,
        date=timezone.now().date() + datetime.timedelta(days=3),
        heure_debut=datetime.time(18, 0),
        heure_fin=datetime.time(21, 0),
    )
    return planning


def seulement_ces_plannings(plannings_du_test):
    """
    Remplace resumes_des_plannings_a_venir : le vrai calcul, réduit aux plannings du test.
    / Replaces resumes_des_plannings_a_venir: the real computation, limited to the test plannings.
    """
    from booking.benevolat import resumes_des_plannings_a_venir

    def resumes_des_plannings_du_test(nombre_max):
        resumes_retenus = []
        for resume in resumes_des_plannings_a_venir(nombre_max):
            if resume["planning"] in plannings_du_test:
                resumes_retenus.append(resume)
        return resumes_retenus

    return patch(
        "booking.views_benevolat.resumes_des_plannings_a_venir",
        resumes_des_plannings_du_test,
    )


# ---------------------------------------------------------------------------
# Ressources / Resources
# ---------------------------------------------------------------------------


def test_une_seule_ressource_ouvre_directement_sa_page(tenant):
    with tenant_context(tenant):
        ressource = creer_ressource_avec_tarif().ressource

        with patch(
            "booking.views.BookingViewSet._group_resources",
            return_value=([], [ressource]),
        ):
            reponse = navigateur().get("/booking/")

    assert reponse.status_code == 302
    assert reponse["Location"] == f"/booking/{ressource.pk}/resource/"


def test_plusieurs_ressources_affichent_la_liste(tenant):
    with tenant_context(tenant):
        premiere_ressource = creer_ressource_avec_tarif().ressource
        deuxieme_ressource = creer_ressource_avec_tarif().ressource
        deux_ressources = [premiere_ressource, deuxieme_ressource]

        with patch(
            "booking.views.BookingViewSet._group_resources",
            return_value=([], deux_ressources),
        ):
            reponse = navigateur().get("/booking/")

    assert reponse.status_code == 200
    html = reponse.content.decode()
    assert premiere_ressource.name in html
    assert deuxieme_ressource.name in html


# ---------------------------------------------------------------------------
# Plannings de bénévoles / Volunteer plannings
# ---------------------------------------------------------------------------


def test_un_seul_planning_a_venir_ouvre_directement_sa_page(tenant):
    with tenant_context(tenant):
        planning = creer_un_planning_avec_un_besoin_a_venir()

        with seulement_ces_plannings([planning]):
            reponse = navigateur().get("/booking/benevolat/")

    assert reponse.status_code == 302
    assert reponse["Location"] == f"/booking/benevolat/{planning.slug}/"


def test_plusieurs_plannings_a_venir_affichent_la_liste(tenant):
    with tenant_context(tenant):
        premier_planning = creer_un_planning_avec_un_besoin_a_venir()
        deuxieme_planning = creer_un_planning_avec_un_besoin_a_venir()

        with seulement_ces_plannings([premier_planning, deuxieme_planning]):
            reponse = navigateur().get("/booking/benevolat/")

    assert reponse.status_code == 200
    html = reponse.content.decode()
    assert 'data-testid="benevolat-liste"' in html
    assert f"/booking/benevolat/{premier_planning.slug}/" in html
    assert f"/booking/benevolat/{deuxieme_planning.slug}/" in html
