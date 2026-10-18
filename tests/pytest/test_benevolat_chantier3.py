"""
Tests du chantier 3 du bénévolat : « Mes créneaux », le bloc d'accueil « Coups de main »,
et la lettre d'information.
/ Volunteering step 3 tests: "My shifts", the "Coups de main" home block, the newsletter.

LOCALISATION : tests/pytest/test_benevolat_chantier3.py

Code testé / Tested code :
- BaseBillet/views.py (MyAccount.my_volunteering), booking/benevolat.py (mes_creneaux_a_venir,
  resumes_des_plannings_a_venir), pages/templatetags/pages_tags.py (plannings_benevoles_a_venir)
- booking/views_benevolat.py (lettre, retirer depuis « Mes créneaux »)
- BaseBillet/tasks.py (send_to_ghost_email, paramètre etiquettes_en_plus)
Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§5.1, §5.5, §5.8)

Chaque test est marqué `django_db` : transaction annulée à la fin, rien ne reste en base.
INDISPENSABLE : on ne modifie jamais GhostConfig en base. get_solo() met la valeur en
cache (SOLO_CACHE), et l'annulation de la transaction ne vide pas ce cache : un Ghost
« configuré » resterait visible des tests suivants. On simule à la place.
/ Never write GhostConfig: get_solo() caches it and the rollback would not clear the cache.

Lancer / Run : make test ARGS="tests/pytest/test_benevolat_chantier3.py"
"""

import copy
import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context

from fabriques_panier import creer_utilisateur, identifiant_unique

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les tâches et signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5)."""
    from django.utils import translation

    yield
    translation.deactivate()


def page_mes_creneaux(utilisateur):
    """
    GET /my_account/my_volunteering/. MyAccount.dispatch crée le portefeuille Fedow d'un
    compte qui n'en a pas, par HTTP : on simule FedowAPI (même parade que
    tests/pytest/test_mon_espace_v2_boutons_qrcode.py).
    / MyAccount.dispatch calls Fedow over HTTP for wallet-less accounts: faked here.
    """
    with patch("BaseBillet.views.FedowAPI", return_value=MagicMock()):
        return navigateur(utilisateur).get("/my_account/my_volunteering/")


def navigateur(utilisateur=None):
    """Client de test sur `lespass`, en français. / Test client on `lespass`, in French."""
    client = Client(HTTP_HOST="lespass.tibillet.localhost", HTTP_ACCEPT_LANGUAGE="fr")
    if utilisateur is not None:
        client.force_login(utilisateur)
    return client


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, sa date du jour (fuseau du lieu), et une fabrique de plannings.
    / The `lespass` venue, today's date, and a planning factory.
    """
    from BaseBillet.models import Configuration

    with tenant_context(tenant):
        fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        yield SimpleNamespace(aujourd_hui=timezone.now().astimezone(fuseau_du_lieu).date())


def creer_un_planning(dans_combien_de_jours, publie=True, nombre_souhaite=2, jours=None):
    """
    Un planning, une tâche, et un besoin par jour demandé (18h–21h).
    `jours` : liste de décalages en jours ; par défaut, un seul besoin.
    Rend (planning, liste des besoins).
    """
    from BaseBillet.models import Configuration
    from booking.models import BesoinBenevole, PlanningBenevole, TacheBenevole

    fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
    aujourd_hui = timezone.now().astimezone(fuseau_du_lieu).date()
    identifiant = identifiant_unique()
    planning = PlanningBenevole.objects.create(
        name=f"TEST_benevolat planning {identifiant}",
        slug=f"test-benevolat-{identifiant}",
        published=publie,
    )
    tache = TacheBenevole.objects.create(name=f"TEST_benevolat bar {identifiant}")
    besoins = []
    for decalage in jours or [dans_combien_de_jours]:
        besoins.append(BesoinBenevole.objects.create(
            planning=planning, tache=tache,
            date=aujourd_hui + datetime.timedelta(days=decalage),
            heure_debut=datetime.time(18, 0), heure_fin=datetime.time(21, 0),
            nombre_souhaite=nombre_souhaite,
        ))
    return planning, besoins


# ---------------------------------------------------------------------------
# « Mes créneaux » (§5.5) / "My shifts"
# ---------------------------------------------------------------------------

