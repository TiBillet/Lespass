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
    5. cree un `Paiement_stripe(source=TRANSFERT)` ;
    6. ecrit sa vente « virement recu » (article `VR`, reglement `SN`), de cle
       `virement-recu-<uuid du paiement>`, par la fabrique
       `BaseBillet.services_vente.ecrire_la_vente_d_un_virement_recu`. Un echec de
       cette ecriture ne fait pas perdre le virement : reponse 201, ligne ERROR au
       journal, vente a rattraper (`rattraper_les_virements_recus`).
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

import logging
import uuid as uuid_module
from types import SimpleNamespace
from unittest import mock

import pytest
from django.db import connection
from django.test import Client as DjangoClient
from django.utils import timezone
from django_tenants.utils import tenant_context

from BaseBillet.models import (
    Configuration,
    FedowTransaction,
    LigneArticle,
    Paiement_stripe,
    PaymentMethod,
    Product,
)
from BaseBillet.models_vente import Reglement, Vente
from Customers.models import Client as TenantClient

pytestmark = pytest.mark.django_db

URL_DU_WEBHOOK = '/api/webhook_stripe/'
COMPTE_CONNECT_DU_LIEU = 'acct_TEST_lespass'
MONTANT_DU_VIREMENT = 1000  # en centimes / in cents

# La cle d'idempotence de la vente ecrite par le webhook : "virement-recu-<uuid>".
# / The idempotency key of the sale written by the webhook.
PREFIXE_DE_LA_CLE_D_UN_VIREMENT_RECU = 'virement-recu-'

# Le journal de la vue du webhook. / The webhook view logger.
NOM_DU_JOURNAL_DU_WEBHOOK = 'ApiBillet.views'


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


def _ventes_du_paiement(lieu, paiement):
    """Les ventes qui portent la cle du virement de ce paiement.
    / The sales holding this payment's transfer key."""
    with tenant_context(lieu):
        return list(
            Vente.objects.filter(
                idempotency_key=f'{PREFIXE_DE_LA_CLE_D_UN_VIREMENT_RECU}{paiement.uuid}',
            )
        )


def _regler_stripe_sur_un_virement_vers_le_lieu(simulacres, identifiant_du_virement):
    """Stripe confirme le virement : vers le lieu, du bon montant.
    / Stripe confirms the transfer: to the venue, for the right amount."""
    simulacres.stripe.id = identifiant_du_virement
    simulacres.stripe.destination = COMPTE_CONNECT_DU_LIEU
    simulacres.stripe.amount = MONTANT_DU_VIREMENT


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

    # Une seule vente « virement recu », malgre le rejeu.
    # / A single "transfer received" sale, despite the replay.
    assert len(_ventes_du_paiement(lieu, paiements[0])) == 1


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


# ---------------------------------------------------------------------------
# D. La vente « virement recu »
# ---------------------------------------------------------------------------


def test_D_un_virement_accepte_ecrit_sa_vente_virement_recu_reliee_au_paiement(
    lieu, identifiant_du_virement, simulacres,
):
    """
    Un `transfer.created` accepte ecrit la vente « virement recu » du paiement :
    reglee, encaissee maintenant, de cle `virement-recu-<uuid du paiement>`, un article
    `VR` du montant, un reglement `SN` du montant relie au paiement. Le paiement recoit
    sa vente.
    / An accepted transfer writes its VR sale, settled now, linked to the payment.
    """
    _regler_stripe_sur_un_virement_vers_le_lieu(simulacres, identifiant_du_virement)
    payload = _payload_transfer_created(
        identifiant_du_virement, COMPTE_CONNECT_DU_LIEU, MONTANT_DU_VIREMENT,
    )

    moment_avant_le_webhook = timezone.now()
    reponse = _poster_le_webhook(payload)
    moment_apres_le_webhook = timezone.now()

    assert reponse.status_code == 201
    paiements = _paiements_du_virement(lieu, identifiant_du_virement)
    assert len(paiements) == 1
    paiement = paiements[0]

    ventes = _ventes_du_paiement(lieu, paiement)
    assert len(ventes) == 1
    vente = ventes[0]
    assert vente.statut == Vente.Statut.REGLEE
    assert moment_avant_le_webhook <= vente.datetime_encaissement
    assert vente.datetime_encaissement <= moment_apres_le_webhook

    with tenant_context(lieu):
        paiement_relu = Paiement_stripe.objects.get(pk=paiement.pk)
        assert paiement_relu.vente_id == vente.pk

        articles_de_la_vente = list(
            LigneArticle.objects.filter(vente=vente).select_related(
                'pricesold__productsold__product'
            )
        )
        assert len(articles_de_la_vente) == 1
        produit_de_l_article = articles_de_la_vente[0].pricesold.productsold.product
        assert produit_de_l_article.methode_caisse == Product.VIREMENT_RECU
        assert articles_de_la_vente[0].amount == MONTANT_DU_VIREMENT

        reglements_de_la_vente = list(Reglement.objects.filter(vente=vente))
        assert len(reglements_de_la_vente) == 1
        assert reglements_de_la_vente[0].moyen == PaymentMethod.STRIPE_NOFED
        assert reglements_de_la_vente[0].montant == MONTANT_DU_VIREMENT
        assert reglements_de_la_vente[0].paiement_stripe_id == paiement.pk


