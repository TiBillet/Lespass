"""
fedow_connect/services.py — Services metier qui parlent au serveur Fedow distant.
/ fedow_connect/services.py — Business services that talk to the remote Fedow server.

LOCALISATION : fedow_connect/services.py

POURQUOI CE MODULE / WHY THIS MODULE :
`fedow_core` est le moteur de portefeuille LOCAL. Il est volontairement hermetique au
reseau : il n'importe jamais `fedow_connect`. C'est ce qui permettra un jour de debrancher
le Fedow legacy sans toucher au moteur.
Consequence : tout ce qui doit PARLER a Fedow avant de toucher au moteur vit ici, et les
appelants (POS, parcours web, seed) composent les deux.
/ fedow_core is the LOCAL wallet engine and never imports fedow_connect. Anything that must
  TALK to Fedow before touching the engine lives here; callers compose the two.
"""

import logging

from django.db import transaction as db_transaction

logger = logging.getLogger(__name__)


# Fragment du message leve par `WalletFedow.get_or_create_wallet` quand l'uuid rendu par
# Fedow differe de celui que le user porte en local (`fedow_connect/fedow_api.py`). Ce
# client leve une `Exception` nue, sans classe dediee : le message est le seul marqueur
# disponible. Si un jour le client gagne une exception typee, c'est ici qu'on la branche.
# / Fragment of the message raised by get_or_create_wallet on a diverging uuid. That client
#   raises a bare Exception, so the message is the only available marker.
MARQUEUR_WALLET_DIVERGENT = "mismatch"


def declarer_wallet_user_a_fedow(user, tenant, ip="0.0.0.0"):
    """
    Declare un user aupres de Fedow et retourne SON wallet Fedow, miroite en local.
    / Declares a user to Fedow and returns THEIR Fedow wallet, mirrored locally.

    LOCALISATION : fedow_connect/services.py

    C'est le SEUL appel qui transmet la cle publique du user (`public_pem`). Sans lui, un
    user se retrouve avec un Wallet local a uuid aleatoire, que Fedow ne connait pas : plus
    aucune requete signee en son nom ne passe (Fedow authentifie via l'en-tete
    `Wallet: <uuid>`), son FED devient invisible au point de vente, et le prochain
    `get_or_create_wallet` echoue sur « Wallet and member mismatch », a vie.
    / This is the ONLY call carrying the user's public key. Without it the user ends up with
      a random-uuid local Wallet that Fedow cannot authenticate.

    DEUX CAS :
    1. Cas nominal — Fedow cree (ou retrouve) le wallet du user, le client le miroite en
       local et le pose sur `user.wallet`.
    2. Wallet local divergent — le user porte deja un wallet a uuid aleatoire (fabrique
       avant que cette regle existe). Fedow rend un autre uuid, le client leve. On repare :
       on detache le wallet local EN MEMOIRE seulement, on redemande a Fedow, puis on
       deplace le solde de l'ancien wallet vers le nouveau par des Transaction(FUSION).

    POURQUOI « EN MEMOIRE SEULEMENT » : `_post` lit `user.wallet` en memoire pour composer
    l'en-tete, et `get_or_create_wallet` ne sauve qu'en cas de succes. En ne persistant
    jamais `user.wallet = None`, on supprime la fenetre pendant laquelle un user existe sans
    wallet en base — fenetre qu'un crash rendrait permanente.
    / IN MEMORY ONLY: _post reads user.wallet in memory and get_or_create_wallet only saves
      on success, so we never persist a wallet-less user.

    POURQUOI DES Transaction(FUSION) ET PAS DES `.update()` EN MASSE : `Token` porte une
    contrainte d'unicite `(wallet, asset)` — le wallet Fedow peut deja porter un Token du
    meme asset, et un `.update()` aveugle leverait `IntegrityError` APRES avoir repointe le
    user, laissant son solde orphelin. Et toutes les FK vers `Wallet` sont en `PROTECT`
    (dont `LigneArticle.wallet`, en TENANT_APPS) : supprimer l'ancien wallet peut echouer a
    cause de lignes vivant dans un AUTRE schema. On deplace donc la valeur, on ne supprime
    rien, et on garde une piste d'audit.
    / FUSION transactions, not bulk .update(): Token has a unique (wallet, asset) constraint
      and every Wallet FK is PROTECT (including LigneArticle in TENANT_APPS). We move value,
      delete nothing, and keep an audit trail.

    Cette fonction fait des APPELS RESEAU : elle NE DOIT JAMAIS etre appelee dans un bloc
    `transaction.atomic()`. Un appel reseau sous transaction tient un verrou DB pendant
    toute la latence, et un rollback ferait disparaitre un user dont Fedow garde deja la
    cle RSA — cet email deviendrait indeclarable.
    / NETWORK CALLS: never call this inside a transaction.atomic() block.

    :param user: TibilletUser a declarer
    :param tenant: Client (tenant courant, pour tracer les Transaction de reparation)
    :param ip: str (adresse IP de la requete, pour l'audit)
    :return: Wallet (le miroir local du wallet Fedow du user)
    :raises Exception: Fedow injoignable ou refus. L'appelant decide quoi en faire.
    """
    # Import local : evite un import circulaire au chargement du module.
    # / Local import: avoids a circular import at module load.
    from fedow_connect.fedow_api import FedowAPI

    fedow_api = FedowAPI()

    try:
        wallet_fedow, _cree = fedow_api.wallet.get_or_create_wallet(user)
        return wallet_fedow
    except Exception as erreur_declaration:
        wallet_est_divergent = (
            MARQUEUR_WALLET_DIVERGENT in f"{erreur_declaration}".lower()
        )
        if not wallet_est_divergent:
            # Fedow injoignable, refuse, ou toute autre panne : ce n'est pas a nous de
            # decider. On remonte tel quel.
            # / Fedow unreachable or refusing: not our call, re-raise as is.
            raise

    # --- Reparation d'un wallet local divergent ---
    # / Repairing a diverging local wallet.
    wallet_local_divergent = user.wallet
    logger.warning(
        f"declarer_wallet_user_a_fedow : {user.email} porte un wallet LOCAL "
        f"({wallet_local_divergent.uuid}) que Fedow ne connait pas. Reparation en cours."
    )

    user.wallet = None  # en memoire seulement / in memory only
    wallet_fedow, _cree = fedow_api.wallet.get_or_create_wallet(user)

    try:
        _deplacer_le_solde(
            wallet_source=wallet_local_divergent,
            wallet_cible=wallet_fedow,
            user=user,
            tenant=tenant,
            ip=ip,
        )
    except Exception:
        # Le solde n'a pas pu suivre : on rend son wallet d'origine au user plutot que de
        # le laisser pointer un wallet vide pendant que son argent dort ailleurs.
        # / The balance could not follow: give the user their original wallet back rather
        #   than leaving them pointing at an empty wallet while their money sits elsewhere.
        user.wallet = wallet_local_divergent
        user.save(update_fields=["wallet"])
        logger.error(
            f"declarer_wallet_user_a_fedow : deplacement du solde de {user.email} echoue, "
            f"wallet local {wallet_local_divergent.uuid} restaure."
        )
        raise

    logger.info(
        f"declarer_wallet_user_a_fedow : {user.email} aligne sur son wallet Fedow "
        f"({wallet_fedow.uuid}), ancien wallet local {wallet_local_divergent.uuid} vide."
    )
    return wallet_fedow


