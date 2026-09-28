"""
tests/pytest/test_webhook_transfer_created.py
Le webhook Stripe `transfer.created` : la remise en banque de la monnaie federee.
/ The Stripe `transfer.created` webhook: the federated currency bank deposit.

LOCALISATION : tests/pytest/test_webhook_transfer_created.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
Quand la plateforme vire des euros au compte Stripe Connect d'un lieu, Stripe
appelle `/api/webhook_stripe/` avec un evenement `transfer.created`. Lespass :
    1. relit le virement chez Stripe (`stripe.Transfer.retrieve`) ;
    2. retrouve le lieu dont le compte Connect est le destinataire ;
    3. demande au Fedow de vider d'autant le portefeuille FED du lieu ;
    4. previent LaBoutik V1 (ligne comptable « Stripe TiBillet transfert ») ;
    5. cree un `Paiement_stripe(source=TRANSFERT)`.
Code : ApiBillet/views.py, branche `transfer.created` de `Webhook_stripe`.

Le webhook est en `AllowAny` et la signature Stripe n'est pas verifiee : le
payload peut venir de n'importe qui. Seule la relecture chez Stripe fait foi.
/ The webhook is AllowAny and the Stripe signature is not checked: the payload
may come from anyone. Only the Stripe re-read is trustworthy.

LES SIMULACRES / THE FAKES
--------------------------
- `stripe.Transfer.retrieve` : rend le virement tel que Stripe le connait. Il
  fournit la VERITE Stripe, il ne decide pas du resultat verifie.
- `FedowSimule` : un Fedow distant qui se souvient des virements deja traites
  et, comme le vrai (Fedow/fedow_core/views.py, global_asset_bank_stripe_deposit),
  rend la meme transaction si on lui renvoie un virement deja traite.
- `send_stripe_bank_deposit_to_laboutik.delay` : capture ce qui part a LaBoutik.
- `Configuration.get_stripe_connect_account` : attribue un compte Connect a chaque
  lieu. Indispensable : la vraie methode CREE un compte chez Stripe pour un lieu
  qui n'en a pas, et le webhook parcourt tous les lieux.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/pytest/test_webhook_transfer_created.py -v
"""

import uuid as uuid_module
from types import SimpleNamespace
from unittest import mock

import pytest
from django.db import connection
from django.test import Client as DjangoClient
from django.utils import timezone
from django_tenants.utils import tenant_context

from BaseBillet.models import Configuration, FedowTransaction, Paiement_stripe
from Customers.models import Client as TenantClient

pytestmark = pytest.mark.django_db

URL_DU_WEBHOOK = '/api/webhook_stripe/'
COMPTE_CONNECT_DU_LIEU = 'acct_TEST_lespass'
MONTANT_DU_VIREMENT = 1000  # en centimes / in cents


# ---------------------------------------------------------------------------
# Les simulacres
# ---------------------------------------------------------------------------


class FedowSimule:
    """Un Fedow distant qui se souvient des remises deja traitees.
    / A remote Fedow that remembers the deposits already processed.

    Comme le vrai Fedow, il deduplique sur l'identifiant du virement : un virement
    deja traite rend la MEME transaction (le vrai repond HTTP 208).
    / Like the real Fedow, it deduplicates on the transfer id.
    """

    def __init__(self):
        # Chaque appel recu, dans l'ordre. / Every call received, in order.
        self.payloads_recus = []
        # Identifiant du virement -> transaction deja creee.
        # / Transfer id -> transaction already created.
        self.transactions_par_virement = {}
        self.wallet = self

    def global_asset_bank_stripe_deposit(self, payload):
        self.payloads_recus.append(payload)
        identifiant_du_virement = payload['data']['object']['id']

        if identifiant_du_virement not in self.transactions_par_virement:
            # La transaction vit dans le schema du lieu : l'appel est fait
            # depuis son tenant_context.
            # / The transaction lives in the venue schema.
            transaction = FedowTransaction.objects.create(
                hash=uuid_module.uuid4().hex + uuid_module.uuid4().hex,
                datetime=timezone.now(),
            )
            self.transactions_par_virement[identifiant_du_virement] = transaction

        transaction = self.transactions_par_virement[identifiant_du_virement]
        return SimpleNamespace(fedow_transaction=transaction)


