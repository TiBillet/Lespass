"""
Les tâches Celery liées à un nouvel utilisateur ou à une adhésion partent APRÈS le COMMIT.
/ Celery tasks tied to a new user or a membership are dispatched AFTER the COMMIT.

LOCALISATION : tests/pytest/test_taches_celery_apres_commit_issue_117.py

Code testé / Tested code :
- AuthBillet/utils.py : sender_mail_connect()
- BaseBillet/triggers.py : trigger_A (adhésion payée)

Issue GitHub #117 : une adhésion créée dans l'admin Django est écrite dans une transaction.
Le worker Celery a sa propre connexion à la base. Si la tâche part avant le COMMIT,
le worker ne trouve pas encore l'utilisateur ou l'adhésion, et plante sur « DoesNotExist ».
/ GitHub issue #117: a task dispatched before COMMIT makes the worker raise DoesNotExist.

Chaque test est marqué `django_db` : pytest-django l'exécute dans une transaction annulée
à la fin. `django_capture_on_commit_callbacks` retient ce qui partirait au COMMIT.
/ Every test runs in a rolled-back transaction.

Lancer / Run : make test ARGS="tests/pytest/test_taches_celery_apres_commit_issue_117.py"
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django_tenants.utils import tenant_context

from fabriques_panier import (
    catalogue_stripe_simule,
    client_connecte,
    creer_adhesion,
    creer_utilisateur,
    noms_des_taches,
    taches_celery_enregistrees,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, avec Stripe (catalogue) et Celery simulés pendant tout le test.
    / The `lespass` venue, with the Stripe catalogue and Celery faked for the whole test.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule() as catalogue_stripe:
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(
                    tenant=tenant,
                    catalogue_stripe=catalogue_stripe,
                    taches_demandees=taches_demandees,
                )


def adherer_gratuitement(acheteur, tarif):
    """POST du formulaire d'adhésion, pour une adhésion à 0 € (active tout de suite).
    / POST of the membership form, for a 0 € membership (active at once)."""
    return client_connecte(acheteur).post(
        "/memberships/",
        {
            "price": str(tarif.uuid),
            "email": acheteur.email,
            "firstname": "Test",
            "lastname": "Issue117",
            "acknowledge": "true",
            "newsletter": "on",
        },
        HTTP_HX_REQUEST="true",
    )


# --------------------------------------------------------------------------
# Mail de connexion d'un nouvel utilisateur (la trace Sentry de l'issue #117)
# / Login mail of a new user (the Sentry trace of issue #117)
# --------------------------------------------------------------------------


def test_le_mail_de_connexion_ne_part_pas_avant_le_commit(
    tenant, django_capture_on_commit_callbacks
):
    """Tant que la transaction n'est pas validée, la tâche Celery n'est pas envoyée.
    / Until the transaction commits, the Celery task is not dispatched."""
    from AuthBillet import utils as auth_utils

    with tenant_context(tenant):
        with patch.object(auth_utils.connexion_celery_mailer, "delay") as envoi_celery:
            with django_capture_on_commit_callbacks(execute=False):
                auth_utils.sender_mail_connect("issue117@mock.test")

                assert envoi_celery.call_count == 0


def test_le_mail_de_connexion_part_apres_le_commit(
    tenant, django_capture_on_commit_callbacks
):
    """Au COMMIT, la tâche Celery part une seule fois, avec le bon email.
    / On COMMIT, the Celery task is dispatched once, with the right email."""
    from AuthBillet import utils as auth_utils

    with tenant_context(tenant):
        with patch.object(auth_utils.connexion_celery_mailer, "delay") as envoi_celery:
            with django_capture_on_commit_callbacks(execute=True):
                auth_utils.sender_mail_connect("issue117@mock.test")

            assert envoi_celery.call_count == 1
            assert envoi_celery.call_args.args[0] == "issue117@mock.test"


# --------------------------------------------------------------------------
# Tâches d'une adhésion payée : mail de confirmation, Ghost, Brevo
# / Tasks of a paid membership: confirmation mail, Ghost, Brevo
# --------------------------------------------------------------------------


def test_les_taches_de_l_adhesion_ne_partent_pas_avant_le_commit(
    lieu, django_capture_on_commit_callbacks
):
    """Mail de confirmation, Ghost et Brevo : rien ne part avant le COMMIT.
    / Confirmation mail, Ghost and Brevo: nothing is dispatched before COMMIT."""
    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="0.00")
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=False):
        adherer_gratuitement(acheteur, adhesion.tarif)

        taches = noms_des_taches(lieu.taches_demandees)
        assert "send_membership_invoice_to_email" not in taches
        assert "send_to_ghost" not in taches
        assert "send_to_brevo" not in taches


def test_le_mail_de_confirmation_d_adhesion_part_apres_le_commit(
    lieu, django_capture_on_commit_callbacks
):
    """Au COMMIT, le mail de confirmation d'adhésion est demandé.
    / On COMMIT, the membership confirmation mail is requested."""
    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="0.00")

    with django_capture_on_commit_callbacks(execute=True):
        adherer_gratuitement(acheteur, adhesion.tarif)

    assert "send_membership_invoice_to_email" in noms_des_taches(lieu.taches_demandees)


def test_ghost_et_brevo_partent_apres_le_commit_si_newsletter_acceptee(
    lieu, django_capture_on_commit_callbacks
):
    """Au COMMIT, Ghost et Brevo sont demandés pour une adhésion avec newsletter.
    / On COMMIT, Ghost and Brevo are requested for a membership with newsletter."""
    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="0.00")

    with django_capture_on_commit_callbacks(execute=True):
        adherer_gratuitement(acheteur, adhesion.tarif)

    taches = noms_des_taches(lieu.taches_demandees)
    assert "send_to_ghost" in taches
    assert "send_to_brevo" in taches