def _deplacer_le_solde(wallet_source, wallet_cible, user, tenant, ip="0.0.0.0"):
    """
    Deplace tout le solde d'un wallet vers un autre, asset par asset.
    / Moves a wallet's whole balance to another one, asset by asset.

    LOCALISATION : fedow_connect/services.py

    Reprend exactement le mecanisme de `WalletService.fusionner_wallet_ephemere` : une
    `Transaction(FUSION)` par asset, sous verrou, dans un seul bloc atomic. Le wallet source
    reste en base, vide, pour l'audit — on ne supprime jamais un wallet qui a porte de la
    valeur.
    / Same mechanism as fusionner_wallet_ephemere: one FUSION transaction per asset, under
      lock, in a single atomic block. The source wallet stays in DB, empty, for audit.

    :param wallet_source: Wallet a vider
    :param wallet_cible: Wallet a crediter
    :param user: TibilletUser (pour le commentaire d'audit)
    :param tenant: Client
    :param ip: str
    """
    from fedow_core.models import Token, Transaction
    from fedow_core.services import TransactionService

    with db_transaction.atomic():
        # `select_for_update` : le montant doit etre lu sous le meme verrou que celui du
        # debit, sinon un paiement concurrent le fait fondre entre la lecture et l'ecriture.
        # / Read the amount under the same lock as the debit, otherwise a concurrent payment
        #   shrinks it between read and write.
        tokens_a_deplacer = Token.objects.select_for_update().filter(
            wallet=wallet_source,
            value__gt=0,
        )
        for token_a_deplacer in tokens_a_deplacer:
            TransactionService.creer(
                sender=wallet_source,
                receiver=wallet_cible,
                asset=token_a_deplacer.asset,
                montant_en_centimes=token_a_deplacer.value,
                action=Transaction.FUSION,
                tenant=tenant,
                ip=ip,
                comment=f"Alignement du wallet de {user.email} sur Fedow",
            )