def _compte_connect_selon_le_lieu(self):
    """Le lieu `lespass` possede le compte vise ; les autres ont chacun le leur.
    / The `lespass` venue owns the targeted account; the others each have their own."""
    if connection.schema_name == 'lespass':
        return COMPTE_CONNECT_DU_LIEU
    return f'acct_TEST_autre_{connection.schema_name}'


def _payload_transfer_created(identifiant_du_virement, destination, montant):
    """Un evenement `transfer.created` tel que Stripe l'envoie (champs utiles).
    / A `transfer.created` event as Stripe sends it (useful fields)."""
    return {
        'id': f'evt_TEST_{uuid_module.uuid4().hex[:12]}',
        'type': 'transfer.created',
        'data': {
            'object': {
                'id': identifiant_du_virement,
                'object': 'transfer',
                'amount': montant,
                'currency': 'eur',
                'destination': destination,
                'created': int(timezone.now().timestamp()),
                'metadata': {},
            },
        },
    }


@pytest.fixture
def lieu():
    return TenantClient.objects.get(schema_name='lespass')


@pytest.fixture
def identifiant_du_virement():
    return f'tr_TEST_{uuid_module.uuid4().hex[:16]}'


@pytest.fixture
def simulacres():
    """Branche Stripe, Fedow et LaBoutik sur des simulacres.
    / Plugs Stripe, Fedow and LaBoutik into fakes.

    `stripe.virement` est ce que Stripe repond : chaque test le regle AVANT
    d'appeler le webhook. / `stripe.virement` is Stripe's answer.
    """
    fedow = FedowSimule()
    virement_chez_stripe = SimpleNamespace(id=None, destination=None, amount=None)

    with (
        mock.patch('stripe.Transfer.retrieve', return_value=virement_chez_stripe),
        mock.patch('ApiBillet.views.FedowAPI', return_value=fedow),
        mock.patch('ApiBillet.views.send_stripe_bank_deposit_to_laboutik') as laboutik,
        mock.patch.object(
            Configuration, 'get_stripe_connect_account', _compte_connect_selon_le_lieu,
        ),
    ):
        yield SimpleNamespace(
            fedow=fedow,
            stripe=virement_chez_stripe,
            laboutik=laboutik.delay,
        )


def _poster_le_webhook(payload):
    # raise_request_exception=False : un refus par exception devient une reponse
    # 500, comme Stripe la recevrait. / A refusal by exception becomes a 500.
    client = DjangoClient(HTTP_HOST='lespass.tibillet.localhost', raise_request_exception=False)
    return client.post(URL_DU_WEBHOOK, data=payload, content_type='application/json')


def _paiements_du_virement(lieu, identifiant_du_virement):
    with tenant_context(lieu):
        return list(Paiement_stripe.objects.filter(payment_intent_id=identifiant_du_virement))


# ---------------------------------------------------------------------------
# A. Le destinataire
# ---------------------------------------------------------------------------


