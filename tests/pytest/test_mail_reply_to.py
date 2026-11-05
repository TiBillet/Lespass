"""
Tests de l'en-tête Reply-To des mails : une réponse part vers l'adresse du lieu.
/ Tests of the emails' Reply-To header: a reply goes to the venue address.

LOCALISATION : tests/pytest/test_mail_reply_to.py

Code testé / Tested code : BaseBillet/tasks.py (CeleryMailerClass.adresse_de_reponse, send, contact_mailer)

Les mails sont lus dans `mailoutbox` (pytest-django) : rien ne part vraiment.
On ne modifie pas la Configuration en base : django-solo la garde en cache, et une
valeur changée ici resterait visible des tests suivants. On remplace get_solo à la place.
/ Configuration is never modified in DB (django-solo cache): get_solo is patched instead.

Lancer / Run : make test ARGS="tests/pytest/test_mail_reply_to.py"
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django_tenants.utils import schema_context, tenant_context

pytestmark = pytest.mark.django_db


def envoyer_un_mail_de_test():
    """Envoie un mail minimal par CeleryMailerClass. / Sends a minimal email."""
    from BaseBillet.tasks import CeleryMailerClass

    mail = CeleryMailerClass(
        "destinataire@mock.test", "Sujet de test", text="Contenu de test"
    )
    mail.send()


def test_le_reply_to_est_l_adresse_du_lieu(tenant, mailoutbox):
    configuration_avec_email = SimpleNamespace(email="contact-du-lieu@mock.test")

    with tenant_context(tenant):
        with patch(
            "BaseBillet.tasks.Configuration.get_solo",
            return_value=configuration_avec_email,
        ):
            envoyer_un_mail_de_test()

    assert len(mailoutbox) == 1
    assert mailoutbox[0].reply_to == ["contact-du-lieu@mock.test"]
    # Le From ne change pas : c'est lui que DMARC contrôle.
    # / The From does not change: DMARC checks it.
    assert mailoutbox[0].from_email != "contact-du-lieu@mock.test"


def test_pas_de_reply_to_quand_le_lieu_n_a_pas_d_email(tenant, mailoutbox):
    configuration_sans_email = SimpleNamespace(email="")

    with tenant_context(tenant):
        with patch(
            "BaseBillet.tasks.Configuration.get_solo",
            return_value=configuration_sans_email,
        ):
            envoyer_un_mail_de_test()

    assert len(mailoutbox) == 1
    assert mailoutbox[0].reply_to == []


def test_pas_de_reply_to_dans_le_schema_public(mailoutbox):
    # Dans public, la table Configuration n'existe pas : on ne doit même pas la lire.
    # / In public, the Configuration table does not exist: it must not be read.
    with schema_context("public"):
        envoyer_un_mail_de_test()

    assert len(mailoutbox) == 1
    assert mailoutbox[0].reply_to == []


def test_les_mails_transactionnels_n_ont_pas_d_en_tete_de_desabonnement(
    tenant, mailoutbox
):
    """
    Billets, achats, réservations, bénévolat : on ne se désabonne pas d'un mail
    transactionnel. Pas d'en-tête List-Unsubscribe.
    / Transactional emails carry no List-Unsubscribe header.
    """
    with tenant_context(tenant):
        envoyer_un_mail_de_test()

    assert "List-Unsubscribe" not in mailoutbox[0].extra_headers
    assert "List-Unsubscribe" not in mailoutbox[0].message()


def test_le_formulaire_de_contact_repond_au_visiteur(tenant, mailoutbox):
    """
    Le message du formulaire de contact part au lieu : quand le lieu clique
    « Répondre », il doit écrire au visiteur, pas à sa propre adresse.
    / The venue's reply must go to the visitor, not to the venue itself.
    """
    from BaseBillet.tasks import contact_mailer

    # logo=None : le gabarit est rendu, et la base des mails lit le logo du lieu.
    # / logo=None: the template is rendered and the email base reads the venue logo.
    configuration_avec_email = SimpleNamespace(
        email="contact-du-lieu@mock.test", organisation="Lieu de test", logo=None
    )

    with tenant_context(tenant):
        with patch(
            "BaseBillet.tasks.Configuration.get_solo",
            return_value=configuration_avec_email,
        ):
            contact_mailer("visiteur@mock.test", "Une question", "Bonjour")

    assert len(mailoutbox) == 1
    assert mailoutbox[0].reply_to == ["visiteur@mock.test"]
