"""
Les logs n'ecrivent ni e-mail, ni lien de connexion, ni message sur plusieurs lignes.
/ Logs write no email, no login link, and no multi-line message.

LOCALISATION : tests/pytest/test_logs_sans_email.py

Les logs partent dans la supervision (OpenObserve) et y restent un an. Docker coupe
un message a chaque retour a la ligne : chaque morceau devient une entree a part,
sans niveau, sans lieu, sans module.
/ Logs reach the monitoring for a year. Docker splits a message at each newline.

Lancer / Run :
    docker exec lespass_django poetry run pytest tests/pytest/test_logs_sans_email.py -v
"""

import logging
import uuid
from unittest import mock

import pytest
from django.test import override_settings
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from Customers.models import Client as TenantClient
from TiBillet.identifiants_pour_les_logs import uuid_court


@pytest.fixture
def tenant_lespass():
    return TenantClient.objects.get(schema_name="lespass")


@pytest.fixture
def utilisateur_inactif(tenant_lespass):
    """
    Un utilisateur jetable, inactif, supprime a la fin du test.
    / A throwaway inactive user, deleted at the end of the test.
    """
    with tenant_context(tenant_lespass):
        email_jetable = f"logs-sans-email-{uuid.uuid4().hex[:8]}@exemple.org"
        utilisateur = TibilletUser.objects.create(
            email=email_jetable,
            username=email_jetable,
            espece=TibilletUser.TYPE_HUM,
            is_active=False,
        )
    yield utilisateur
    with tenant_context(tenant_lespass):
        TibilletUser.objects.filter(pk=utilisateur.pk).delete()


def test_machine_a_etat_ecrit_une_ligne_sans_email(tenant_lespass, utilisateur_inactif, caplog):
    """
    Un utilisateur qui passe de inactif a actif : la machine a etat ecrit UNE ligne,
    avec l'UUID court, sans l'e-mail (str(user) renvoie l'e-mail) et sans retour a la ligne.
    / A user going inactive -> active: one line, short UUID, no email, no newline.
    """
    caplog.set_level(logging.INFO, logger="BaseBillet.signals")

    with tenant_context(tenant_lespass):
        utilisateur_inactif.is_active = True
        utilisateur_inactif.save()

    lignes_de_la_machine_a_etat = []
    for enregistrement in caplog.records:
        message = enregistrement.getMessage()
        if "START MACHINE A ETAT" in message:
            lignes_de_la_machine_a_etat.append(message)

    assert len(lignes_de_la_machine_a_etat) == 1
    ligne = lignes_de_la_machine_a_etat[0]
    assert f"TIBILLETUSER {uuid_court(utilisateur_inactif.pk)} : False to True" in ligne
    assert "\n" not in ligne

    for enregistrement in caplog.records:
        assert utilisateur_inactif.email not in enregistrement.getMessage()


@override_settings(DEBUG=False)
def test_mail_de_connexion_ne_logge_ni_le_lien_ni_l_email(tenant_lespass, utilisateur_inactif, caplog):
    """
    Hors DEBUG, la tache d'envoi du mail de connexion ne logge pas le lien : son jeton
    ouvre le compte. Elle ne logge pas non plus l'e-mail.
    / Outside DEBUG, the login mail task logs neither the link (its token opens the
    account) nor the email.
    """
    from BaseBillet import tasks

    jeton_secret = "JETON-SECRET-DE-TEST"
    faux_lien_de_connexion = f"https://lespass.tibillet.localhost/emailconfirmation/{jeton_secret}"
    caplog.set_level(logging.INFO, logger="BaseBillet.tasks")

    with tenant_context(tenant_lespass):
        with mock.patch.object(tasks, "forge_connexion_url", return_value=faux_lien_de_connexion), \
                mock.patch.object(tasks, "CeleryMailerClass") as faux_mailer:
            tasks.connexion_celery_mailer(
                utilisateur_inactif.email,
                "https://lespass.tibillet.localhost",
            )

    # Le mail part bien avec le lien : seul le log change.
    # / The mail is still sent with the link: only the log changes.
    assert faux_mailer.call_args.kwargs["context"]["connexion_url"] == faux_lien_de_connexion

    for enregistrement in caplog.records:
        message = enregistrement.getMessage()
        assert jeton_secret not in message
        assert utilisateur_inactif.email not in message
