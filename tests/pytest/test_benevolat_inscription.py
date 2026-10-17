"""
Tests de la page publique d'un planning de bénévoles, de l'inscription et du retrait.
/ Tests of the volunteer planning public page, sign-up and withdrawal.

LOCALISATION : tests/pytest/test_benevolat_inscription.py

Code testé / Tested code : booking/views_benevolat.py, booking/benevolat.py
Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§5.2 à §5.4, §8)

Chaque test est marqué `django_db` : transaction annulée à la fin, rien ne reste en base.
Les mails partent après le commit (transaction.on_commit) : les tests qui les vérifient
exécutent ces rappels avec `django_capture_on_commit_callbacks(execute=True)`, et
`taches_celery_enregistrees` intercepte les .delay() sans worker.
/ Mails are sent on commit: tests run those callbacks explicitly.

Lancer / Run : make test ARGS="tests/pytest/test_benevolat_inscription.py"
"""

import datetime
from types import SimpleNamespace

import pytest
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context

from fabriques_panier import (
    creer_adhesion,
    creer_une_adhesion_active,
    creer_utilisateur,
    identifiant_unique,
    noms_des_taches,
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


def navigateur(utilisateur=None):
    """
    Client de test sur le lieu `lespass`, en français : les textes source des gabarits
    du bénévolat sont en français.
    / Test client on `lespass`, in French (the volunteering source strings are French).
    """
    client = Client(HTTP_HOST="lespass.tibillet.localhost", HTTP_ACCEPT_LANGUAGE="fr")
    if utilisateur is not None:
        client.force_login(utilisateur)
    return client


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass` avec un planning publié, une tâche et un besoin dans 5 jours
    (18h–21h, 1 personne souhaitée). Celery est intercepté.
    / The `lespass` venue with a published planning, a task and a need in 5 days.
    """
    from BaseBillet.models import Configuration
    from booking.models import BesoinBenevole, PlanningBenevole, TacheBenevole

    with tenant_context(tenant):
        with taches_celery_enregistrees() as taches_demandees:
            identifiant = identifiant_unique()
            fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
            aujourd_hui = timezone.now().astimezone(fuseau_du_lieu).date()

            planning = PlanningBenevole.objects.create(
                name=f"TEST_benevolat planning {identifiant}",
                slug=f"test-benevolat-{identifiant}",
                published=True,
            )
            tache = TacheBenevole.objects.create(name=f"TEST_benevolat bar {identifiant}")
            besoin = BesoinBenevole.objects.create(
                planning=planning,
                tache=tache,
                date=aujourd_hui + datetime.timedelta(days=5),
                heure_debut=datetime.time(18, 0),
                heure_fin=datetime.time(21, 0),
                nombre_souhaite=1,
            )
            yield SimpleNamespace(
                planning=planning,
                tache=tache,
                besoin=besoin,
                aujourd_hui=aujourd_hui,
                taches_demandees=taches_demandees,
            )


def adresse_du_planning(planning):
    return f"/booking/benevolat/{planning.slug}/"


def adresse_inscrire(besoin):
    return f"/booking/benevolat/besoin/{besoin.pk}/inscrire/"


def adresse_retirer(besoin):
    return f"/booking/benevolat/besoin/{besoin.pk}/retirer/"


# ---------------------------------------------------------------------------
# Fonction pure : taux de remplissage / Pure function: fill rate
# ---------------------------------------------------------------------------

class FauxBesoin:
    """Un besoin sans base : seulement ce que taux_de_remplissage lit."""

    def __init__(self, nombre_souhaite, nombre_inscrits):
        self.nombre_souhaite = nombre_souhaite
        self._nombre_inscrits = nombre_inscrits

    def places_couvertes(self):
        return min(self._nombre_inscrits, self.nombre_souhaite)


@pytest.mark.parametrize(
    "besoins, taux_attendu",
    [
        ([FauxBesoin(2, 0), FauxBesoin(1, 0)], 0),
        ([FauxBesoin(2, 1), FauxBesoin(2, 2)], 75),
        ([FauxBesoin(2, 2), FauxBesoin(1, 1)], 100),
        # Les renforts ne font pas dépasser 100 / Extras never exceed 100
        ([FauxBesoin(2, 5)], 100),
        ([FauxBesoin(2, 5), FauxBesoin(2, 0)], 50),
        ([], 100),
    ],
)
def test_taux_de_remplissage(besoins, taux_attendu):
    from booking.benevolat import taux_de_remplissage

    assert taux_de_remplissage(besoins) == taux_attendu


# ---------------------------------------------------------------------------
# Page publique / Public page
# ---------------------------------------------------------------------------

def test_la_page_est_publique_et_n_affiche_jamais_d_email(lieu):
    """
    Anonyme : la page s'affiche, le prénom est visible, l'email jamais ; un compte sans
    prénom s'affiche « Bénévole ».
    / Anonymous: page shown, first name visible, never the email; no first name → "Bénévole".
    """
    from booking.models import BesoinBenevole, InscriptionBenevole

    camille = creer_utilisateur(prenom="Camille", nom="Martin")
    sans_prenom = creer_utilisateur(prenom="", nom="Dupont")
    autre_besoin = BesoinBenevole.objects.create(
        planning=lieu.planning, tache=lieu.tache, date=lieu.besoin.date, nombre_souhaite=3,
    )
    InscriptionBenevole.objects.create(besoin=lieu.besoin, user=camille)
    InscriptionBenevole.objects.create(besoin=autre_besoin, user=sans_prenom)

    reponse = navigateur().get(adresse_du_planning(lieu.planning))

    assert reponse.status_code == 200
    html = reponse.content.decode()
    assert "Camille" in html
    assert "Bénévole" in html
    assert camille.email not in html
    assert sans_prenom.email not in html
    assert "Martin" not in html
    assert "Dupont" not in html


def test_un_planning_non_publie_est_introuvable(lieu):
    lieu.planning.published = False
    lieu.planning.save()

    reponse = navigateur().get(adresse_du_planning(lieu.planning))

    assert reponse.status_code == 404


def test_anonyme_sur_un_besoin_couvert_voit_couvert_et_me_connecter(lieu):
    """D22 : badge « Couvert » + « Me connecter pour venir », pas de « Je viens »."""
    from booking.models import InscriptionBenevole

    InscriptionBenevole.objects.create(besoin=lieu.besoin, user=creer_utilisateur())

    html = navigateur().get(adresse_du_planning(lieu.planning)).content.decode()

    assert "Couvert" in html
    assert f'data-testid="benevolat-connexion-{lieu.besoin.pk}"' in html
    assert f'data-testid="benevolat-je-viens-{lieu.besoin.pk}"' not in html


def test_un_besoin_passe_n_est_plus_affiche(lieu):
    """
    P6 : un besoin dont la fin est passée disparaît de la page publique.
    Un besoin « Journée » d'hier est fini depuis minuit : la requête le charge (elle garde
    les besoins depuis hier), c'est le contrôle de sa fin qui doit l'écarter.
    / Yesterday's whole-day need is loaded by the query; the end check must drop it.
    """
    from booking.models import BesoinBenevole

    besoin_d_hier = BesoinBenevole.objects.create(
        planning=lieu.planning, tache=lieu.tache,
        date=lieu.aujourd_hui - datetime.timedelta(days=1), nombre_souhaite=1,
    )

    html = navigateur().get(adresse_du_planning(lieu.planning)).content.decode()

    assert str(lieu.besoin.pk) in html
    assert str(besoin_d_hier.pk) not in html


def test_le_compteur_de_l_en_tete(lieu):
    """
    D21 : places couvertes, renforts, créneaux encore vides.
    Besoin A (1 souhaité) : 2 inscrits → 1 couverte, 1 renfort. Besoin B (2 souhaités) : vide.
    """
    from booking.models import BesoinBenevole, InscriptionBenevole

    BesoinBenevole.objects.create(
        planning=lieu.planning, tache=lieu.tache, date=lieu.besoin.date, nombre_souhaite=2,
    )
    InscriptionBenevole.objects.create(besoin=lieu.besoin, user=creer_utilisateur())
    InscriptionBenevole.objects.create(besoin=lieu.besoin, user=creer_utilisateur())

    html = navigateur().get(adresse_du_planning(lieu.planning)).content.decode()

    assert "<b>1</b> / 3 places couvertes" in html
    assert "<b>1</b> en renfort" in html
    assert "<b>1</b> créneau encore vide" in html


def test_un_planning_au_slug_book_est_servi_par_le_benevolat(lieu):
    """
    BookingViewSet est sur le préfixe vide (« <pk>/book/ ») : les routes du bénévolat
    passent avant lui. Un planning au slug « book » ou « lettre » s'affiche.
    """
    for slug in ["book", "lettre"]:
        lieu.planning.slug = slug
        lieu.planning.save()
        reponse = navigateur().get(f"/booking/benevolat/{slug}/")
        assert reponse.status_code == 200, slug
        assert 'data-testid="benevolat-page"' in reponse.content.decode()


# ---------------------------------------------------------------------------
# S'inscrire / Sign up
# ---------------------------------------------------------------------------

def test_anonyme_ne_peut_pas_s_inscrire(lieu):
    from booking.models import InscriptionBenevole

    reponse = navigateur().post(adresse_inscrire(lieu.besoin))

    assert reponse.status_code == 403
    assert not InscriptionBenevole.objects.filter(besoin=lieu.besoin).exists()


def test_je_viens_inscrit_et_envoie_un_seul_mail_meme_en_double_clic(lieu, django_capture_on_commit_callbacks):
    """
    Un clic : inscription, zone rendue, toast, un mail. Un second clic : rien de plus.
    Aucune ligne de vente n'est créée.
    / One click: sign-up, zone, toast, one mail. Second click: nothing more. No sale line.
    """
    from BaseBillet.models import LigneArticle
    from booking.models import InscriptionBenevole

    camille = creer_utilisateur(prenom="Camille", nom="Martin")
    client = navigateur(camille)
    nombre_de_lignes_de_vente_avant = LigneArticle.objects.count()

    with django_capture_on_commit_callbacks(execute=True):
        premiere_reponse = client.post(adresse_inscrire(lieu.besoin))
    with django_capture_on_commit_callbacks(execute=True):
        seconde_reponse = client.post(adresse_inscrire(lieu.besoin))

    assert premiere_reponse.status_code == 200
    assert seconde_reponse.status_code == 200
    assert 'id="benevolat-planning"' in premiere_reponse.content.decode()
    assert "appToast" in premiere_reponse["HX-Trigger"]
    assert InscriptionBenevole.objects.filter(besoin=lieu.besoin, user=camille).count() == 1
    assert noms_des_taches(lieu.taches_demandees).count("envoyer_confirmation_benevole") == 1
    assert LigneArticle.objects.count() == nombre_de_lignes_de_vente_avant


def test_on_peut_s_inscrire_au_dela_du_nombre_souhaite(lieu):
    """D7 : le besoin (1 souhaité) est couvert, une deuxième personne vient en renfort : 2/1."""
    from booking.models import InscriptionBenevole

    InscriptionBenevole.objects.create(besoin=lieu.besoin, user=creer_utilisateur())
    leo = creer_utilisateur(prenom="Léo", nom="Bernard")

    html_avant = navigateur(leo).get(adresse_du_planning(lieu.planning)).content.decode()
    assert f'data-testid="benevolat-je-viens-aussi-{lieu.besoin.pk}"' in html_avant

    reponse = navigateur(leo).post(adresse_inscrire(lieu.besoin))

    assert reponse.status_code == 200
    assert InscriptionBenevole.objects.filter(besoin=lieu.besoin).count() == 2
    assert "<b>2</b>/1" in reponse.content.decode()


def test_un_planning_reserve_refuse_sans_adhesion_et_accepte_avec(lieu):
    """D3 : réservé aux adhérent·es d'une adhésion. Sans : 422. Avec une adhésion active : OK."""
    from booking.models import InscriptionBenevole

    adhesion = creer_adhesion()
    lieu.planning.adhesions_requises.add(adhesion.produit)

    sans_adhesion = creer_utilisateur()
    reponse_refusee = navigateur(sans_adhesion).post(adresse_inscrire(lieu.besoin))
    assert reponse_refusee.status_code == 422
    assert not InscriptionBenevole.objects.filter(besoin=lieu.besoin, user=sans_adhesion).exists()

    adherente = creer_utilisateur()
    creer_une_adhesion_active(adherente, adhesion)
    reponse_acceptee = navigateur(adherente).post(adresse_inscrire(lieu.besoin))
    assert reponse_acceptee.status_code == 200
    assert InscriptionBenevole.objects.filter(besoin=lieu.besoin, user=adherente).exists()


def test_une_adhesion_expiree_ne_suffit_pas(lieu):
    from booking.models import InscriptionBenevole

    adhesion = creer_adhesion()
    lieu.planning.adhesions_requises.add(adhesion.produit)
    ancienne_adherente = creer_utilisateur()
    creer_une_adhesion_active(ancienne_adherente, adhesion, jours_restants=-1)

    reponse = navigateur(ancienne_adherente).post(adresse_inscrire(lieu.besoin))

    assert reponse.status_code == 422
    assert not InscriptionBenevole.objects.filter(besoin=lieu.besoin).exists()


def test_on_ne_s_inscrit_pas_a_un_besoin_passe(lieu):
    from booking.models import BesoinBenevole, InscriptionBenevole

    besoin_d_avant_hier = BesoinBenevole.objects.create(
        planning=lieu.planning, tache=lieu.tache,
        date=lieu.aujourd_hui - datetime.timedelta(days=2), nombre_souhaite=1,
    )

    reponse = navigateur(creer_utilisateur()).post(adresse_inscrire(besoin_d_avant_hier))

    assert reponse.status_code == 422
    assert not InscriptionBenevole.objects.filter(besoin=besoin_d_avant_hier).exists()


# ---------------------------------------------------------------------------
# Prénom ou nom manquant (D18) / Missing first or last name
# ---------------------------------------------------------------------------

def test_prenom_manquant_ouvre_la_fenetre_puis_inscrit(lieu, django_capture_on_commit_callbacks):
    """
    1er POST : la fenêtre, aucune inscription. 2e POST depuis la fenêtre : prénom et nom
    enregistrés dans le compte, inscription faite, fenêtre fermée.
    """
    from booking.models import InscriptionBenevole

    sans_nom = creer_utilisateur(prenom="", nom="")
    client = navigateur(sans_nom)

    premiere_reponse = client.post(adresse_inscrire(lieu.besoin))

    assert premiere_reponse.status_code == 200
    assert premiere_reponse["HX-Retarget"] == "#benevolat-modale-contenu"
    assert "ouvrirModaleBenevolat" in premiere_reponse["HX-Trigger-After-Settle"]
    html_de_la_fenetre = premiere_reponse.content.decode()
    assert 'data-testid="benevolat-prenom"' in html_de_la_fenetre
    assert 'data-testid="benevolat-nom"' in html_de_la_fenetre
    assert not InscriptionBenevole.objects.filter(besoin=lieu.besoin).exists()

    with django_capture_on_commit_callbacks(execute=True):
        seconde_reponse = client.post(
            adresse_inscrire(lieu.besoin),
            {"fenetre_nom": "1", "prenom": "  Camille ", "nom": "Martin"},
        )

    assert seconde_reponse.status_code == 200
    assert "fermerModaleBenevolat" in seconde_reponse["HX-Trigger-After-Settle"]
    sans_nom.refresh_from_db()
    assert sans_nom.first_name == "Camille"
    assert sans_nom.last_name == "Martin"
    assert InscriptionBenevole.objects.filter(besoin=lieu.besoin, user=sans_nom).exists()
    assert "envoyer_confirmation_benevole" in noms_des_taches(lieu.taches_demandees)


@pytest.mark.parametrize("prenom_envoye", ["", "   "])
def test_prenom_vide_dans_la_fenetre_est_refuse(lieu, prenom_envoye):
    from booking.models import InscriptionBenevole

    sans_nom = creer_utilisateur(prenom="", nom="")

    reponse = navigateur(sans_nom).post(
        adresse_inscrire(lieu.besoin), {"fenetre_nom": "1", "prenom": prenom_envoye, "nom": "Martin"},
    )

    assert reponse.status_code == 422
    assert reponse["HX-Retarget"] == "#benevolat-modale-contenu"
    assert "Écris ton prénom" in reponse.content.decode()
    sans_nom.refresh_from_db()
    assert not sans_nom.first_name
    assert not InscriptionBenevole.objects.filter(besoin=lieu.besoin).exists()


def test_nom_manquant_ne_demande_que_le_nom_et_ne_reecrit_pas_le_prenom(lieu):
    from booking.models import InscriptionBenevole

    sans_nom_de_famille = creer_utilisateur(prenom="Camille", nom="")
    client = navigateur(sans_nom_de_famille)

    html_de_la_fenetre = client.post(adresse_inscrire(lieu.besoin)).content.decode()
    assert 'data-testid="benevolat-nom"' in html_de_la_fenetre
    assert 'data-testid="benevolat-prenom"' not in html_de_la_fenetre

    reponse = client.post(
        adresse_inscrire(lieu.besoin), {"fenetre_nom": "1", "prenom": "Autre", "nom": "Martin"},
    )

    assert reponse.status_code == 200
    sans_nom_de_famille.refresh_from_db()
    assert sans_nom_de_famille.first_name == "Camille"
    assert sans_nom_de_famille.last_name == "Martin"
    assert InscriptionBenevole.objects.filter(besoin=lieu.besoin, user=sans_nom_de_famille).exists()


# ---------------------------------------------------------------------------
# Se retirer / Withdraw
# ---------------------------------------------------------------------------

def test_se_retirer_avant_le_delai_ne_previent_personne(lieu, django_capture_on_commit_callbacks):
    from booking.models import InscriptionBenevole

    camille = creer_utilisateur()
    InscriptionBenevole.objects.create(besoin=lieu.besoin, user=camille)

    with django_capture_on_commit_callbacks(execute=True):
        reponse = navigateur(camille).post(adresse_retirer(lieu.besoin))

    assert reponse.status_code == 200
    assert not InscriptionBenevole.objects.filter(besoin=lieu.besoin, user=camille).exists()
    assert "prevenir_l_equipe_d_un_desistement" not in noms_des_taches(lieu.taches_demandees)


def test_se_retirer_apres_le_delai_retire_et_previent_l_equipe(lieu, django_capture_on_commit_callbacks):
    """P10 : après le délai, le retrait marche aussi, et l'équipe est prévenue."""
    from booking.models import InscriptionBenevole

    # Le besoin est dans 5 jours : un délai de 10 jours le met « après le délai ».
    # / The need is in 5 days: a 10-day deadline puts it "after the deadline".
    lieu.planning.delai_desinscription_heures = 240
    lieu.planning.save()
    camille = creer_utilisateur(prenom="Camille", nom="Martin")
    inscription = InscriptionBenevole.objects.create(besoin=lieu.besoin, user=camille)
    # L'équipe ne compte sur la personne que si elle s'était inscrite AVANT le délai :
    # on vieillit l'inscription de 20 jours. / Age the sign-up past the deadline.
    InscriptionBenevole.objects.filter(pk=inscription.pk).update(
        created_at=timezone.now() - datetime.timedelta(days=20),
    )

    html_avant = navigateur(camille).get(adresse_du_planning(lieu.planning)).content.decode()
    assert "Je ne peux plus venir" in html_avant

    with django_capture_on_commit_callbacks(execute=True):
        reponse = navigateur(camille).post(adresse_retirer(lieu.besoin))

    assert reponse.status_code == 200
    assert not InscriptionBenevole.objects.filter(besoin=lieu.besoin, user=camille).exists()
    taches_de_desistement = [
        arguments for nom, arguments in lieu.taches_demandees
        if nom == "prevenir_l_equipe_d_un_desistement"
    ]
    assert taches_de_desistement == [(str(lieu.besoin.pk), "Camille Martin")]


def test_on_ne_se_retire_pas_d_un_besoin_passe(lieu):
    from booking.models import BesoinBenevole, InscriptionBenevole

    besoin_d_avant_hier = BesoinBenevole.objects.create(
        planning=lieu.planning, tache=lieu.tache,
        date=lieu.aujourd_hui - datetime.timedelta(days=2), nombre_souhaite=1,
    )
    camille = creer_utilisateur()
    InscriptionBenevole.objects.create(besoin=besoin_d_avant_hier, user=camille)

    reponse = navigateur(camille).post(adresse_retirer(besoin_d_avant_hier))

    assert reponse.status_code == 422
    assert InscriptionBenevole.objects.filter(besoin=besoin_d_avant_hier, user=camille).exists()


def test_se_retirer_ne_touche_pas_l_inscription_d_une_autre_personne(lieu):
    from booking.models import InscriptionBenevole

    camille = creer_utilisateur()
    leo = creer_utilisateur()
    InscriptionBenevole.objects.create(besoin=lieu.besoin, user=camille)

    reponse = navigateur(leo).post(adresse_retirer(lieu.besoin))

    assert reponse.status_code == 200
    assert InscriptionBenevole.objects.filter(besoin=lieu.besoin, user=camille).exists()


# ---------------------------------------------------------------------------
# Mails / Emails
# ---------------------------------------------------------------------------

def test_les_mails_se_rendent_sans_erreur(lieu):
    """
    Les deux gabarits de mail se rendent avec le contexte des tâches, heures locales comprises.
    / Both email templates render with the tasks' context, local hours included.
    """
    from django.template.loader import render_to_string

    contexte_commun = {
        "title": "Titre", "organisation": "Lespass", "image_url_place": "",
        "besoin": lieu.besoin, "plage": "18h–21h",
    }
    confirmation = render_to_string(
        "booking/benevolat/emails/confirmation.html",
        {**contexte_commun, "par_l_equipe": True, "url_du_planning": "https://x/"},
    )
    desistement = render_to_string(
        "booking/benevolat/emails/desistement_equipe.html",
        {**contexte_commun, "nom_de_la_personne": "Camille Martin", "nombre_inscrits": 0,
         "url_de_l_admin": "https://x/"},
    )

    assert lieu.tache.name in confirmation
    assert "18h–21h" in confirmation
    assert "Camille Martin" in desistement


# ---------------------------------------------------------------------------
# Relecture du 2026-10-16 : cas limites et sécurité
# / 2026-10-16 review: edge cases and security
# ---------------------------------------------------------------------------

def test_inscrire_et_retirer_sur_un_planning_non_publie_rendent_404(lieu):
    from booking.models import InscriptionBenevole

    camille = creer_utilisateur()
    InscriptionBenevole.objects.create(besoin=lieu.besoin, user=camille)
    lieu.planning.published = False
    lieu.planning.save()

    assert navigateur(creer_utilisateur()).post(adresse_inscrire(lieu.besoin)).status_code == 404
    assert navigateur(camille).post(adresse_retirer(lieu.besoin)).status_code == 404
    assert InscriptionBenevole.objects.filter(besoin=lieu.besoin, user=camille).exists()


def test_retirer_en_anonyme_rend_403_avec_un_toast(lieu):
    reponse = navigateur().post(adresse_retirer(lieu.besoin))

    assert reponse.status_code == 403
    assert "appToast" in reponse["HX-Trigger"]


def test_un_post_sans_jeton_csrf_est_refuse(lieu):
    from booking.models import InscriptionBenevole

    camille = creer_utilisateur()
    client = Client(HTTP_HOST="lespass.tibillet.localhost", enforce_csrf_checks=True)
    client.force_login(camille)

    reponse = client.post(adresse_inscrire(lieu.besoin))

    assert reponse.status_code == 403
    assert not InscriptionBenevole.objects.filter(besoin=lieu.besoin).exists()


def test_inscrit_apres_le_delai_puis_retire_ne_previent_pas_l_equipe(lieu, django_capture_on_commit_callbacks):
    """
    Un renfort de dernière minute qui se retire : l'équipe ne comptait pas sur lui,
    pas de mail. Ça ferme aussi la boucle « Je viens » / « Je ne peux plus venir ».
    """
    from booking.models import InscriptionBenevole

    lieu.planning.delai_desinscription_heures = 240
    lieu.planning.save()
    camille = creer_utilisateur()

    with django_capture_on_commit_callbacks(execute=True):
        navigateur(camille).post(adresse_inscrire(lieu.besoin))
        reponse = navigateur(camille).post(adresse_retirer(lieu.besoin))

    assert reponse.status_code == 200
    assert not InscriptionBenevole.objects.filter(besoin=lieu.besoin, user=camille).exists()
    assert "prevenir_l_equipe_d_un_desistement" not in noms_des_taches(lieu.taches_demandees)


def test_une_adhesion_annulee_n_ouvre_pas_le_planning(lieu):
    from BaseBillet.models import Membership
    from booking.models import InscriptionBenevole

    adhesion = creer_adhesion()
    lieu.planning.adhesions_requises.add(adhesion.produit)
    adherente_annulee = creer_utilisateur()
    adhesion_de_la_personne = creer_une_adhesion_active(adherente_annulee, adhesion)
    adhesion_de_la_personne.status = Membership.CANCELED
    adhesion_de_la_personne.save()

    reponse = navigateur(adherente_annulee).post(adresse_inscrire(lieu.besoin))

    assert reponse.status_code == 422
    assert not InscriptionBenevole.objects.filter(besoin=lieu.besoin).exists()


@pytest.mark.parametrize("prenom_envoye", ["C" * 201, "Camille\nMartin", "Camille\rX"])
def test_prenom_trop_long_ou_sur_deux_lignes_est_refuse(lieu, prenom_envoye):
    from booking.models import InscriptionBenevole

    sans_nom = creer_utilisateur(prenom="", nom="Martin")

    reponse = navigateur(sans_nom).post(
        adresse_inscrire(lieu.besoin), {"fenetre_nom": "1", "prenom": prenom_envoye},
    )

    assert reponse.status_code == 422
    sans_nom.refresh_from_db()
    assert not sans_nom.first_name
    assert not InscriptionBenevole.objects.filter(besoin=lieu.besoin).exists()


def test_un_refus_depuis_la_fenetre_la_ferme(lieu):
    """Planning devenu réservé pendant que la fenêtre est ouverte : la 422 la ferme."""
    adhesion = creer_adhesion()
    lieu.planning.adhesions_requises.add(adhesion.produit)
    sans_nom = creer_utilisateur(prenom="", nom="")

    reponse = navigateur(sans_nom).post(
        adresse_inscrire(lieu.besoin), {"fenetre_nom": "1", "prenom": "Camille", "nom": "Martin"},
    )

    assert reponse.status_code == 422
    assert "fermerModaleBenevolat" in reponse["HX-Trigger-After-Settle"]


def test_fenetre_envoyee_alors_que_le_compte_a_deja_son_nom_ne_reecrit_rien(lieu):
    from booking.models import InscriptionBenevole

    camille = creer_utilisateur(prenom="Camille", nom="Martin")

    reponse = navigateur(camille).post(
        adresse_inscrire(lieu.besoin), {"fenetre_nom": "1", "prenom": "Autre", "nom": "Autre"},
    )

    assert reponse.status_code == 200
    camille.refresh_from_db()
    assert (camille.first_name, camille.last_name) == ("Camille", "Martin")
    assert InscriptionBenevole.objects.filter(besoin=lieu.besoin, user=camille).exists()