def test_mes_creneaux_liste_mes_inscriptions_a_venir_seulement(lieu):
    """
    À venir et sur un planning publié : affiché. Passé, sur un planning dépublié, ou
    l'inscription d'une autre personne : absent.
    """
    from booking.models import InscriptionBenevole

    camille = creer_utilisateur(prenom="Camille", nom="Martin")
    leo = creer_utilisateur()
    _planning, (besoin_a_venir,) = creer_un_planning(3)
    _planning, (besoin_passe,) = creer_un_planning(-2)
    _planning, (besoin_depublie,) = creer_un_planning(4, publie=False)
    _planning, (besoin_de_leo,) = creer_un_planning(5)
    for besoin in [besoin_a_venir, besoin_passe, besoin_depublie]:
        InscriptionBenevole.objects.create(besoin=besoin, user=camille)
    InscriptionBenevole.objects.create(besoin=besoin_de_leo, user=leo)

    reponse = page_mes_creneaux(camille)

    assert reponse.status_code == 200
    html = reponse.content.decode()
    assert f'data-testid="benevolat-mon-creneau-{besoin_a_venir.pk}"' in html
    assert str(besoin_passe.pk) not in html
    assert str(besoin_depublie.pk) not in html
    assert str(besoin_de_leo.pk) not in html


def test_mes_creneaux_anonyme_est_renvoye_a_l_accueil(lieu):
    reponse = navigateur().get("/my_account/my_volunteering/")
    assert reponse.status_code in (302, 403)


def test_mes_creneaux_apres_le_delai_affiche_je_ne_peux_plus_venir(lieu):
    from booking.models import InscriptionBenevole

    camille = creer_utilisateur()
    planning, (besoin,) = creer_un_planning(3)
    planning.delai_desinscription_heures = 500
    planning.save()
    InscriptionBenevole.objects.create(besoin=besoin, user=camille)

    html = page_mes_creneaux(camille).content.decode()

    assert "Je ne peux plus venir" in html


def test_se_retirer_depuis_mes_creneaux_rend_une_reponse_vide(lieu):
    """depuis=mes_creneaux : la réponse est vide (la ligne disparaît) et porte le toast."""
    from booking.models import InscriptionBenevole

    camille = creer_utilisateur()
    _planning, (besoin,) = creer_un_planning(3)
    InscriptionBenevole.objects.create(besoin=besoin, user=camille)

    reponse = navigateur(camille).post(
        f"/booking/benevolat/besoin/{besoin.pk}/retirer/", {"depuis": "mes_creneaux"},
    )

    assert reponse.status_code == 200
    assert reponse.content == b""
    assert "appToast" in reponse["HX-Trigger"]
    assert not InscriptionBenevole.objects.filter(besoin=besoin, user=camille).exists()


# ---------------------------------------------------------------------------
# Bloc d'accueil « Coups de main » (§5.1) / Home block
# ---------------------------------------------------------------------------

def test_le_bloc_ne_montre_que_les_plannings_publies_avec_un_besoin_a_venir(lieu):
    from pages.templatetags.pages_tags import plannings_benevoles_a_venir

    planning_dans_10_jours, _besoins = creer_un_planning(10)
    planning_dans_2_jours, _besoins = creer_un_planning(2, jours=[2, 4, 6, 8, 10, 12])
    planning_depublie, _besoins = creer_un_planning(1, publie=False)
    planning_passe, _besoins = creer_un_planning(-3)

    resumes = plannings_benevoles_a_venir(50)
    plannings_affiches = [resume["planning"] for resume in resumes]

    assert planning_depublie not in plannings_affiches
    assert planning_passe not in plannings_affiches
    # Le plus proche d'abord / Nearest first
    assert plannings_affiches.index(planning_dans_2_jours) < plannings_affiches.index(planning_dans_10_jours)

    resume_du_planning_long = resumes[plannings_affiches.index(planning_dans_2_jours)]
    assert len(resume_du_planning_long["jours"]) == 5
    assert resume_du_planning_long["places_libres"] == 12


def test_le_bloc_respecte_nombre_max(lieu):
    from pages.templatetags.pages_tags import plannings_benevoles_a_venir

    for decalage in [1, 2, 3]:
        creer_un_planning(decalage)

    assert len(plannings_benevoles_a_venir(2)) == 2


