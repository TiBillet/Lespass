"""
Tests du rappel de la veille et du lien « Je ne peux plus venir » des mails.
/ Tests of the day-before reminder and the "I can't come anymore" email link.

LOCALISATION : tests/pytest/test_benevolat_rappel.py

Code testé / Tested code : booking/tasks.py (rappeler_les_benevoles_du_lendemain[_du_lieu],
envoyer_confirmation_benevole), booking/benevolat.py (jeton_de_desistement,
inscription_du_jeton, retirer_une_inscription), booking/views_benevolat.py (desistement)
Spec : TECH_DOC/SESSIONS/TODO/BENEVOLAT-planning-besoins.md (§5.9)

Chaque test est marqué `django_db` : transaction annulée à la fin.
Les mails ne partent pas : CeleryMailerClass est remplacé par un faux qui note chaque
envoi (destinataire, sujet, contexte).
/ Mails are faked: a fake CeleryMailerClass records each send.

Lancer / Run : make test ARGS="tests/pytest/test_benevolat_rappel.py"
"""

import datetime
import re
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone
from django_tenants.utils import tenant_context

from fabriques_panier import creer_utilisateur, identifiant_unique, noms_des_taches, taches_celery_enregistrees

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les tâches activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5)."""
    from django.utils import translation

    yield
    translation.deactivate()


class FauxMailer:
    """Remplace CeleryMailerClass : note les envois au lieu de les faire."""
    envois = []

    def __init__(self, email, title, template=None, context=None, **autres):
        self.email = email
        self.title = title
        self.context = context
        self.sended = None

    def send(self):
        FauxMailer.envois.append(self)
        self.sended = True


@pytest.fixture
def mails_envoyes():
    FauxMailer.envois = []
    with patch("booking.tasks.CeleryMailerClass", FauxMailer):
        yield FauxMailer.envois


@pytest.fixture
def lieu(tenant):
    from BaseBillet.models import Configuration

    with tenant_context(tenant):
        with taches_celery_enregistrees() as taches_demandees:
            fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
            yield SimpleNamespace(
                aujourd_hui=timezone.now().astimezone(fuseau_du_lieu).date(),
                taches_demandees=taches_demandees,
            )


def creer_un_besoin(dans_combien_de_jours, journee=False, publie=True, delai_heures=24):
    from BaseBillet.models import Configuration
    from booking.models import BesoinBenevole, PlanningBenevole, TacheBenevole

    fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
    aujourd_hui = timezone.now().astimezone(fuseau_du_lieu).date()
    identifiant = identifiant_unique()
    planning = PlanningBenevole.objects.create(
        name=f"TEST_benevolat planning {identifiant}", slug=f"test-benevolat-{identifiant}",
        published=publie, delai_desinscription_heures=delai_heures,
    )
    tache = TacheBenevole.objects.create(name=f"TEST_benevolat bar {identifiant}")
    heures = {} if journee else {"heure_debut": datetime.time(18), "heure_fin": datetime.time(21)}
    return BesoinBenevole.objects.create(
        planning=planning, tache=tache, date=aujourd_hui + datetime.timedelta(days=dans_combien_de_jours),
        nombre_souhaite=2, **heures,
    )


def inscrire(besoin, utilisateur=None, il_y_a_jours=0):
    """Une inscription, éventuellement vieillie de `il_y_a_jours`. / An optionally aged sign-up."""
    from booking.models import InscriptionBenevole

    inscription = InscriptionBenevole.objects.create(besoin=besoin, user=utilisateur or creer_utilisateur())
    if il_y_a_jours:
        InscriptionBenevole.objects.filter(pk=inscription.pk).update(
            created_at=timezone.now() - datetime.timedelta(days=il_y_a_jours),
        )
        inscription.refresh_from_db()
    return inscription


def navigateur():
    return Client(HTTP_HOST="lespass.tibillet.localhost", HTTP_ACCEPT_LANGUAGE="fr")


# ---------------------------------------------------------------------------
# Rappel de la veille / Day-before reminder
# ---------------------------------------------------------------------------

def test_un_besoin_de_demain_recoit_un_rappel_et_un_seul(lieu, mails_envoyes):
    from booking.tasks import rappeler_les_benevoles_du_lendemain_du_lieu

    inscription = inscrire(creer_un_besoin(1))

    assert rappeler_les_benevoles_du_lendemain_du_lieu() >= 1
    mails_de_cette_personne = [mail for mail in mails_envoyes if mail.email == inscription.user.email]
    assert len(mails_de_cette_personne) == 1
    assert "18h–21h" in mails_de_cette_personne[0].title
    inscription.refresh_from_db()
    assert inscription.rappel_envoye_le is not None

    # Relancer la tâche n'envoie rien deux fois / Running it again sends nothing twice
    rappeler_les_benevoles_du_lendemain_du_lieu()
    assert len([mail for mail in mails_envoyes if mail.email == inscription.user.email]) == 1


def test_apres_demain_ou_planning_depublie_pas_de_rappel(lieu, mails_envoyes):
    from booking.tasks import rappeler_les_benevoles_du_lendemain_du_lieu

    apres_demain = inscrire(creer_un_besoin(2))
    depublie = inscrire(creer_un_besoin(1, publie=False))

    rappeler_les_benevoles_du_lendemain_du_lieu()

    destinataires = [mail.email for mail in mails_envoyes]
    assert apres_demain.user.email not in destinataires
    assert depublie.user.email not in destinataires


def test_un_besoin_journee_a_sa_propre_phrase(lieu, mails_envoyes):
    from booking.tasks import rappeler_les_benevoles_du_lendemain_du_lieu

    inscription = inscrire(creer_un_besoin(1, journee=True))

    rappeler_les_benevoles_du_lendemain_du_lieu()

    sujet = [mail.title for mail in mails_envoyes if mail.email == inscription.user.email][0]
    assert "Demain :" in sujet
    assert "–" not in sujet.split("Demain")[1].split(":")[0]


def test_un_envoi_rate_ne_marque_pas_le_rappel(lieu):
    """Mail non parti : rappel_envoye_le reste vide. / Failed send: not marked."""
    from booking.tasks import rappeler_les_benevoles_du_lendemain_du_lieu

    class MailerEnPanne(FauxMailer):
        def send(self):
            self.sended = False

    inscription = inscrire(creer_un_besoin(1))
    with patch("booking.tasks.CeleryMailerClass", MailerEnPanne):
        rappeler_les_benevoles_du_lendemain_du_lieu()

    inscription.refresh_from_db()
    assert inscription.rappel_envoye_le is None


def test_la_tache_parcourt_les_lieux_sauf_public_et_emplacements_vides():
    """Un passage par lieu configuré ; jamais public ni WAITING_CONFIG."""
    from django.db import connection

    from Customers.models import Client as Lieu
    from booking.tasks import rappeler_les_benevoles_du_lendemain

    schemas_parcourus = []
    with patch(
        "booking.tasks.rappeler_les_benevoles_du_lendemain_du_lieu",
        side_effect=lambda: schemas_parcourus.append(connection.schema_name),
    ):
        rappeler_les_benevoles_du_lendemain()

    assert "public" not in schemas_parcourus
    assert "lespass" in schemas_parcourus
    emplacements_vides = set(Lieu.objects.filter(categorie=Lieu.WAITING_CONFIG).values_list("schema_name", flat=True))
    assert not emplacements_vides & set(schemas_parcourus)


# ---------------------------------------------------------------------------
# Lien « Je ne peux plus venir » / Withdrawal link
# ---------------------------------------------------------------------------

def adresse_du_lien(inscription):
    from booking.benevolat import jeton_de_desistement

    return f"/booking/benevolat/desistement/{jeton_de_desistement(inscription)}/"


def test_les_deux_mails_portent_un_lien_de_desistement_qui_marche(lieu, mails_envoyes):
    """Rappel et confirmation : le lien signé ouvre la page de confirmation."""
    from booking.tasks import envoyer_confirmation_benevole, rappeler_les_benevoles_du_lendemain_du_lieu

    inscription = inscrire(creer_un_besoin(1))
    rappeler_les_benevoles_du_lendemain_du_lieu()
    envoyer_confirmation_benevole(str(inscription.pk))

    mails = [mail for mail in mails_envoyes if mail.email == inscription.user.email]
    assert len(mails) == 2
    for mail in mails:
        chemin = re.sub(r"^https://[^/]+", "", mail.context["url_de_desistement"])
        html = navigateur().get(chemin).content.decode()
        assert 'data-testid="benevolat-desistement-confirmer"' in html


def test_le_get_ne_supprime_rien_et_le_post_retire(lieu, django_capture_on_commit_callbacks):
    from booking.models import InscriptionBenevole

    inscription = inscrire(creer_un_besoin(5))

    reponse_get = navigateur().get(adresse_du_lien(inscription))
    assert reponse_get.status_code == 200
    assert InscriptionBenevole.objects.filter(pk=inscription.pk).exists()

    with django_capture_on_commit_callbacks(execute=True):
        reponse_post = navigateur().post(adresse_du_lien(inscription))
    assert reponse_post.status_code == 200
    assert 'data-testid="benevolat-desistement-fait"' in reponse_post.content.decode()
    assert not InscriptionBenevole.objects.filter(pk=inscription.pk).exists()
    # Avant le délai : l'équipe n'est pas prévenue / Before the deadline: team not warned
    assert "prevenir_l_equipe_d_un_desistement" not in noms_des_taches(lieu.taches_demandees)


def test_apres_le_delai_le_lien_marche_et_previent_l_equipe(lieu, django_capture_on_commit_callbacks):
    """D16 : le lien marche MÊME après le délai de retrait, et l'équipe est prévenue."""
    besoin = creer_un_besoin(1, delai_heures=48)
    inscription = inscrire(besoin, il_y_a_jours=10)

    with django_capture_on_commit_callbacks(execute=True):
        reponse = navigateur().post(adresse_du_lien(inscription))

    assert "L'équipe est prévenue" in reponse.content.decode()
    assert "prevenir_l_equipe_d_un_desistement" in noms_des_taches(lieu.taches_demandees)


