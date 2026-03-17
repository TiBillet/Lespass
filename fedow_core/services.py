"""
fedow_core/services.py — Couche de service du moteur de portefeuille.
fedow_core/services.py — Service layer for the wallet engine.

Ce fichier remplace fedow_connect/fedow_api.py (700 lignes HTTP).
Au lieu d'appeler un serveur Fedow distant, on fait des requetes DB directes.
This file replaces fedow_connect/fedow_api.py (700 lines of HTTP).
Instead of calling a remote Fedow server, we do direct DB queries.

REGLES / RULES:
- Toujours filtrer par tenant (SHARED_APPS = pas d'isolation auto).
  Always filter by tenant (SHARED_APPS = no automatic isolation).
- Toutes les valeurs monetaires sont en centimes (int).
  All monetary values are in cents (int).
- Les operations d'ecriture (crediter, debiter, creer) utilisent
  transaction.atomic() et select_for_update() pour l'integrite.
  Write operations (credit, debit, create) use
  transaction.atomic() and select_for_update() for integrity.
"""

import logging

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from fedow_core.exceptions import SoldeInsuffisant
from fedow_core.models import Asset, Federation, Token, Transaction

from AuthBillet.models import Wallet

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AssetService : gestion des monnaies et tokens
# AssetService: currency and token management
# ---------------------------------------------------------------------------

class AssetService:
    """
    Methodes statiques pour gerer les assets (monnaies/tokens).
    Static methods to manage assets (currencies/tokens).

    Toutes les methodes qui prennent un tenant en parametre
    filtrent les resultats par ce tenant.
    All methods that take a tenant parameter
    filter results by that tenant.
    """

    @staticmethod
    def obtenir_assets_du_tenant(tenant):
        """
        Retourne les assets crees par ce tenant (son propre lieu).
        Returns assets created by this tenant (its own venue).

        Exemple / Example:
            assets_du_lieu = AssetService.obtenir_assets_du_tenant(tenant=mon_lieu)
            → [monnaie_locale, points_fidelite, ...]
        """
        assets_du_tenant = Asset.objects.filter(
            tenant_origin=tenant,
        ).order_by('name')

        return assets_du_tenant

    @staticmethod
    def obtenir_assets_accessibles(tenant):
        """
        Retourne les assets que ce tenant peut utiliser :
        - ses propres assets (crees par lui)
        - les assets partages via une Federation

        Returns assets this tenant can use:
        - its own assets (created by it)
        - assets shared via a Federation

        Exemple / Example:
            assets = AssetService.obtenir_assets_accessibles(tenant=mon_lieu)
            → [ma_monnaie_locale, monnaie_federee_tibillet, ...]
        """
        # Recuperer les UUIDs des assets federes avec ce tenant.
        # Get UUIDs of assets federated with this tenant.
        federations_du_tenant = Federation.objects.filter(
            tenants=tenant,
        )
        assets_federes_uuids = federations_du_tenant.values_list(
            'assets__uuid', flat=True,
        )

        # Combiner : assets du tenant OU assets federes, actifs uniquement.
        # Combine: tenant's assets OR federated assets, active only.
        assets_accessibles = Asset.objects.filter(
            Q(tenant_origin=tenant) | Q(uuid__in=assets_federes_uuids),
            active=True,
        ).distinct().order_by('name')

        return assets_accessibles

    @staticmethod
    def creer_asset(tenant, name, category, currency_code, wallet_origin):
        """
        Cree un nouvel asset pour ce tenant.
        Creates a new asset for this tenant.

        Args:
            tenant: Client (le lieu createur / the creating venue)
            name: str (nom lisible / human-readable name)
            category: str (Asset.TLF, Asset.TNF, etc.)
            currency_code: str (3 caracteres : "EUR", "TMP", "PTS" / 3 chars)
            wallet_origin: Wallet (le wallet du lieu / the venue's wallet)

        Returns:
            Asset: l'asset cree / the created asset

        Exemple / Example:
            asset = AssetService.creer_asset(
                tenant=mon_lieu,
                name="Monnaie locale Reunion",
                category=Asset.TLF,
                currency_code="EUR",
                wallet_origin=mon_lieu_wallet,
            )
        """
        nouvel_asset = Asset.objects.create(
            name=name,
            category=category,
            currency_code=currency_code,
            wallet_origin=wallet_origin,
            tenant_origin=tenant,
        )

        logger.info(
            f"Asset cree : '{nouvel_asset.name}' ({nouvel_asset.category}) "
            f"pour le tenant {tenant.schema_name}"
        )

        return nouvel_asset