def test_A_virement_vers_un_autre_compte_ne_vide_pas_le_portefeuille_du_lieu(
    lieu, identifiant_du_virement, simulacres,
):
    """
    Le payload dit « virement vers le lieu », Stripe dit « vers un autre compte ».
    / The payload says "to the venue", Stripe says "to another account".

    EN PRATIQUE : le Fedow ne verifie pas le destinataire, il vide le portefeuille
    du lieu qui l'appelle. Sans ce controle, le virement d'un lieu B viderait le
    portefeuille FED du lieu A, qui n'aurait rien recu.
    / In practice the Fedow does not check the recipient: without this check,
    venue B's transfer would drain venue A's FED wallet.
    """
    simulacres.stripe.id = identifiant_du_virement
    simulacres.stripe.destination = 'acct_TEST_un_autre_lieu'
    simulacres.stripe.amount = MONTANT_DU_VIREMENT

    payload = _payload_transfer_created(
        identifiant_du_virement, COMPTE_CONNECT_DU_LIEU, MONTANT_DU_VIREMENT,
    )
    reponse = _poster_le_webhook(payload)

    assert reponse.status_code == 400
    assert simulacres.fedow.payloads_recus == []
    assert simulacres.laboutik.call_count == 0
    assert _paiements_du_virement(lieu, identifiant_du_virement) == []


# ---------------------------------------------------------------------------
# B. Le rejeu
# ---------------------------------------------------------------------------


def test_B_le_meme_evenement_rejoue_n_est_traite_qu_une_fois(
    lieu, identifiant_du_virement, simulacres,
):
    """
    Stripe livre un evenement « au moins une fois » et relance en cas d'erreur.
    / Stripe delivers an event "at least once" and retries on error.

    Le second envoi doit etre reconnu par Lespass : un seul appel au Fedow, un
    seul `Paiement_stripe`. / The second delivery must be recognised by Lespass.
    """
    simulacres.stripe.id = identifiant_du_virement
    simulacres.stripe.destination = COMPTE_CONNECT_DU_LIEU
    simulacres.stripe.amount = MONTANT_DU_VIREMENT

    payload = _payload_transfer_created(
        identifiant_du_virement, COMPTE_CONNECT_DU_LIEU, MONTANT_DU_VIREMENT,
    )
    premiere_reponse = _poster_le_webhook(payload)
    seconde_reponse = _poster_le_webhook(payload)

    assert premiere_reponse.status_code == 201
    assert seconde_reponse.status_code == 208
    assert len(simulacres.fedow.payloads_recus) == 1
    assert simulacres.laboutik.call_count == 1

    paiements = _paiements_du_virement(lieu, identifiant_du_virement)
    assert len(paiements) == 1
    assert paiements[0].source == Paiement_stripe.TRANSFERT
    assert paiements[0].total() == MONTANT_DU_VIREMENT / 100


# ---------------------------------------------------------------------------
# C. Le montant
# ---------------------------------------------------------------------------


def test_C_un_montant_falsifie_dans_le_payload_est_refuse(
    lieu, identifiant_du_virement, simulacres,
):
    """
    Stripe dit 10 € ; le payload annonce 9 999,99 €.
    / Stripe says 10 €; the payload claims 9,999.99 €.

    EN PRATIQUE : le Fedow relit le montant chez Stripe, le portefeuille serait
    debite du bon montant. Mais LaBoutik (`amount / 100`) et
    `Paiement_stripe.total()` lisent le payload : la ligne de caisse et l'admin
    afficheraient 9 999,99 €. Un payload qui contredit Stripe doit etre refuse,
    comme un destinataire qui contredit Stripe.
    / The Fedow re-reads Stripe, but LaBoutik and `Paiement_stripe.total()` read
    the payload. A payload that contradicts Stripe must be refused.
    """
    simulacres.stripe.id = identifiant_du_virement
    simulacres.stripe.destination = COMPTE_CONNECT_DU_LIEU
    simulacres.stripe.amount = MONTANT_DU_VIREMENT

    montant_falsifie = 999999
    payload = _payload_transfer_created(
        identifiant_du_virement, COMPTE_CONNECT_DU_LIEU, montant_falsifie,
    )
    reponse = _poster_le_webhook(payload)

    assert reponse.status_code == 400
    assert simulacres.fedow.payloads_recus == []
    assert simulacres.laboutik.call_count == 0
    assert _paiements_du_virement(lieu, identifiant_du_virement) == []
