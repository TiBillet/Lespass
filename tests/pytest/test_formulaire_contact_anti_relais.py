"""
Formulaire de contact : il ne doit pas servir de relais à spam.
/ Contact form: it must not be usable as a spam relay.

Incident du 2026-11-10 : un robot postait le formulaire avec x=0, y=0, answer=0
(le captcha venait du navigateur) et l'adresse de sa cible dans « email ».
TiBillet envoyait alors une « copie » à cette cible, depuis facteur@mail.tibillet.coop.
/ Incident of 2026-11-10: a bot posted the form with x=0, y=0, answer=0
(the captcha came from the browser) and its target's address in "email".
TiBillet then sent a "copy" to that target, from facteur@mail.tibillet.coop.

Depuis : formulaire réservé aux personnes connectées, adresse = celle du compte.
Plus de captcha : une session connectée suppose une adresse vérifiée.
/ Since then: logged-in people only, address = the account's.
No captcha anymore: a logged-in session implies a verified address.

Code testé / Tested code :
  BaseBillet/validators.py (ContactValidator)
  BaseBillet/views.py (HomeViewset.contact)
  BaseBillet/tasks.py (contact_mailer)
  BaseBillet/templates/commun/formulaires/contact.html
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import Client as HttpClient
from django_tenants.utils import tenant_context

DOMAINE_DU_LIEU = "lespass.tibillet.localhost"
ADRESSE_DE_LA_CIBLE = "cible-du-robot@mock.test"


def _poster_le_formulaire(client):
    """
    Poste le formulaire de contact, avec Celery remplacé par un espion.
    Le champ « email » et l'ancien captcha sont envoyés quand même, comme le ferait le robot.
    Renvoie les arguments passés à contact_mailer.delay, ou None si rien n'est parti.
    / Posts the contact form, with Celery replaced by a spy.
    The "email" field and the old captcha are sent anyway, as the bot would.
    Returns the arguments given to contact_mailer.delay, or None if nothing was sent.
    """
    donnees_du_robot = {
        "email": ADRESSE_DE_LA_CIBLE,
        "subject": "Secafi Expertise — billetterie prix libre",
        "message": "Bonjour",
        "x": 0,
        "y": 0,
        "answer": 0,
    }

    with patch("BaseBillet.views.contact_mailer.delay") as espion_de_l_envoi:
        client.post("/home/contact/", donnees_du_robot)

    if not espion_de_l_envoi.called:
        return None
    return espion_de_l_envoi.call_args.kwargs


# --- La vue / The view ---


def test_un_visiteur_anonyme_ne_peut_rien_envoyer():
    """
    Anonyme : rien ne part, même avec l'ancienne attaque du robot.
    / Anonymous: nothing is sent, even with the bot's old attack.
    """
    client_anonyme = HttpClient(HTTP_HOST=DOMAINE_DU_LIEU)

    arguments_de_l_envoi = _poster_le_formulaire(client_anonyme)

    assert arguments_de_l_envoi is None


def test_l_adresse_utilisee_est_celle_du_compte_pas_celle_postee(admin_user):
    """
    Connecté : le message part avec l'adresse du compte.
    Le champ « email » posté à la main est ignoré.
    / Logged in: the message uses the account address.
    The hand-posted "email" field is ignored.
    """
    client_connecte = HttpClient(HTTP_HOST=DOMAINE_DU_LIEU)
    client_connecte.force_login(admin_user)

    arguments_de_l_envoi = _poster_le_formulaire(client_connecte)

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


def test_le_gabarit_connecte_n_a_ni_champ_email_ni_captcha(tenant, admin_user):
    """
    Connecté : le formulaire n'a ni champ email ni captcha, et affiche l'adresse du compte.
    / Logged in: the form has no email field nor captcha, and shows the account address.
    """
    with tenant_context(tenant):
        html = render_to_string("commun/formulaires/contact.html", {"user": admin_user})

    assert "<form" in html
    assert 'name="email"' not in html
    assert 'name="answer"' not in html
    assert admin_user.email in html