def test_le_post_exige_le_jeton_csrf(lieu):
    from booking.models import InscriptionBenevole

    inscription = inscrire(creer_un_besoin(5))
    client_strict = Client(HTTP_HOST="lespass.tibillet.localhost", enforce_csrf_checks=True)

    reponse = client_strict.post(adresse_du_lien(inscription))

    assert reponse.status_code == 403
    assert InscriptionBenevole.objects.filter(pk=inscription.pk).exists()


def test_lien_faux_d_un_autre_lieu_supprime_ou_passe_ne_marche_plus(lieu):
    """
    Jeton modifié, jeton signé d'un uuid inconnu ici (celui d'un autre lieu), inscription
    déjà supprimée, besoin passé : « Ce lien ne marche plus », jamais d'erreur.
    """
    from django.core import signing

    from booking.benevolat import SEL_DU_LIEN_DE_DESISTEMENT, jeton_de_desistement

    deja_supprimee = inscrire(creer_un_besoin(5))
    jeton_deja_supprime = jeton_de_desistement(deja_supprimee)
    deja_supprimee.delete()
    passee = inscrire(creer_un_besoin(-2))

    jetons_morts = [
        "nimportequoi",
        jeton_de_desistement(inscrire(creer_un_besoin(5))) + "x",
        signing.dumps(str(uuid.uuid4()), salt=SEL_DU_LIEN_DE_DESISTEMENT),
        signing.dumps("pas-un-uuid", salt=SEL_DU_LIEN_DE_DESISTEMENT),
        jeton_deja_supprime,
        jeton_de_desistement(passee),
    ]
    for jeton in jetons_morts:
        for methode in ["get", "post"]:
            reponse = getattr(navigateur(), methode)(f"/booking/benevolat/desistement/{jeton}/")
            assert reponse.status_code == 200, jeton
            assert 'data-testid="benevolat-desistement-lien-mort"' in reponse.content.decode(), jeton