def rendre_hebdomadaire(planning):
    """Passe le planning en « chaque semaine ». / Makes the planning weekly."""
    from booking.models import PlanningBenevole

    planning.type_de_planning = PlanningBenevole.HEBDOMADAIRE
    planning.save()


def resume_du_planning(planning):
    """Le résumé de ce planning dans le bloc, ou None. / This planning's card data, or None."""
    from pages.templatetags.pages_tags import plannings_benevoles_a_venir

    for resume in plannings_benevoles_a_venir(50):
        if resume["planning"] == planning:
            return resume
    return None


def test_le_bloc_compte_les_places_d_un_planning_chaque_semaine_sur_10_jours(lieu):
    """Chaque semaine, besoins à J+2 et J+12 (2 places chacun) : seul J+2 compte."""
    planning, _besoins = creer_un_planning(2, jours=[2, 12])
    rendre_hebdomadaire(planning)

    assert resume_du_planning(planning)["places_libres"] == 2


def test_le_bloc_cache_un_planning_chaque_semaine_sans_besoin_dans_10_jours(lieu):
    """Chaque semaine, premier besoin à J+12 : pas de carte (pas de « tout est couvert » faux)."""
    planning, _besoins = creer_un_planning(12)
    rendre_hebdomadaire(planning)

    assert resume_du_planning(planning) is None


def test_le_bloc_compte_toutes_les_places_d_un_planning_ponctuel(lieu):
    """Ponctuel, besoins à J+2 et J+40 : toutes les places comptent, même loin."""
    planning, _besoins = creer_un_planning(2, jours=[2, 40])

    assert resume_du_planning(planning)["places_libres"] == 4


def test_un_creneau_a_remplir_est_un_besoin_qui_a_encore_une_place(lieu):
    """
    3 besoins de 2 places, dont un complet : 2 créneaux à remplir, 4 places libres.
    / 3 needs of 2 places, one full: 2 slots to fill, 4 free places.
    """
    from booking.models import InscriptionBenevole

    planning, besoins = creer_un_planning(2, jours=[2, 3, 4])
    besoin_complet = besoins[0]
    InscriptionBenevole.objects.create(besoin=besoin_complet, user=creer_utilisateur())
    InscriptionBenevole.objects.create(besoin=besoin_complet, user=creer_utilisateur())

    resume = resume_du_planning(planning)

    assert resume["creneaux_a_remplir"] == 2
    assert resume["places_libres"] == 4


def test_la_page_liste_montre_un_planning_chaque_semaine_meme_au_dela_de_10_jours(lieu):
    """
    La page /booking/benevolat/ n'a pas d'horizon : un planning chaque semaine dont le
    premier besoin est à J+14 (lieu fermé deux semaines) y reste.
    / The list page has no horizon: a weekly planning starting at D+14 stays listed.
    """
    planning, _besoins = creer_un_planning(14)
    rendre_hebdomadaire(planning)

    html = navigateur().get("/booking/benevolat/").content.decode()

    assert f"/booking/benevolat/{planning.slug}/" in html


def test_le_bloc_est_vide_sur_le_schema_public():
    """`pages` est aussi en SHARED_APPS : sur public, les tables du bénévolat n'existent pas."""
    from django_tenants.utils import schema_context

    from pages.templatetags.pages_tags import plannings_benevoles_a_venir

    with schema_context("public"):
        assert plannings_benevoles_a_venir(6) == []


def test_la_carte_du_bloc_affiche_nom_periode_et_places(lieu):
    from django.template.loader import render_to_string

    from pages.templatetags.pages_tags import plannings_benevoles_a_venir

    planning, _besoins = creer_un_planning(2, jours=[2, 5], nombre_souhaite=3)
    resumes = [resume for resume in plannings_benevoles_a_venir(50) if resume["planning"] == planning]

    html = render_to_string(
        "booking/benevolat/partials/cartes_accueil.html", {"plannings": resumes},
    )

    assert planning.name in html
    # 2 besoins de 3 places : 2 créneaux (pas 6, qui serait le nombre de places).
    # / 2 needs of 3 places: 2 slots (not 6, the number of places).
    assert "2 créneaux libres" in html
    assert f"/booking/benevolat/{planning.slug}/" in html


