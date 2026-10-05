"""
Le webhook Stripe `invoice.paid` ignore un abonnement qui n'a pas ete cree par Lespass.
/ The Stripe `invoice.paid` webhook skips a subscription not created by Lespass.

LOCALISATION : tests/pytest/test_webhook_invoice_paid_sans_metadata.py

Code teste / Tested code : ApiBillet/views.py, branche `invoice.paid` de `Webhook_stripe`.

Avec Stripe Connect, la plateforme recoit les webhooks de TOUS les comptes connectes.
Un lieu peut creer un abonnement directement dans son dashboard Stripe : ses
renouvellements arrivent ici sans les metadata TiBillet (`tenant`, `membership_uuid`,
`price_uuid`). La vue doit alors :
- repondre 204, pour que Stripe arrete de reessayer ;
- ecrire un log de niveau ERROR, pour que Sentry leve une alerte.
/ With Stripe Connect, the platform receives every connected account's webhooks. A
renewal without TiBillet metadata must get a 204 and an ERROR log.

Le webhook est en `AllowAny` et ne verifie pas la signature : on le poste directement.
/ The webhook is AllowAny with no signature check: we post to it directly.

Lancer / Run :
    docker exec lespass_django poetry run pytest \
        tests/pytest/test_webhook_invoice_paid_sans_metadata.py -q
"""

import uuid as uuid_module
from unittest import mock

import pytest
from django.test import Client as DjangoClient

pytestmark = pytest.mark.django_db

URL_DU_WEBHOOK = "/api/webhook_stripe/"


def _payload_renouvellement(metadata_de_l_abonnement):
    """
    Un evenement `invoice.paid` de renouvellement, tel que Stripe l'envoie
    (seulement les champs lus par la vue).
    / A renewal `invoice.paid` event (only the fields the view reads).
    """
    identifiant_unique = uuid_module.uuid4().hex[:12]
    return {
        "id": f"evt_TEST_{identifiant_unique}",
        "type": "invoice.paid",
        "data": {
            "object": {
                "id": f"in_TEST_{identifiant_unique}",
                "object": "invoice",
                "billing_reason": "subscription_cycle",
                "paid": True,
                "status": "paid",
                "account_name": "Lieu de test",
                "subscription": f"sub_TEST_{identifiant_unique}",
                "subscription_details": {"metadata": metadata_de_l_abonnement},
            }
        },
    }


def _poster_le_webhook(payload):
    """POST JSON vers le webhook, sans lever les exceptions de la vue.
    / JSON POST to the webhook, without raising view exceptions."""
    client = DjangoClient(
        HTTP_HOST="lespass.tibillet.localhost", raise_request_exception=False
    )
    return client.post(URL_DU_WEBHOOK, data=payload, content_type="application/json")


def test_un_abonnement_sans_metadata_tibillet_recoit_un_204():
    """
    Metadata vides : reponse 204, et pas de 500.
    / Empty metadata: 204 answer, no 500.
    """
    reponse = _poster_le_webhook(_payload_renouvellement({}))

    assert reponse.status_code == 204


def test_un_abonnement_sans_metadata_tibillet_ecrit_un_log_error():
    """
    Metadata vides : un log ERROR qui cite l'abonnement, pour l'alerte Sentry.
    / Empty metadata: an ERROR log naming the subscription, for the Sentry alert.
    """
    payload = _payload_renouvellement({})
    identifiant_de_l_abonnement = payload["data"]["object"]["subscription"]

    with mock.patch("ApiBillet.views.logger") as faux_logger:
        _poster_le_webhook(payload)

    messages_d_erreur = []
    for appel in faux_logger.error.call_args_list:
        messages_d_erreur.append(str(appel.args[0]))
    assert any(identifiant_de_l_abonnement in message for message in messages_d_erreur)