def test_un_jeton_signe_d_un_entier_ne_marche_pas(lieu):
    """D25 : seul un uuid est accepté ; un entier signé (ancien schéma) ne désigne rien."""
    from django.core import signing

    from booking.benevolat import SEL_DU_LIEN_DE_DESISTEMENT

    jeton = signing.dumps(1, salt=SEL_DU_LIEN_DE_DESISTEMENT)
    reponse = navigateur().get(f"/booking/benevolat/desistement/{jeton}/")

    assert 'data-testid="benevolat-desistement-lien-mort"' in reponse.content.decode()


# ---------------------------------------------------------------------------
# Relecture du 2026-10-16 / 2026-10-16 review
# ---------------------------------------------------------------------------

def test_un_mail_qui_plante_n_empeche_pas_les_autres_rappels(lieu):
    """Un envoi qui lève une exception est journalisé ; les rappels suivants partent."""
    from booking.tasks import rappeler_les_benevoles_du_lendemain_du_lieu

    premiere = inscrire(creer_un_besoin(1))
    seconde = inscrire(creer_un_besoin(1))
    envois = []

    class MailerQuiPlanteUneFois(FauxMailer):
        def send(self):
            if self.email == premiere.user.email:
                raise ValueError("adresse refusée")
            envois.append(self.email)
            self.sended = True

    with patch("booking.tasks.CeleryMailerClass", MailerQuiPlanteUneFois):
        rappeler_les_benevoles_du_lendemain_du_lieu()

    assert seconde.user.email in envois
    premiere.refresh_from_db()
    seconde.refresh_from_db()
    assert premiere.rappel_envoye_le is None
    assert seconde.rappel_envoye_le is not None


