"""
Le webhook d'adhesion ne part QU'APRES le COMMIT de la transaction.
/ The membership webhook is only dispatched AFTER the transaction COMMIT.

LOCALISATION : tests/pytest/test_webhook_membership_on_commit.py

Le receveur BaseBillet.signals.create_lignearticle_if_membership_created_on_admin
doit dispatcher webhook_membership via transaction.on_commit. Sinon le worker
Celery, qui a sa propre connexion a la base, lit l'adhesion avant le COMMIT et
leve DoesNotExist ; et une transaction annulee (formset admin invalide) envoie un
webhook pour une adhesion qui n'existera jamais.
/ The signal must dispatch webhook_membership through transaction.on_commit: the
Celery worker has its own DB connection and would raise DoesNotExist.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import tenant_context

from BaseBillet.models import Membership

pytestmark = pytest.mark.django_db


# tenant_context (et non schema_context) : schema_context pose un FakeTenant,
# et tout code qui lit connection.tenant.uuid plante alors.
# / tenant_context, never schema_context: the latter installs a FakeTenant.
def test_webhook_membership_est_dispatche_seulement_apres_le_commit(
    tenant, django_capture_on_commit_callbacks
):
    """Le dispatch Celery est differe jusqu'au COMMIT, puis il part avec le bon pk."""
    with tenant_context(tenant):
        with patch(
            "BaseBillet.signals.webhook_membership.delay"
        ) as dispatch_celery_du_webhook:
            with django_capture_on_commit_callbacks(
                execute=False
            ) as callbacks_differes:
                # price et user restent vides (ils sont optionnels) : creer un
                # Product/Price declencherait les signaux Fedow, donc des appels
                # reseau. Le status par defaut (ONCE) evite la LigneArticle.
                # / price and user stay empty: a Product/Price would trigger Fedow.
                adhesion_valide = Membership.objects.create(
                    deadline=timezone.localtime() + timedelta(days=30),
                    last_name="TestOnCommitWebhook",
                )

                assert dispatch_celery_du_webhook.call_count == 0, (
                    "Le webhook est parti avant le COMMIT : le worker Celery "
                    "lirait l'adhesion avant qu'elle existe (DoesNotExist)."
                )

            assert len(callbacks_differes) == 1

            # On joue le callback : c'est ce que fait le COMMIT reel.
            # / Run the callback: this is what the real COMMIT does.
            callbacks_differes[0]()
            dispatch_celery_du_webhook.assert_called_once_with(adhesion_valide.pk)


def test_webhook_membership_ne_part_pas_si_la_transaction_est_annulee(tenant):
    """Transaction annulee (formset admin invalide) : aucun webhook n'est envoye."""
    with tenant_context(tenant):
        with patch(
            "BaseBillet.signals.webhook_membership.delay"
        ) as dispatch_celery_du_webhook:
            # Cas de l'admin : l'adhesion est sauvee, puis la transaction est
            # annulee parce qu'un formset inline est invalide.
            # / Admin case: membership saved, then rolled back on an invalid inline.
            try:
                with transaction.atomic():
                    Membership.objects.create(
                        deadline=timezone.localtime() + timedelta(days=30),
                        last_name="TestRollbackWebhook",
                    )
                    raise RuntimeError("formset inline invalide")
            except RuntimeError:
                pass

            # Le ROLLBACK jette les callbacks on_commit.
            # / ROLLBACK discards on_commit callbacks.
            assert dispatch_celery_du_webhook.call_count == 0, (
                "Un webhook est parti pour une adhesion annulee par le ROLLBACK."
            )