# ---------------------------------------------------------------------------
# WalletService : operations sur les soldes (Token)
# WalletService: balance operations (Token)
# ---------------------------------------------------------------------------

class WalletService:
    """
    Methodes statiques pour lire et modifier les soldes des wallets.
    Static methods to read and modify wallet balances.

    Les operations d'ecriture (crediter, debiter) utilisent
    select_for_update() pour verrouiller la ligne Token concernee.
    Ce verrou est par ligne (pas cross-tenant) et est relache
    a la fin de la transaction DB.

    Write operations (credit, debit) use select_for_update()
    to lock the relevant Token row. This lock is per-row
    (not cross-tenant) and is released at the end of the DB transaction.
    """

    @staticmethod
    def obtenir_solde(wallet, asset):
        """
        Retourne le solde (en centimes) d'un wallet pour un asset donne.
        Returns the balance (in cents) of a wallet for a given asset.

        Si le Token n'existe pas encore, retourne 0.
        If the Token doesn't exist yet, returns 0.

        Exemple / Example:
            solde = WalletService.obtenir_solde(wallet=alice.wallet, asset=monnaie_locale)
            → 1500  (= 15,00 EUR)
        """
        try:
            token = Token.objects.get(wallet=wallet, asset=asset)
            return token.value
        except Token.DoesNotExist:
            return 0

    @staticmethod
    def obtenir_tous_les_soldes(wallet):
        """
        Retourne tous les Tokens d'un wallet (tous les assets, tous les lieux).
        Returns all Tokens for a wallet (all assets, all venues).

        C'est LA requete "combien a cette personne sur sa carte ?"
        This is THE query "how much does this person have on their card?"

        Exemple / Example:
            soldes = WalletService.obtenir_tous_les_soldes(wallet=alice.wallet)
            → QuerySet[Token(monnaie_locale, 1500), Token(fidelite, 300)]
        """
        tous_les_tokens = Token.objects.filter(
            wallet=wallet,
        ).select_related('asset', 'asset__tenant_origin')

        return tous_les_tokens

    @staticmethod
    def obtenir_total_en_centimes(wallet):
        """
        Retourne la somme de tous les soldes d'un wallet, en centimes.
        Returns the sum of all balances for a wallet, in cents.

        Attention : additionne des monnaies differentes (EUR + temps + fidelite).
        Utile seulement pour un affichage global approximatif.
        Warning: adds different currencies together (EUR + time + loyalty).
        Only useful for a rough global display.

        Exemple / Example:
            total = WalletService.obtenir_total_en_centimes(wallet=alice.wallet)
            → 1800  (1500 monnaie locale + 300 fidelite)
        """
        resultat = Token.objects.filter(
            wallet=wallet,
        ).aggregate(
            total=Sum('value'),
        )

        # Si aucun Token n'existe, aggregate retourne {'total': None}.
        # If no Token exists, aggregate returns {'total': None}.
        total_en_centimes = resultat['total'] or 0

        return total_en_centimes

    @staticmethod
    def crediter(wallet, asset, montant_en_centimes):
        """
        Augmente le solde d'un wallet pour un asset donne.
        Increases a wallet's balance for a given asset.

        Cree le Token s'il n'existe pas encore (get_or_create).
        Creates the Token if it doesn't exist yet (get_or_create).

        DOIT etre appele dans un bloc transaction.atomic().
        MUST be called inside a transaction.atomic() block.

        Utilise select_for_update() pour verrouiller la ligne Token.
        Uses select_for_update() to lock the Token row.

        Args:
            wallet: Wallet (le wallet a crediter / the wallet to credit)
            asset: Asset (l'asset concerne / the concerned asset)
            montant_en_centimes: int (montant positif / positive amount)

        Returns:
            Token: le token mis a jour / the updated token

        Exemple / Example:
            with transaction.atomic():
                token = WalletService.crediter(
                    wallet=alice.wallet,
                    asset=monnaie_locale,
                    montant_en_centimes=500,  # +5,00 EUR
                )
        """
        # Creer le Token s'il n'existe pas encore.
        # Create the Token if it doesn't exist yet.
        token, token_just_created = Token.objects.get_or_create(
            wallet=wallet,
            asset=asset,
            defaults={'value': 0},
        )

        # Verrouiller la ligne pour eviter les modifications concurrentes.
        # Lock the row to prevent concurrent modifications.
        token_verrouille = Token.objects.select_for_update().get(pk=token.pk)

        token_verrouille.value = token_verrouille.value + montant_en_centimes
        token_verrouille.save(update_fields=['value'])

        return token_verrouille

    @staticmethod
    def fusionner_wallet_ephemere(carte, user, tenant, ip="0.0.0.0"):
        """
        Fusionne le wallet_ephemere d'une carte vers le wallet du user.
        Reproduit le mecanisme de LinkWalletCardQrCode.fusion()
        de l'ancien Fedow (V1), mais en acces DB direct (pas de HTTP).
        / Merges a card's wallet_ephemere into the user's wallet.
        Reproduces LinkWalletCardQrCode.fusion() from the old Fedow (V1),
        but with direct DB access (no HTTP).

        LOCALISATION : fedow_core/services.py

        DOIT etre appelee dans un bloc transaction.atomic() externe.
        Le caller (laboutik/views.py:_creer_adhesions_depuis_panier) fournit
        ce bloc atomic.
        / MUST be called inside an outer transaction.atomic() block.
        The caller (laboutik/views.py:_creer_adhesions_depuis_panier) provides
        that atomic block.

        FLUX :
        1. Si pas de wallet_ephemere → juste poser carte.user et retourner
        2. Creer user.wallet si inexistant (Wallet + FK sur TibilletUser)
        3. Pour chaque Token du wallet_ephemere avec value > 0 :
           → TransactionService.creer(action=FUSION, sender=eph, receiver=user)
           → Debit wallet_ephemere + credit user.wallet (via select_for_update)
        4. carte.user = user, carte.wallet_ephemere = None

        COEXISTENCE V1/V2 :
        Cette methode ne touche que fedow_core (SHARED_APPS) et CarteCashless.
        Les anciens tenants (V1, server_cashless renseigne) ne passent jamais
        par ce code — ils utilisent fedow_connect/fedow_api.py → serveur Fedow
        distant. Les deux systemes de tokens sont disjoints (BD locale vs BD distante).
        Le seul etat partage est CarteCashless.user, mais V1 ne l'utilise pas
        pour les operations cashless (elle passe par le serveur Fedow distant).
        / This method only touches fedow_core (SHARED_APPS) and CarteCashless.
        Old tenants (V1, server_cashless set) never call this code — they use
        fedow_connect/fedow_api.py → remote Fedow server. The two token systems
        are disjoint (local DB vs remote DB). The only shared state is
        CarteCashless.user, but V1 doesn't use it for cashless operations.

        :param carte: CarteCashless (la carte NFC scannee / the scanned NFC card)
        :param user: TibilletUser (le membre identifie / the identified member)
        :param tenant: Client (le tenant courant / the current tenant)
        :param ip: str (adresse IP de la requete / request IP address)
        """
        # --- Garde : pas de wallet_ephemere → rien a fusionner ---
        # On pose quand meme le lien carte → user si ce n'est pas deja fait.
        # / Guard: no wallet_ephemere → nothing to merge.
        # We still set the card → user link if not already done.
        carte_a_un_wallet_ephemere = carte.wallet_ephemere is not None
        if not carte_a_un_wallet_ephemere:
            carte_user_est_deja_correct = (carte.user == user)
            if not carte_user_est_deja_correct:
                carte.user = user
                carte.save(update_fields=['user'])
            return

        wallet_source = carte.wallet_ephemere

        # --- Creer user.wallet si inexistant ---
        # Certains users viennent d'etre crees par get_or_create_user()
        # et n'ont pas encore de wallet.
        # / Some users were just created by get_or_create_user()
        # and don't have a wallet yet.
        user_a_deja_un_wallet = user.wallet is not None
        if not user_a_deja_un_wallet:
            nouveau_wallet = Wallet.objects.create(
                origin=tenant,
                name=f"Wallet {user.email}",
            )
            user.wallet = nouveau_wallet
            user.save(update_fields=['wallet'])

        wallet_cible = user.wallet

        # --- Garde defensive : source == cible ---
        # Cas improbable mais possible si quelqu'un a manuellement
        # pointe wallet_ephemere vers le meme wallet que user.wallet.
        # / Unlikely but possible if someone manually pointed
        # wallet_ephemere to the same wallet as user.wallet.
        wallet_source_est_le_meme_que_cible = (wallet_source.pk == wallet_cible.pk)
        if wallet_source_est_le_meme_que_cible:
            carte.user = user
            carte.wallet_ephemere = None
            carte.save(update_fields=['user', 'wallet_ephemere'])
            return

        # --- Transferer chaque Token avec solde > 0 ---
        # Un wallet ephemere peut avoir plusieurs assets (TLF, TNF, TIM, FID...).
        # On transfere chaque asset separement, avec une Transaction FUSION
        # pour l'audit trail.
        # / An ephemeral wallet can have multiple assets (TLF, TNF, TIM, FID...).
        # We transfer each asset separately, with a FUSION Transaction
        # for the audit trail.
        tokens_avec_solde = Token.objects.filter(
            wallet=wallet_source,
            value__gt=0,
        )
        for token_a_transferer in tokens_avec_solde:
            TransactionService.creer(
                sender=wallet_source,
                receiver=wallet_cible,
                asset=token_a_transferer.asset,
                montant_en_centimes=token_a_transferer.value,
                action=Transaction.FUSION,
                tenant=tenant,
                card=carte,
                ip=ip,
                comment=f"Fusion ephemere vers {user.email}",
            )

        # --- Poser le lien carte → user et detacher le wallet ephemere ---
        # Le wallet_source reste en base pour audit (on ne le supprime pas).
        # Il est juste detache de la carte.
        # / wallet_source stays in DB for audit (we don't delete it).
        # It's just detached from the card.
        carte.user = user
        carte.wallet_ephemere = None
        carte.save(update_fields=['user', 'wallet_ephemere'])

        logger.info(
            f"Fusion wallet ephemere terminee pour carte {carte.tag_id} "
            f"vers user {user.email} (tenant={tenant.schema_name})"
        )

    @staticmethod
    def debiter(wallet, asset, montant_en_centimes):
        """
        Diminue le solde d'un wallet pour un asset donne.
        Decreases a wallet's balance for a given asset.

        DOIT etre appele dans un bloc transaction.atomic().
        MUST be called inside a transaction.atomic() block.

        Utilise select_for_update() pour verrouiller la ligne Token.
        Uses select_for_update() to lock the Token row.

        Leve SoldeInsuffisant si le solde est inferieur au montant demande.
        Raises SoldeInsuffisant if the balance is less than the requested amount.

        Args:
            wallet: Wallet (le wallet a debiter / the wallet to debit)
            asset: Asset (l'asset concerne / the concerned asset)
            montant_en_centimes: int (montant positif / positive amount)

        Returns:
            Token: le token mis a jour / the updated token

        Raises:
            SoldeInsuffisant: si le solde est insuffisant OU si aucun Token
                n'existe pour ce couple (wallet, asset) (solde = 0).
            SoldeInsuffisant: if balance is insufficient OR if no Token
                exists for this (wallet, asset) pair (balance = 0).

        Exemple / Example:
            with transaction.atomic():
                token = WalletService.debiter(
                    wallet=alice.wallet,
                    asset=monnaie_locale,
                    montant_en_centimes=350,  # -3,50 EUR
                )
        """
        # Verrouiller la ligne Token avant de lire le solde.
        # On ne fait PAS get_or_create ici : si le Token n'existe pas,
        # le solde est 0, donc on ne peut pas debiter.
        # Lock the Token row before reading the balance.
        # We do NOT get_or_create here: if the Token doesn't exist,
        # the balance is 0, so we can't debit.
        try:
            token_verrouille = Token.objects.select_for_update().get(
                wallet=wallet,
                asset=asset,
            )
        except Token.DoesNotExist:
            raise SoldeInsuffisant(
                solde_actuel_en_centimes=0,
                montant_demande_en_centimes=montant_en_centimes,
                asset_name=asset.name,
            )

        # Verifier que le solde est suffisant.
        # Check that the balance is sufficient.
        solde_insuffisant = token_verrouille.value < montant_en_centimes
        if solde_insuffisant:
            raise SoldeInsuffisant(
                solde_actuel_en_centimes=token_verrouille.value,
                montant_demande_en_centimes=montant_en_centimes,
                asset_name=asset.name,
            )

        token_verrouille.value = token_verrouille.value - montant_en_centimes
        token_verrouille.save(update_fields=['value'])

        return token_verrouille