def test_la_carte_d_un_planning_chaque_semaine_annonce_les_creneaux_a_remplir(lieu):
    """Chaque semaine, un besoin à J+2 : « Ces prochains jours, on a besoin de remplir 1 créneau »."""
    from django.template.loader import render_to_string

    planning, _besoins = creer_un_planning(2)
    rendre_hebdomadaire(planning)

    html = render_to_string(
        "booking/benevolat/partials/cartes_accueil.html",
        {"plannings": [resume_du_planning(planning)]},
    )

    assert "Ces prochains jours, on a besoin de remplir 1 créneau" in html
    assert "créneau libre" not in html


def accueil_v2(configuration=None):
    """
    GET / sur `lespass`, skin V2 forcé (accueil codé en dur, pages/V2/vues/accueil.html).
    `configuration` : une copie modifiée de Configuration, pour simuler un module éteint.
    / GET / on `lespass` with the V2 skin forced; optional patched configuration.

    Une page d'accueil CMS publiée remplacerait l'accueil codé en dur (BaseBillet/views.py,
    index) : on les dépublie, la transaction du test annule le changement.
    / A published CMS home page would replace the hardcoded home: unpublished here.
    """
    from pages.models import Page

    Page.objects.filter(est_accueil=True, publie=True).update(publie=False)
    with patch("BaseBillet.views.get_skin_courant", return_value="V2"):
        if configuration is None:
            return navigateur().get("/").content.decode()
        with patch("BaseBillet.models.Configuration.get_solo", return_value=configuration):
            return navigateur().get("/").content.decode()


def test_l_accueil_v2_montre_les_coups_de_main_a_venir(lieu):
    """Un planning publié avec un besoin dans 1 jour : sa carte est sur l'accueil."""
    planning, _besoins = creer_un_planning(1)

    html = accueil_v2()

    assert 'data-testid="accueil-benevolat"' in html
    assert f"/booking/benevolat/{planning.slug}/" in html


def test_l_accueil_v2_cache_les_coups_de_main_module_eteint(lieu):
    """Module bénévolat éteint : pas de section, même avec un planning à venir."""
    from BaseBillet.models import Configuration

    creer_un_planning(1)
    # Cas positif d'abord : sans lui, le test passerait à vide si le module était déjà
    # éteint en base. / Positive case first, or the test could pass vacuously.
    assert 'data-testid="accueil-benevolat"' in accueil_v2()

    configuration_eteinte = copy.copy(Configuration.get_solo())
    configuration_eteinte.module_benevolat = False

    html = accueil_v2(configuration_eteinte)

    assert 'data-testid="accueil-benevolat"' not in html


def test_la_source_coups_de_main_est_un_choix_du_bloc():
    from pages.models import Bloc

    assert Bloc.COUPS_DE_MAIN in [valeur for valeur, _libelle in Bloc.SOURCE_CHOICES]


# ---------------------------------------------------------------------------
# Lettre d'information (§5.8) / Newsletter
# ---------------------------------------------------------------------------

def test_lettre_active_seulement_avec_adresse_et_cle_ghost():
    from booking.views_benevolat import lettre_d_information_active

    cas = [
        ({"ghost_url": "https://ghost.exemple", "ghost_key": "chiffree"}, True),
        ({"ghost_url": "https://ghost.exemple", "ghost_key": None}, False),
        ({"ghost_url": None, "ghost_key": "chiffree"}, False),
    ]
    for champs, attendu in cas:
        with patch("booking.views_benevolat.GhostConfig.get_solo", return_value=SimpleNamespace(**champs)):
            assert lettre_d_information_active() is attendu, champs


def test_le_bloc_lettre_absent_si_ghost_n_est_pas_configure(lieu):
    planning, _besoins = creer_un_planning(3)

    with patch("booking.views_benevolat.lettre_d_information_active", return_value=False):
        html = navigateur().get(f"/booking/benevolat/{planning.slug}/").content.decode()
        reponse_du_post = navigateur().post(
            f"/booking/benevolat/{planning.slug}/lettre/", {"email": "a@exemple.org"},
        )

    assert 'data-testid="benevolat-lettre"' not in html
    assert reponse_du_post.status_code == 404


