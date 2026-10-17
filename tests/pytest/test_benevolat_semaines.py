"""
Tests de la pagination par semaine de la page publique d'un planning de bénévoles.
/ Tests of the week-by-week pagination of the volunteer planning public page.

LOCALISATION : tests/pytest/test_benevolat_semaines.py

Code testé / Tested code : booking/benevolat.py (choisir_la_semaine, construire_le_planning…),
booking/views_benevolat.py (retrieve, _reponse_zone)
Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§11.1, D28)

Les dates sont calculées à partir du lundi de la semaine en cours, au fuseau du lieu :
« semaine + 2 » veut dire « le lundi dans deux semaines ».
Chaque test est marqué `django_db` : transaction annulée à la fin, rien ne reste en base.
/ Dates are computed from the current week's Monday. Each test is rolled back.

Lancer / Run : make test ARGS="tests/pytest/test_benevolat_semaines.py"
"""

import datetime
from types import SimpleNamespace
from unittest import mock

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django_tenants.utils import tenant_context

from fabriques_panier import (
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les tâches et signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Tasks and signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


def navigateur(utilisateur=None, **entetes):
    """Client de test sur le lieu `lespass`, en français. / Test client on `lespass`, in French."""
    client = Client(HTTP_HOST="lespass.tibillet.localhost", HTTP_ACCEPT_LANGUAGE="fr", **entetes)
    if utilisateur is not None:
        client.force_login(utilisateur)
    return client


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass` avec un planning publié SANS besoin, et une tâche.
    `lieu.semaine(n)` rend le lundi dans n semaines ; `lieu.besoin(jour)` crée un besoin.
    / The `lespass` venue with a published planning without needs, and a task.
    """
    from BaseBillet.models import Configuration
    from booking.models import BesoinBenevole, PlanningBenevole, TacheBenevole

    with tenant_context(tenant):
        with taches_celery_enregistrees():
            identifiant = identifiant_unique()
            fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
            aujourd_hui = timezone.now().astimezone(fuseau_du_lieu).date()
            lundi_de_cette_semaine = aujourd_hui - datetime.timedelta(days=aujourd_hui.weekday())

            planning = PlanningBenevole.objects.create(
                name=f"TEST_benevolat semaines {identifiant}",
                slug=f"test-benevolat-semaines-{identifiant}",
                published=True,
            )
            tache = TacheBenevole.objects.create(name=f"TEST_benevolat bar {identifiant}")

            def semaine(nombre_de_semaines):
                return lundi_de_cette_semaine + datetime.timedelta(weeks=nombre_de_semaines)

            def besoin(une_date, nombre_souhaite=1):
                return BesoinBenevole.objects.create(
                    planning=planning, tache=tache, date=une_date,
                    heure_debut=datetime.time(18, 0), heure_fin=datetime.time(21, 0),
                    nombre_souhaite=nombre_souhaite,
                )

            yield SimpleNamespace(
                planning=planning, tache=tache, aujourd_hui=aujourd_hui,
                semaine=semaine, besoin=besoin,
            )


def adresse_du_planning(planning, semaine=None):
    adresse = f"/booking/benevolat/{planning.slug}/"
    if semaine is not None:
        adresse += f"?semaine={semaine}"
    return adresse


# ---------------------------------------------------------------------------
# Fonctions pures / Pure functions
# ---------------------------------------------------------------------------

LUNDI = datetime.date(2031, 10, 20)


def test_sans_semaine_demandee_c_est_la_semaine_du_prochain_besoin():
    from booking.benevolat import choisir_la_semaine

    dates_des_besoins = [LUNDI + datetime.timedelta(days=17), LUNDI + datetime.timedelta(days=30)]

    assert choisir_la_semaine(None, dates_des_besoins, LUNDI) == LUNDI + datetime.timedelta(days=14)


def test_un_dimanche_demande_donne_le_lundi_de_sa_semaine():
    from booking.benevolat import choisir_la_semaine

    dimanche_dans_deux_semaines = LUNDI + datetime.timedelta(days=20)

    assert choisir_la_semaine(dimanche_dans_deux_semaines, [], LUNDI) == LUNDI + datetime.timedelta(days=14)


def test_une_semaine_passee_demandee_retombe_sur_la_semaine_par_defaut():
    from booking.benevolat import choisir_la_semaine

    dates_des_besoins = [LUNDI + datetime.timedelta(days=9)]

    assert choisir_la_semaine(LUNDI - datetime.timedelta(days=1), dates_des_besoins, LUNDI) == LUNDI + datetime.timedelta(days=7)


def test_sans_aucun_besoin_c_est_la_semaine_en_cours():
    from booking.benevolat import choisir_la_semaine

    assert choisir_la_semaine(None, [], LUNDI) == LUNDI


def test_un_besoin_du_dimanche_soir_encore_en_cours_le_lundi_est_saute():
    """Le besoin d'hier (dimanche 21h → 0h30) est encore « à venir », mais sa semaine est passée."""
    from booking.benevolat import choisir_la_semaine

    dates_des_besoins = [LUNDI - datetime.timedelta(days=1), LUNDI + datetime.timedelta(days=3)]

    assert choisir_la_semaine(None, dates_des_besoins, LUNDI) == LUNDI


@pytest.mark.parametrize("texte", ["", None, "pas-une-date", "2031-13-40"])
def test_une_semaine_illisible_vaut_none(texte):
    from booking.benevolat import lire_la_semaine_demandee

    assert lire_la_semaine_demandee(texte) is None


def test_titre_de_la_semaine():
    from django.utils import translation

    from booking.benevolat import titre_de_la_semaine

    with translation.override("fr"):
        assert titre_de_la_semaine(datetime.date(2031, 10, 20)) == "20 – 26 octobre"
        assert titre_de_la_semaine(datetime.date(2031, 10, 27)) == "27 octobre – 2 novembre"
        assert titre_de_la_semaine(datetime.date(2029, 12, 31)) == "31 décembre 2029 – 6 janvier 2030"


# ---------------------------------------------------------------------------
# La page / The page
# ---------------------------------------------------------------------------

def test_la_page_montre_la_semaine_du_prochain_besoin_et_rien_d_autre(lieu):
    besoin_dans_deux_semaines = lieu.besoin(lieu.semaine(2) + datetime.timedelta(days=4))
    besoin_dans_trois_semaines = lieu.besoin(lieu.semaine(3))

    html = navigateur().get(adresse_du_planning(lieu.planning)).content.decode()

    assert str(besoin_dans_deux_semaines.pk) in html
    assert str(besoin_dans_trois_semaines.pk) not in html


def test_un_dimanche_dans_l_adresse_montre_toute_sa_semaine(lieu):
    lundi = lieu.semaine(2)
    besoin_du_lundi = lieu.besoin(lundi)
    besoin_du_dimanche = lieu.besoin(lundi + datetime.timedelta(days=6))
    besoin_de_la_semaine_d_apres = lieu.besoin(lundi + datetime.timedelta(days=7))

    dimanche = (lundi + datetime.timedelta(days=6)).isoformat()
    html = navigateur().get(adresse_du_planning(lieu.planning, dimanche)).content.decode()

    assert str(besoin_du_lundi.pk) in html
    assert str(besoin_du_dimanche.pk) in html
    assert str(besoin_de_la_semaine_d_apres.pk) not in html


@pytest.mark.parametrize("valeur", ["n-importe-quoi", "2020-01-06"])
def test_une_semaine_illisible_ou_passee_donne_la_semaine_par_defaut(lieu, valeur):
    premier_besoin = lieu.besoin(lieu.semaine(1))
    besoin_plus_tard = lieu.besoin(lieu.semaine(4))

    reponse = navigateur().get(adresse_du_planning(lieu.planning, valeur))

    assert reponse.status_code == 200
    html = reponse.content.decode()
    assert str(premier_besoin.pk) in html
    assert str(besoin_plus_tard.pk) not in html


def test_pas_de_semaine_precedente_sur_la_semaine_en_cours(lieu):
    lieu.besoin(lieu.semaine(1))

    html = navigateur().get(adresse_du_planning(lieu.planning, lieu.semaine(0).isoformat())).content.decode()

    assert 'data-testid="benevolat-semaine-precedente"' not in html
    assert 'data-testid="benevolat-semaine-suivante"' in html
    assert f"?semaine={lieu.semaine(1).isoformat()}" in html


def test_pas_de_semaine_suivante_apres_le_dernier_besoin(lieu):
    lieu.besoin(lieu.semaine(1))
    lieu.besoin(lieu.semaine(2))

    html = navigateur().get(adresse_du_planning(lieu.planning, lieu.semaine(2).isoformat())).content.decode()

    assert 'data-testid="benevolat-semaine-suivante"' not in html
    assert 'data-testid="benevolat-semaine-precedente"' in html
    assert f"?semaine={lieu.semaine(1).isoformat()}" in html
    # Les liens de semaine rechargent la zone en htmx et changent l'adresse.
    # / Week links reload the zone with htmx and update the address.
    assert 'hx-push-url="true"' in html


def test_une_semaine_sans_besoin_entre_deux_le_dit(lieu):
    lieu.besoin(lieu.semaine(1))
    lieu.besoin(lieu.semaine(3))

    html = navigateur().get(adresse_du_planning(lieu.planning, lieu.semaine(2).isoformat())).content.decode()

    assert 'data-testid="benevolat-semaine-vide"' in html
    assert 'data-testid="benevolat-semaine-suivante"' in html


def test_le_compteur_porte_sur_tout_le_planning(lieu):
    """Deux besoins de 2 places, dans deux semaines différentes : le compteur dit « 0 / 4 »."""
    lieu.besoin(lieu.semaine(1), nombre_souhaite=2)
    lieu.besoin(lieu.semaine(2), nombre_souhaite=2)

    html = navigateur().get(adresse_du_planning(lieu.planning)).content.decode()

    assert "<b>0</b> / 4 places couvertes" in html
    assert "<b>2</b> créneaux encore vides" in html


def test_la_zone_seule_pour_htmx_qui_cible_la_zone(lieu):
    lieu.besoin(lieu.semaine(1))

    html_de_la_zone = navigateur(HTTP_HX_REQUEST="true", HTTP_HX_TARGET="benevolat-planning").get(
        adresse_du_planning(lieu.planning)
    ).content.decode()
    html_autre_cible = navigateur(HTTP_HX_REQUEST="true", HTTP_HX_TARGET="contenu").get(
        adresse_du_planning(lieu.planning)
    ).content.decode()

    assert 'id="benevolat-planning"' in html_de_la_zone
    assert 'data-testid="benevolat-page"' not in html_de_la_zone
    assert 'data-testid="benevolat-page"' in html_autre_cible


# ---------------------------------------------------------------------------
# Après une action : la semaine du besoin / After an action: the need's week
# ---------------------------------------------------------------------------

def test_je_viens_rend_la_semaine_du_besoin(lieu):
    lieu.besoin(lieu.semaine(1))
    besoin_lointain = lieu.besoin(lieu.semaine(3) + datetime.timedelta(days=2))

    reponse = navigateur(creer_utilisateur()).post(f"/booking/benevolat/besoin/{besoin_lointain.pk}/inscrire/")

    assert reponse.status_code == 200
    html = reponse.content.decode()
    assert f'data-testid="benevolat-besoin-{besoin_lointain.pk}"' in html
    assert f"?semaine={lieu.semaine(2).isoformat()}" in html


def test_me_retirer_rend_la_semaine_du_besoin(lieu):
    from booking.models import InscriptionBenevole

    lieu.besoin(lieu.semaine(1))
    besoin_lointain = lieu.besoin(lieu.semaine(4))
    camille = creer_utilisateur()
    InscriptionBenevole.objects.create(besoin=besoin_lointain, user=camille)

    reponse = navigateur(camille).post(f"/booking/benevolat/besoin/{besoin_lointain.pk}/retirer/")

    assert reponse.status_code == 200
    assert f'data-testid="benevolat-besoin-{besoin_lointain.pk}"' in reponse.content.decode()


def test_un_besoin_passe_rend_422_avec_la_semaine_par_defaut(lieu):
    besoin_passe = lieu.besoin(lieu.semaine(-2))
    prochain_besoin = lieu.besoin(lieu.semaine(1))

    reponse = navigateur(creer_utilisateur()).post(f"/booking/benevolat/besoin/{besoin_passe.pk}/inscrire/")

    assert reponse.status_code == 422
    assert f'data-testid="benevolat-besoin-{prochain_besoin.pk}"' in reponse.content.decode()


# ---------------------------------------------------------------------------
# Coût de la page / Page cost
# ---------------------------------------------------------------------------

def test_requetes_et_lectures_de_configuration_constantes(lieu):
    """
    10 ou 300 besoins (dont la moitié dans la semaine affichée, tous avec une inscription
    de la personne connectée) : le même nombre de requêtes SQL et de lectures de la
    Configuration (un aller-retour au cache chacune).
    / 10 or 300 needs: same SQL query count and same Configuration reads.
    """
    from BaseBillet.models import Configuration
    from booking.models import BesoinBenevole, InscriptionBenevole

    camille = creer_utilisateur()
    client = navigateur(camille)

    def cout_de_la_page(nombre_de_besoins):
        BesoinBenevole.objects.filter(planning=lieu.planning).delete()
        nouveaux_besoins = []
        for numero in range(nombre_de_besoins):
            # La moitié en semaine + 1, l'autre en semaine + 2.
            # / Half in week + 1, the other half in week + 2.
            numero_de_semaine = 1 + (numero % 2)
            nouveaux_besoins.append(BesoinBenevole(
                planning=lieu.planning, tache=lieu.tache,
                date=lieu.semaine(numero_de_semaine) + datetime.timedelta(days=numero % 7),
                heure_debut=datetime.time(18, 0), heure_fin=datetime.time(21, 0),
            ))
        BesoinBenevole.objects.bulk_create(nouveaux_besoins)
        InscriptionBenevole.objects.bulk_create(
            [InscriptionBenevole(besoin=besoin, user=camille) for besoin in nouveaux_besoins]
        )

        with mock.patch.object(Configuration, "get_solo", wraps=Configuration.get_solo) as lectures_de_la_configuration:
            with CaptureQueriesContext(connection) as requetes:
                reponse = client.get(adresse_du_planning(lieu.planning))
        assert reponse.status_code == 200
        assert f"?semaine={lieu.semaine(2).isoformat()}" in reponse.content.decode()
        return len(requetes), lectures_de_la_configuration.call_count

    cout_de_la_page(10)  # chauffe les caches / warms the caches
    assert cout_de_la_page(300) == cout_de_la_page(10)