def test_deux_retraits_simultanes_ne_previennent_l_equipe_qu_une_fois(lieu, django_capture_on_commit_callbacks):
    """Deux requêtes chargent la même inscription : une seule la supprime, un seul mail."""
    from booking.benevolat import retirer_une_inscription
    from booking.models import InscriptionBenevole

    inscription = inscrire(creer_un_besoin(1, delai_heures=48), il_y_a_jours=10)
    copie_chargee_par_l_autre_requete = InscriptionBenevole.objects.get(pk=inscription.pk)

    with django_capture_on_commit_callbacks(execute=True):
        premier = retirer_une_inscription(inscription, "Camille")
        second = retirer_une_inscription(copie_chargee_par_l_autre_requete, "Camille")

    assert (premier, second) == (True, False)
    assert noms_des_taches(lieu.taches_demandees).count("prevenir_l_equipe_d_un_desistement") == 1


def test_un_besoin_deplace_retrouve_son_rappel(lieu, mails_envoyes):
    """Rappel déjà envoyé, puis le besoin change de jour : rappel_envoye_le est vidé."""
    inscription = inscrire(creer_un_besoin(5))
    inscription.__class__.objects.filter(pk=inscription.pk).update(rappel_envoye_le=timezone.now())
    besoin = inscription.besoin

    besoin.date = besoin.date + datetime.timedelta(days=1)
    besoin.save()

    inscription.refresh_from_db()
    assert inscription.rappel_envoye_le is None


def test_csrf_echoue_sur_le_desistement_affiche_la_page_avec_un_message(lieu):
    from booking.models import InscriptionBenevole

    inscription = inscrire(creer_un_besoin(5))
    client_strict = Client(HTTP_HOST="lespass.tibillet.localhost", enforce_csrf_checks=True, HTTP_ACCEPT_LANGUAGE="fr")

    reponse = client_strict.post(adresse_du_lien(inscription))

    assert reponse.status_code == 403
    assert 'data-testid="benevolat-desistement-page-perimee"' in reponse.content.decode()
    assert InscriptionBenevole.objects.filter(pk=inscription.pk).exists()