def test_lettre_connecte_envoie_l_email_le_nom_et_l_etiquette(lieu):
    planning, _besoins = creer_un_planning(3)
    camille = creer_utilisateur(prenom="Camille", nom="Martin")

    with patch("booking.views_benevolat.lettre_d_information_active", return_value=True), \
            patch("booking.views_benevolat.send_to_ghost_email") as tache_ghost:
        html_de_la_page = navigateur(camille).get(f"/booking/benevolat/{planning.slug}/").content.decode()
        reponse = navigateur(camille).post(
            f"/booking/benevolat/{planning.slug}/lettre/", {"email": "camille@exemple.org"},
        )

    assert f'value="{camille.email}"' in html_de_la_page
    assert reponse.status_code == 200
    assert "camille@exemple.org recevra la lettre" in reponse.content.decode()
    tache_ghost.delay.assert_called_once_with(
        "camille@exemple.org", "Camille Martin", etiquettes_en_plus=["Bénévolat"],
    )


def test_lettre_anonyme_envoie_un_nom_vide(lieu):
    planning, _besoins = creer_un_planning(3)

    with patch("booking.views_benevolat.lettre_d_information_active", return_value=True), \
            patch("booking.views_benevolat.send_to_ghost_email") as tache_ghost:
        reponse = navigateur().post(
            f"/booking/benevolat/{planning.slug}/lettre/", {"email": "x@exemple.org"},
        )

    assert reponse.status_code == 200
    tache_ghost.delay.assert_called_once_with("x@exemple.org", "", etiquettes_en_plus=["Bénévolat"])


@pytest.mark.parametrize("email", ["", "pas-un-email"])
def test_lettre_email_invalide_rend_422_sans_rien_envoyer(lieu, email):
    planning, _besoins = creer_un_planning(3)

    with patch("booking.views_benevolat.lettre_d_information_active", return_value=True), \
            patch("booking.views_benevolat.send_to_ghost_email") as tache_ghost:
        reponse = navigateur().post(f"/booking/benevolat/{planning.slug}/lettre/", {"email": email})

    assert reponse.status_code == 422
    assert 'aria-invalid="true"' in reponse.content.decode()
    tache_ghost.delay.assert_not_called()


# ---------------------------------------------------------------------------
# send_to_ghost_email : étiquettes en plus / extra labels (Ghost simulé)
# ---------------------------------------------------------------------------

def reponse_http(status_code, json_renvoye=None):
    reponse = MagicMock()
    reponse.status_code = status_code
    reponse.ok = 200 <= status_code < 300
    reponse.json.return_value = json_renvoye or {}
    reponse.text = ""
    return reponse


@pytest.fixture
def ghost_simule():
    """
    Un Ghost configuré, et les appels HTTP de la tâche interceptés.
    / A configured Ghost, with the task's HTTP calls intercepted.
    """
    config = MagicMock(ghost_url="https://ghost.exemple")
    config.get_api_key.return_value = "identifiant:00ff00ff"
    with patch("BaseBillet.tasks.GhostConfig.get_solo", return_value=config), \
            patch("BaseBillet.tasks.requests") as requetes:
        yield requetes


def test_ghost_sans_etiquette_en_plus_garde_les_etiquettes_d_avant(ghost_simule):
    from BaseBillet.tasks import send_to_ghost_email

    ghost_simule.get.return_value = reponse_http(200, {"members": []})
    ghost_simule.post.return_value = reponse_http(201, {"members": [{}]})

    send_to_ghost_email("a@exemple.org", "A")

    etiquettes = ghost_simule.post.call_args.kwargs["json"]["members"][0]["labels"]
    assert etiquettes[0] == "TiBillet"
    assert len(etiquettes) == 2
    ghost_simule.put.assert_not_called()


def test_ghost_nouveau_membre_recoit_l_etiquette_benevolat(ghost_simule):
    from BaseBillet.tasks import send_to_ghost_email

    ghost_simule.get.return_value = reponse_http(200, {"members": []})
    ghost_simule.post.return_value = reponse_http(201, {"members": [{}]})

    send_to_ghost_email("a@exemple.org", "A", etiquettes_en_plus=["Bénévolat"])

    etiquettes = ghost_simule.post.call_args.kwargs["json"]["members"][0]["labels"]
    assert "Bénévolat" in etiquettes
    assert "TiBillet" in etiquettes