def test_D_un_echec_de_la_vente_ne_fait_pas_perdre_le_virement(
    lieu, identifiant_du_virement, simulacres, caplog,
):
    """
    La fabrique de la vente leve une exception (simulee). Le virement n'est pas perdu :
    reponse 201, paiement cree, Fedow et LaBoutik appeles. Aucune vente n'est ecrite,
    et une ligne ERROR part au journal : la vente reste a rattraper.

    Le simulacre remplace la fabrique dans `BaseBillet.services_vente` : le webhook
    doit la lire dans ce module au moment de l'appel (import local dans la branche).
    / The factory raises: response 201, payment created, Fedow and LaBoutik called, no
    sale, one ERROR log line. The fake replaces the factory in BaseBillet.services_vente.
    """
    _regler_stripe_sur_un_virement_vers_le_lieu(simulacres, identifiant_du_virement)
    payload = _payload_transfer_created(
        identifiant_du_virement, COMPTE_CONNECT_DU_LIEU, MONTANT_DU_VIREMENT,
    )

    with caplog.at_level(logging.ERROR, logger=NOM_DU_JOURNAL_DU_WEBHOOK):
        with mock.patch(
            'BaseBillet.services_vente.ecrire_la_vente_d_un_virement_recu',
            side_effect=RuntimeError('panne simulee de la vente'),
        ):
            reponse = _poster_le_webhook(payload)

    assert reponse.status_code == 201
    assert len(simulacres.fedow.payloads_recus) == 1
    assert simulacres.laboutik.call_count == 1

    paiements = _paiements_du_virement(lieu, identifiant_du_virement)
    assert len(paiements) == 1
    paiement = paiements[0]
    assert paiement.vente_id is None
    assert _ventes_du_paiement(lieu, paiement) == []

    erreurs_du_webhook = []
    for enregistrement in caplog.records:
        if (
            enregistrement.name == NOM_DU_JOURNAL_DU_WEBHOOK
            and enregistrement.levelno >= logging.ERROR
        ):
            erreurs_du_webhook.append(enregistrement)
    assert len(erreurs_du_webhook) >= 1


def test_D_le_journal_et_la_reponse_affichent_l_uuid_court_du_paiement(
    lieu, identifiant_du_virement, simulacres, caplog,
):
    """
    Le journal et la reponse du webhook nomment le paiement par son uuid court
    (`uuid_8()`), jamais par la representation d'une methode (« bound method »).
    / The log and the response show the payment short uuid, never "bound method".
    """
    _regler_stripe_sur_un_virement_vers_le_lieu(simulacres, identifiant_du_virement)
    payload = _payload_transfer_created(
        identifiant_du_virement, COMPTE_CONNECT_DU_LIEU, MONTANT_DU_VIREMENT,
    )

    with caplog.at_level(logging.INFO, logger=NOM_DU_JOURNAL_DU_WEBHOOK):
        reponse = _poster_le_webhook(payload)

    assert reponse.status_code == 201
    paiement = _paiements_du_virement(lieu, identifiant_du_virement)[0]
    uuid_court_du_paiement = paiement.uuid_8()

    messages_du_webhook = []
    for enregistrement in caplog.records:
        if enregistrement.name == NOM_DU_JOURNAL_DU_WEBHOOK:
            messages_du_webhook.append(enregistrement.getMessage())

    messages_qui_nomment_le_paiement = []
    for message in messages_du_webhook:
        assert 'bound method' not in message
        if uuid_court_du_paiement in message:
            messages_qui_nomment_le_paiement.append(message)
    assert len(messages_qui_nomment_le_paiement) >= 1

    texte_de_la_reponse = reponse.content.decode()
    assert 'bound method' not in texte_de_la_reponse
    assert uuid_court_du_paiement in texte_de_la_reponse