# ---------------------------------------------------------------------------
# TransactionService : creation de transactions (mouvements financiers)
# TransactionService: transaction creation (financial movements)
# ---------------------------------------------------------------------------

class TransactionService:
    """
    Methodes statiques pour creer des transactions.
    Static methods to create transactions.

    Chaque creation de transaction :
    1. Debite le sender (si applicable)
    2. Credite le receiver (si applicable)
    3. Cree l'enregistrement Transaction
    Le tout dans un seul bloc transaction.atomic().

    Each transaction creation:
    1. Debits the sender (if applicable)
    2. Credits the receiver (if applicable)
    3. Creates the Transaction record
    All inside a single transaction.atomic() block.

    L'id (BigAutoField) est auto-attribue par Django/PostgreSQL.
    Le hash est null (Phase 2 du plan de migration — pas de calcul).
    The id (BigAutoField) is auto-assigned by Django/PostgreSQL.
    The hash is null (Phase 2 of the migration plan — no calculation).
    """

    @staticmethod
    def creer(
        sender,
        receiver,
        asset,
        montant_en_centimes,
        action,
        tenant,
        card=None,
        primary_card=None,
        comment="",
        metadata=None,
        ip="0.0.0.0",
        checkout_stripe_uuid=None,
    ):
        """
        Cree une transaction complete : debit sender + credit receiver + enregistrement.
        Creates a complete transaction: debit sender + credit receiver + record.

        C'est la methode centrale. Les wrappers (creer_vente, creer_recharge)
        l'appellent avec les bons parametres.
        This is the central method. Wrappers (creer_vente, creer_recharge)
        call it with the right parameters.

        Le tout est dans un seul bloc transaction.atomic() :
        si le debit echoue (SoldeInsuffisant), rien n'est ecrit.
        Everything is in a single transaction.atomic() block:
        if the debit fails (SoldeInsuffisant), nothing is written.

        Args:
            sender: Wallet (qui paye / who pays)
            receiver: Wallet ou None (qui recoit / who receives)
            asset: Asset (quelle monnaie / which currency)
            montant_en_centimes: int (montant positif / positive amount)
            action: str (Transaction.SALE, Transaction.REFILL, etc.)
            tenant: Client (le lieu concerne / the concerned venue)
            card: CarteCashless ou None (carte NFC utilisee / NFC card used)
            primary_card: CarteCashless ou None (carte maitresse / primary card)
            comment: str (commentaire libre / free comment)
            metadata: dict ou None (donnees supplementaires / additional data)
            ip: str (adresse IP de la requete / request IP address)
            checkout_stripe_uuid: UUID ou None (lien vers Paiement_stripe)

        Returns:
            Transaction: la transaction creee / the created transaction

        Raises:
            SoldeInsuffisant: si le sender n'a pas assez de solde.
                If the sender doesn't have enough balance.
        """
        if metadata is None:
            metadata = {}

        with transaction.atomic():

            # --- Debit du sender ---
            # Certaines actions ne debitent pas le sender :
            # - FIRST / CREATION : genesis, pas de debit
            # - REFILL : le lieu emet des tokens, il ne depense pas les siens
            # Some actions don't debit the sender:
            # - FIRST / CREATION: genesis, no debit
            # - REFILL: the venue issues tokens, it doesn't spend its own
            actions_sans_debit = [Transaction.FIRST, Transaction.CREATION, Transaction.REFILL]
            action_necessite_debit = action not in actions_sans_debit

            if action_necessite_debit:
                WalletService.debiter(
                    wallet=sender,
                    asset=asset,
                    montant_en_centimes=montant_en_centimes,
                )

            # --- Credit du receiver ---
            # Certaines actions ne creditent pas (VOID, REFUND sans receiver).
            # Some actions don't credit (VOID, REFUND without receiver).
            receiver_existe = receiver is not None
            if receiver_existe:
                WalletService.crediter(
                    wallet=receiver,
                    asset=asset,
                    montant_en_centimes=montant_en_centimes,
                )

            # --- Creation de l'enregistrement Transaction ---
            # L'id (BigAutoField) est auto-attribue par Django/PostgreSQL.
            # Le hash est null (Phase 2 — pas de calcul pour l'instant).
            # The id (BigAutoField) is auto-assigned by Django/PostgreSQL.
            # The hash is null (Phase 2 — no calculation for now).
            nouvelle_transaction = Transaction.objects.create(
                sender=sender,
                receiver=receiver,
                asset=asset,
                amount=montant_en_centimes,
                action=action,
                tenant=tenant,
                card=card,
                primary_card=primary_card,
                datetime=timezone.now(),
                comment=comment,
                metadata=metadata,
                ip=ip,
                checkout_stripe=checkout_stripe_uuid,
                # id : auto (BigAutoField)
                # hash : null (Phase 2)
            )

        logger.info(
            f"Transaction #{nouvelle_transaction.id} "
            f"{nouvelle_transaction.get_action_display()} "
            f"{montant_en_centimes} centimes "
            f"(tenant={tenant.schema_name})"
        )

        return nouvelle_transaction

    @staticmethod
    def creer_vente(
        sender_wallet,
        receiver_wallet,
        asset,
        montant_en_centimes,
        tenant,
        card=None,
        primary_card=None,
        comment="",
        metadata=None,
        ip="0.0.0.0",
    ):
        """
        Cree une transaction de type VENTE (paiement cashless).
        Creates a SALE transaction (cashless payment).

        Le client (sender) paye le lieu (receiver).
        The customer (sender) pays the venue (receiver).

        Wrapper FALC pour creer() avec action=SALE.
        FALC wrapper for creer() with action=SALE.

        Exemple / Example:
            transaction_vente = TransactionService.creer_vente(
                sender_wallet=alice.wallet,       # la cliente / the customer
                receiver_wallet=bar.wallet,       # le lieu / the venue
                asset=monnaie_locale,
                montant_en_centimes=350,          # 3,50 EUR
                tenant=festival_tenant,
                card=alice_carte_nfc,
                primary_card=carte_caisse,
            )
        """
        transaction_vente = TransactionService.creer(
            sender=sender_wallet,
            receiver=receiver_wallet,
            asset=asset,
            montant_en_centimes=montant_en_centimes,
            action=Transaction.SALE,
            tenant=tenant,
            card=card,
            primary_card=primary_card,
            comment=comment,
            metadata=metadata,
            ip=ip,
        )

        return transaction_vente

    @staticmethod
    def creer_recharge(
        sender_wallet,
        receiver_wallet,
        asset,
        montant_en_centimes,
        tenant,
        comment="",
        metadata=None,
        ip="0.0.0.0",
        checkout_stripe_uuid=None,
    ):
        """
        Cree une transaction de type RECHARGE (ajout de tokens sur un wallet).
        Creates a REFILL transaction (adding tokens to a wallet).

        Le lieu ou le systeme (sender) recharge le wallet du client (receiver).
        The venue or system (sender) refills the customer's wallet (receiver).

        Wrapper FALC pour creer() avec action=REFILL.
        FALC wrapper for creer() with action=REFILL.

        Exemple / Example:
            transaction_recharge = TransactionService.creer_recharge(
                sender_wallet=lieu.wallet,        # le lieu / the venue
                receiver_wallet=alice.wallet,     # la cliente / the customer
                asset=monnaie_locale,
                montant_en_centimes=2000,         # 20,00 EUR
                tenant=festival_tenant,
            )
        """
        transaction_recharge = TransactionService.creer(
            sender=sender_wallet,
            receiver=receiver_wallet,
            asset=asset,
            montant_en_centimes=montant_en_centimes,
            action=Transaction.REFILL,
            tenant=tenant,
            comment=comment,
            metadata=metadata,
            ip=ip,
            checkout_stripe_uuid=checkout_stripe_uuid,
        )

        return transaction_recharge