def test_ghost_membre_existant_sans_l_etiquette_recoit_un_put(ghost_simule):
    from BaseBillet.tasks import send_to_ghost_email

    membre = {"id": "m1", "labels": [{"name": "TiBillet"}]}
    ghost_simule.get.return_value = reponse_http(200, {"members": [membre]})
    ghost_simule.put.return_value = reponse_http(200)

    send_to_ghost_email("a@exemple.org", "A", etiquettes_en_plus=["Bénévolat"])

    ghost_simule.put.assert_called_once()
    assert ghost_simule.put.call_args.args[0] == "https://ghost.exemple/ghost/api/admin/members/m1/"
    assert ghost_simule.put.call_args.kwargs["json"] == {"members": [{"labels": ["TiBillet", "Bénévolat"]}]}
    ghost_simule.post.assert_not_called()


def test_ghost_membre_qui_a_deja_l_etiquette_n_est_pas_touche(ghost_simule):
    from BaseBillet.tasks import send_to_ghost_email

    membre = {"id": "m1", "labels": [{"name": "TiBillet"}, {"name": "Bénévolat"}]}
    ghost_simule.get.return_value = reponse_http(200, {"members": [membre]})

    send_to_ghost_email("a@exemple.org", "A", etiquettes_en_plus=["Bénévolat"])

    ghost_simule.put.assert_not_called()


# ---------------------------------------------------------------------------
# Relecture du 2026-10-16 / 2026-10-16 review
# ---------------------------------------------------------------------------

def test_lettre_post_anonyme_sans_jeton_csrf_refuse(lieu):
    planning, _besoins = creer_un_planning(3)
    client_strict = Client(HTTP_HOST="lespass.tibillet.localhost", enforce_csrf_checks=True)

    with patch("booking.views_benevolat.lettre_d_information_active", return_value=True), \
            patch("booking.views_benevolat.send_to_ghost_email") as tache_ghost:
        reponse = client_strict.post(f"/booking/benevolat/{planning.slug}/lettre/", {"email": "a@exemple.org"})

    assert reponse.status_code == 403
    tache_ghost.delay.assert_not_called()


def test_mes_creneaux_retrait_apres_le_delai_previent_l_equipe(lieu, django_capture_on_commit_callbacks):
    from booking.models import InscriptionBenevole

    camille = creer_utilisateur()
    planning, (besoin,) = creer_un_planning(3)
    planning.delai_desinscription_heures = 500
    planning.save()
    inscription = InscriptionBenevole.objects.create(besoin=besoin, user=camille)
    InscriptionBenevole.objects.filter(pk=inscription.pk).update(
        created_at=timezone.now() - datetime.timedelta(days=30),
    )

    html = page_mes_creneaux(camille).content.decode()
    with patch("booking.tasks.prevenir_l_equipe_d_un_desistement") as alerte_equipe:
        with django_capture_on_commit_callbacks(execute=True):
            navigateur(camille).post(f"/booking/benevolat/besoin/{besoin.pk}/retirer/", {"depuis": "mes_creneaux"})

    assert "hx-confirm=" in html
    alerte_equipe.delay.assert_called_once()


def test_mes_creneaux_retrait_d_un_besoin_passe_rend_422_vide(lieu):
    from booking.models import InscriptionBenevole

    camille = creer_utilisateur()
    _planning, (besoin,) = creer_un_planning(-2)
    InscriptionBenevole.objects.create(besoin=besoin, user=camille)

    reponse = navigateur(camille).post(f"/booking/benevolat/besoin/{besoin.pk}/retirer/", {"depuis": "mes_creneaux"})

    assert reponse.status_code == 422
    assert reponse.content == b""
    assert InscriptionBenevole.objects.filter(besoin=besoin, user=camille).exists()


def test_la_page_publique_reste_servie_module_eteint(lieu):
    """P7 : le module ne règle que les menus ; la page publique ne le vérifie pas."""
    from BaseBillet.models import Configuration

    planning, _besoins = creer_un_planning(3)
    configuration_eteinte = copy.copy(Configuration.get_solo())
    configuration_eteinte.module_benevolat = False

    with patch("BaseBillet.models.Configuration.get_solo", return_value=configuration_eteinte):
        reponse = navigateur().get(f"/booking/benevolat/{planning.slug}/")

    assert reponse.status_code == 200
