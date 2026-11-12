"""
Formulaire de contact : il ne doit pas servir de relais à spam.
/ Contact form: it must not be usable as a spam relay.

Incident du 2026-11-10 : un robot postait le formulaire avec x=0, y=0, answer=0
(le captcha venait du navigateur) et l'adresse de sa cible dans « email ».
TiBillet envoyait alors une « copie » à cette cible, depuis facteur@mail.tibillet.coop.
/ Incident of 2026-11-10: a bot posted the form with x=0, y=0, answer=0
(the captcha came from the browser) and its target's address in "email".
TiBillet then sent a "copy" to that target, from facteur@mail.tibillet.coop.

Depuis : formulaire réservé aux personnes connectées, adresse = celle du compte,
captcha tiré et signé par le serveur.
/ Since then: logged-in people only, address = the account's, captcha drawn
and signed by the server.

Code testé / Tested code :
  BaseBillet/templatetags/tibitags.py (captcha_contact)
  BaseBillet/validators.py (ContactValidator)
  BaseBillet/views.py (HomeViewset.contact)
  BaseBillet/tasks.py (contact_mailer)
  BaseBillet/templates/commun/formulaires/contact.html
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.template.loader import render_to_string
from django.test import Client as HttpClient
from django_tenants.utils import tenant_context

from BaseBillet.templatetags.tibitags import SEL_CAPTCHA_CONTACT, captcha_contact

DOMAINE_DU_LIEU = "lespass.tibillet.localhost"
ADRESSE_DE_LA_CIBLE = "cible-du-robot@mock.test"


def _poster_le_formulaire(client, donnees_du_captcha):
    """
    Poste le formulaire de contact, avec Celery remplacé par un espion.
    Le champ « email » est envoyé quand même, comme le ferait un robot.
    Renvoie les arguments passés à contact_mailer.delay, ou None si rien n'est parti.
    / Posts the contact form, with Celery replaced by a spy.
    The "email" field is sent anyway, as a bot would.
    Returns the arguments given to contact_mailer.delay, or None if nothing was sent.
    """
    donnees = {
        "email": ADRESSE_DE_LA_CIBLE,
        "subject": "Secafi Expertise — billetterie prix libre",
        "message": "Bonjour",
    }
    donnees.update(donnees_du_captcha)

    with patch("BaseBillet.views.contact_mailer.delay") as espion_de_l_envoi:
        client.post("/home/contact/", donnees)

    if not espion_de_l_envoi.called:
        return None
    return espion_de_l_envoi.call_args.kwargs


def _captcha_bien_repondu():
    """Un captcha tiré par le serveur, avec la bonne réponse. / A server-drawn captcha, answered right."""
    captcha = captcha_contact()
    return {"captcha_jeton": captcha["jeton"], "answer": captcha["x"] + captcha["y"]}


def _client_connecte(utilisateur):
    client = HttpClient(HTTP_HOST=DOMAINE_DU_LIEU)
    client.force_login(utilisateur)
    return client


# --- La vue / The view ---


def test_un_visiteur_anonyme_ne_peut_rien_envoyer():
    """
    Anonyme, même avec un captcha juste : rien ne part.
    / Anonymous, even with a right captcha: nothing is sent.
    """
    client_anonyme = HttpClient(HTTP_HOST=DOMAINE_DU_LIEU)

    arguments_de_l_envoi = _poster_le_formulaire(client_anonyme, _captcha_bien_repondu())

    assert arguments_de_l_envoi is None


def test_le_robot_qui_choisit_sa_question_est_refuse(admin_user):
    """
    L'ancienne attaque : x=0, y=0, answer=0, sans jeton signé. Rien ne part.
    / The old attack: x=0, y=0, answer=0, no signed token. Nothing is sent.
    """
    arguments_de_l_envoi = _poster_le_formulaire(
        _client_connecte(admin_user), {"x": 0, "y": 0, "answer": 0}
    )

    assert arguments_de_l_envoi is None


def test_un_jeton_fabrique_a_la_main_est_refuse(admin_user):
    """
    Un jeton non signé par le serveur est refusé, même avec la « bonne » réponse.
    / A token not signed by the server is refused, even with the "right" answer.
    """
    jeton_falsifie = signing.dumps(0, salt=SEL_CAPTCHA_CONTACT, key="pas-la-cle-du-serveur")

    arguments_de_l_envoi = _poster_le_formulaire(
        _client_connecte(admin_user), {"captcha_jeton": jeton_falsifie, "answer": 0}
    )

    assert arguments_de_l_envoi is None


def test_une_mauvaise_reponse_est_refusee(admin_user):
    """Le jeton est bon, la réponse est fausse : rien ne part. / Right token, wrong answer: nothing sent."""
    captcha = captcha_contact()

    arguments_de_l_envoi = _poster_le_formulaire(
        _client_connecte(admin_user),
        {"captcha_jeton": captcha["jeton"], "answer": captcha["x"] + captcha["y"] + 1},
    )

    assert arguments_de_l_envoi is None


def test_l_adresse_utilisee_est_celle_du_compte_pas_celle_postee(admin_user):
    """
    Connecté, captcha juste : le message part avec l'adresse du compte.
    Le champ « email » posté par un robot est ignoré.
    / Logged in, right captcha: the message uses the account address.
    The "email" field posted by a bot is ignored.
    """
    arguments_de_l_envoi = _poster_le_formulaire(_client_connecte(admin_user), _captcha_bien_repondu())

    assert arguments_de_l_envoi is not None
    assert arguments_de_l_envoi["sender"] == admin_user.email
    assert arguments_de_l_envoi["sender"] != ADRESSE_DE_LA_CIBLE


# --- La tâche / The task ---


def test_contact_mailer_ecrit_au_lieu_avec_copie_au_compte(tenant, mailoutbox):
    """
    Le lieu reçoit le message, le compte reçoit la copie et reste en « Répondre à ».
    / The venue gets the message, the account gets the copy and stays as "Reply-To".
    """
    from BaseBillet.tasks import contact_mailer

    configuration_avec_email = SimpleNamespace(
        email="contact-du-lieu@mock.test", organisation="Lieu de test", logo=None
    )
    with tenant_context(tenant):
        with patch("BaseBillet.tasks.Configuration.get_solo", return_value=configuration_avec_email):
            contact_mailer("compte@mock.test", "Une question", "Bonjour")

    assert len(mailoutbox) == 1
    assert sorted(mailoutbox[0].to) == ["compte@mock.test", "contact-du-lieu@mock.test"]
    assert mailoutbox[0].reply_to == ["compte@mock.test"]


# --- Le gabarit / The template ---


def test_le_gabarit_anonyme_propose_la_connexion_sans_formulaire(tenant):
    """Anonyme : pas de formulaire, un bouton qui ouvre #loginPanel. / Anonymous: no form, a #loginPanel button."""
    with tenant_context(tenant):
        html = render_to_string("commun/formulaires/contact.html", {"user": AnonymousUser()})

    assert "<form" not in html
    assert 'data-bs-target="#loginPanel"' in html


def test_le_gabarit_connecte_n_a_plus_de_champ_email(tenant, admin_user):
    """
    Connecté : le formulaire n'a ni champ email ni x/y, mais porte le jeton signé.
    / Logged in: the form has no email field nor x/y, but carries the signed token.
    """
    with tenant_context(tenant):
        html = render_to_string("commun/formulaires/contact.html", {"user": admin_user})

    assert "<form" in html
    assert 'name="email"' not in html
    assert 'name="x"' not in html
    assert 'name="captcha_jeton"' in html
    assert admin_user.email in html
