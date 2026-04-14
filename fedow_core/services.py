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
    def get_or_create_wallet_tenant(tenant):
        """
        Recupere ou cree le wallet "lieu" du tenant — wallet receveur des refunds
        et BANK_TRANSFER, et sender des operations sortantes du lieu.
        Returns or creates the tenant's "venue" wallet.

        Convention : un wallet par tenant, identifie par origin=tenant
        ET name=f"Lieu {tenant.schema_name}". Idempotent.

        NB : a remplacer par tenant.wallet quand la convention sera formalisee
        sur le modele Customers.Client.
        """
        wallet, _created = Wallet.objects.get_or_create(
            origin=tenant,
            name=f"Lieu {tenant.schema_name}",
        )
        return wallet

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

    @staticmethod
    def rembourser_en_especes(
        carte,
        tenant,
        receiver_wallet,
        ip: str = "0.0.0.0",
        vider_carte: bool = False,
        primary_card=None,
    ) -> dict:
        """
        Rembourse en especes les tokens eligibles d'une carte.
        Refunds in cash the eligible tokens of a card.

        Tokens eligibles / Eligible tokens :
        - TLF avec asset.tenant_origin == tenant
        - FED (toutes valeurs, sans filtre origine — un seul FED dans le systeme)

        Cree :
        - 1 Transaction(action=REFUND, sender=wallet_carte, receiver=receiver_wallet) par asset
        - 1 LigneArticle FED (encaissement positif STRIPE_FED) si solde FED > 0
        - 1 LigneArticle CASH negative (sortie cash totale TLF + FED)
        - Si vider_carte=True : carte.user=None, carte.wallet_ephemere=None,
          CartePrimaire.objects.filter(carte=carte).delete()

        Tout dans un seul transaction.atomic().
        All in a single transaction.atomic() block.

        :param carte: CarteCashless (la carte a vider)
        :param tenant: Client (le tenant courant)
        :param receiver_wallet: Wallet (le wallet receveur des REFUND, generalement le wallet du lieu)
        :param ip: str (adresse IP de la requete)
        :param vider_carte: bool (si True, reset user + wallet_ephemere + CartePrimaire)

        :return: dict {
            "transactions": list[Transaction],
            "lignes_articles": list[LigneArticle],
            "total_centimes": int,
            "total_tlf_centimes": int,
            "total_fed_centimes": int,
        }
        :raises NoEligibleTokens: si aucun token eligible n'a value > 0
        """
        # Imports locaux pour eviter le cycle (BaseBillet est en TENANT_APPS)
        # / Local imports to avoid cycle (BaseBillet is in TENANT_APPS)
        from django.db.models import Q
        from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin
        from BaseBillet.services_refund import (
            get_or_create_product_remboursement,
            get_or_create_pricesold_refund,
        )
        from fedow_core.exceptions import NoEligibleTokens

        # 1. Charger le wallet de la carte
        # / 1. Load the card's wallet
        wallet_carte = None
        if carte.user is not None and carte.user.wallet is not None:
            wallet_carte = carte.user.wallet
        elif carte.wallet_ephemere is not None:
            wallet_carte = carte.wallet_ephemere

        if wallet_carte is None:
            raise NoEligibleTokens(carte_tag_id=carte.tag_id)

        # 2. Filtrer les tokens eligibles : TLF du tenant + FED
        # / 2. Filter eligible tokens: tenant's TLF + FED
        tokens_eligibles = list(
            Token.objects.filter(
                wallet=wallet_carte,
                value__gt=0,
            ).filter(
                Q(asset__category=Asset.TLF, asset__tenant_origin=tenant)
                | Q(asset__category=Asset.FED)
            ).select_related('asset', 'asset__tenant_origin')
        )

        if not tokens_eligibles:
            raise NoEligibleTokens(carte_tag_id=carte.tag_id)

        # 3. Atomic : transactions REFUND + LigneArticle + reset eventuel
        # / 3. Atomic: REFUND transactions + LigneArticle + optional reset
        transactions_creees = []
        total_tlf = 0
        total_fed = 0

        with transaction.atomic():
            for token in tokens_eligibles:
                tx = TransactionService.creer(
                    sender=wallet_carte,
                    receiver=receiver_wallet,
                    asset=token.asset,
                    montant_en_centimes=token.value,
                    action=Transaction.REFUND,
                    tenant=tenant,
                    card=carte,
                    primary_card=primary_card,
                    ip=ip,
                    comment="Remboursement especes admin",
                    metadata={
                        "vider_carte": vider_carte,
                    },
                )
                transactions_creees.append(tx)
                if token.asset.category == Asset.TLF:
                    total_tlf += token.value
                elif token.asset.category == Asset.FED:
                    total_fed += token.value

            # 4. Creer les LigneArticle (Product/PriceSold systeme partages)
            # / 4. Create LigneArticle (shared system Product/PriceSold)
            product_refund = get_or_create_product_remboursement()
            pricesold_refund = get_or_create_pricesold_refund(product_refund)

            lignes_creees = []

            if total_fed > 0:
                # Recupere l'asset FED unique (convention : 1 seul FED dans le systeme)
                # On utilise .filter().first() pour un message d'erreur clair si absent
                # / Get the unique FED asset (convention: 1 FED in the system).
                # Using .filter().first() for a clear error message if missing.
                fed_asset = Asset.objects.filter(category=Asset.FED).first()
                if fed_asset is None:
                    raise RuntimeError(
                        "Aucun asset FED n'existe dans le systeme : "
                        "impossible de rembourser le solde federe."
                    )
                ligne_fed = LigneArticle.objects.create(
                    pricesold=pricesold_refund,
                    qty=1,
                    amount=total_fed,
                    payment_method=PaymentMethod.STRIPE_FED,
                    status=LigneArticle.VALID,
                    sale_origin=SaleOrigin.ADMIN,
                    carte=carte,
                    wallet=wallet_carte,
                    asset=fed_asset.uuid,
                )
                lignes_creees.append(ligne_fed)

            ligne_cash = LigneArticle.objects.create(
                pricesold=pricesold_refund,
                qty=1,
                amount=-(total_tlf + total_fed),
                payment_method=PaymentMethod.CASH,
                status=LigneArticle.VALID,
                sale_origin=SaleOrigin.ADMIN,
                carte=carte,
                wallet=wallet_carte,
            )
            lignes_creees.append(ligne_cash)

            # 5. Reset optionnel de la carte (action VV)
            # / 5. Optional card reset (VV action)
            if vider_carte:
                # Import local : laboutik n'est pas toujours dispo selon le contexte
                # / Local import: laboutik may not be available depending on context
                try:
                    from laboutik.models import CartePrimaire
                    CartePrimaire.objects.filter(carte=carte).delete()
                except ImportError:
                    pass
                carte.user = None
                carte.wallet_ephemere = None
                carte.save(update_fields=["user", "wallet_ephemere"])

        return {
            "transactions": transactions_creees,
            "lignes_articles": lignes_creees,
            "total_centimes": total_tlf + total_fed,
            "total_tlf_centimes": total_tlf,
            "total_fed_centimes": total_fed,
        }


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
            actions_sans_debit = [
                Transaction.FIRST,
                Transaction.CREATION,
                Transaction.REFILL,
                Transaction.BANK_TRANSFER,  # virement bancaire externe : pas de mutation Token
            ]
            action_necessite_debit = action not in actions_sans_debit

            if action_necessite_debit:
                WalletService.debiter(
                    wallet=sender,
                    asset=asset,
                    montant_en_centimes=montant_en_centimes,
                )

            # --- Credit du receiver ---
            # Certaines actions ne creditent pas le receiver :
            # - receiver=None (VOID, REFUND sans receiver explicite)
            # - BANK_TRANSFER : virement bancaire externe, l'argent n'arrive pas
            #   sur le wallet receveur (il arrive sur le compte bancaire externe).
            # Some actions don't credit:
            # - receiver=None (VOID, REFUND without explicit receiver)
            # - BANK_TRANSFER: external bank movement, money does NOT land on
            #   the receiver wallet (it lands on the external bank account).
            actions_sans_credit = [Transaction.BANK_TRANSFER]
            receiver_existe = receiver is not None
            action_necessite_credit = action not in actions_sans_credit
            if receiver_existe and action_necessite_credit:
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


# ---------------------------------------------------------------------------
# BankTransferService : suivi de la dette pot central → tenant (Phase 2)
# BankTransferService: tracking central pot debt to tenants (Phase 2)
# ---------------------------------------------------------------------------

class BankTransferService:
    """
    Service de gestion des virements bancaires pot central -> tenant.
    Tracks the central pot's debt to tenants for refunded FED tokens.

    La dette = somme(REFUND FED vers tenant) - somme(BANK_TRANSFER FED vers tenant).
    Aucune mutation Token (les BANK_TRANSFER sont des evenements bancaires externes,
    enregistres pour audit + reporting comptable).

    The debt = sum(REFUND FED to tenant) - sum(BANK_TRANSFER FED to tenant).
    No Token mutation (BANK_TRANSFER are external bank events, recorded for
    audit + accounting reporting only).
    """

    @staticmethod
    def calculer_dette(tenant, asset) -> int:
        """
        Retourne la dette actuelle en centimes du pot central envers ce tenant pour cet asset.
        Returns the central pot's current debt to this tenant for this asset, in cents.

        Calcul : sum(REFUND, asset, tenant=tenant) - sum(BANK_TRANSFER, asset, tenant=tenant).
        Garantit >= 0 (validation hard a la saisie empeche tout sur-versement).
        """
        from django.db.models import Sum

        agg_refund = Transaction.objects.filter(
            action=Transaction.REFUND,
            asset=asset,
            tenant=tenant,
        ).aggregate(total=Sum('amount'))
        total_refund = agg_refund.get('total') or 0

        agg_virement = Transaction.objects.filter(
            action=Transaction.BANK_TRANSFER,
            asset=asset,
            tenant=tenant,
        ).aggregate(total=Sum('amount'))
        total_virement = agg_virement.get('total') or 0

        dette = total_refund - total_virement
        return max(0, dette)  # filet de securite : la dette ne peut etre negative

    @staticmethod
    def obtenir_dettes_par_tenant_et_asset() -> list:
        """
        Pour le dashboard superuser : toutes les dettes par couple (tenant, asset).
        For the superuser dashboard: all debts per (tenant, asset) pair.

        Inclut les couples avec dette > 0 OU au moins 1 REFUND historique.
        Trie par dette decroissante.

        Retourne : list[dict] avec les cles :
          - tenant: Client
          - asset: Asset
          - dette_centimes: int
          - total_refund_centimes: int
          - total_virements_centimes: int
          - dernier_virement: Transaction | None
        """
        from django.db.models import Sum
        from Customers.models import Client

        couples = Transaction.objects.filter(
            action__in=[Transaction.REFUND, Transaction.BANK_TRANSFER],
            asset__category=Asset.FED,
        ).values_list('tenant_id', 'asset_id').distinct()

        resultat = []
        for tenant_id, asset_id in couples:
            tenant = Client.objects.filter(pk=tenant_id).first()
            asset = Asset.objects.filter(pk=asset_id).first()
            if tenant is None or asset is None:
                continue

            agg_refund = Transaction.objects.filter(
                action=Transaction.REFUND, asset=asset, tenant=tenant,
            ).aggregate(total=Sum('amount'))
            total_refund = agg_refund.get('total') or 0

            agg_virement = Transaction.objects.filter(
                action=Transaction.BANK_TRANSFER, asset=asset, tenant=tenant,
            ).aggregate(total=Sum('amount'))
            total_virement = agg_virement.get('total') or 0

            dette = max(0, total_refund - total_virement)

            dernier_virement = Transaction.objects.filter(
                action=Transaction.BANK_TRANSFER, asset=asset, tenant=tenant,
            ).order_by('-datetime').first()

            resultat.append({
                "tenant": tenant,
                "asset": asset,
                "dette_centimes": dette,
                "total_refund_centimes": total_refund,
                "total_virements_centimes": total_virement,
                "dernier_virement": dernier_virement,
            })

        # Tri : dette decroissante / Sort: debt descending
        resultat.sort(key=lambda d: d["dette_centimes"], reverse=True)
        return resultat

    @staticmethod
    def obtenir_dette_pour_tenant(tenant) -> list:
        """
        Pour le widget tenant : meme structure que obtenir_dettes_par_tenant_et_asset
        mais filtree au tenant courant.
        """
        toutes = BankTransferService.obtenir_dettes_par_tenant_et_asset()
        return [d for d in toutes if d["tenant"].pk == tenant.pk]

    @staticmethod
    def enregistrer_virement(
        tenant,
        asset,
        montant_en_centimes: int,
        date_virement,
        reference_bancaire: str,
        comment: str = "",
        ip: str = "0.0.0.0",
        admin_email: str = "",
    ):
        """
        Enregistre un virement bancaire recu par le tenant.
        Records a bank transfer received by the tenant.

        Cree atomiquement :
        - 1 Transaction(action=BANK_TRANSFER, sender=asset.wallet_origin,
                        receiver=tenant.wallet_lieu, asset=asset, amount=...).
        - 1 LigneArticle d'encaissement (payment_method=TRANSFER, +amount,
                                          sale_origin=ADMIN, asset=asset.uuid).

        Validation : montant <= calculer_dette(tenant, asset) (re-check dans l'atomic).

        :return: Transaction creee
        :raises MontantSuperieurDette: si sur-versement
        """
        # Imports locaux pour eviter le cycle SHARED_APPS / TENANT_APPS
        # / Local imports to avoid SHARED_APPS / TENANT_APPS cycle
        from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin
        from BaseBillet.services_refund import (
            get_or_create_product_virement_recu,
            get_or_create_pricesold_refund,
        )
        from fedow_core.exceptions import MontantSuperieurDette

        with transaction.atomic():
            # Re-check de la dette dans l'atomic (race guard)
            dette = BankTransferService.calculer_dette(tenant=tenant, asset=asset)
            if montant_en_centimes > dette:
                raise MontantSuperieurDette(
                    montant_demande_en_centimes=montant_en_centimes,
                    dette_actuelle_en_centimes=dette,
                )

            receiver_wallet = WalletService.get_or_create_wallet_tenant(tenant)

            # 1. Transaction BANK_TRANSFER (no token mutation grace a actions_sans_credit)
            tx = TransactionService.creer(
                sender=asset.wallet_origin,
                receiver=receiver_wallet,
                asset=asset,
                montant_en_centimes=montant_en_centimes,
                action=Transaction.BANK_TRANSFER,
                tenant=tenant,
                ip=ip,
                comment=comment,
                metadata={
                    "reference_bancaire": reference_bancaire,
                    "date_virement": date_virement.isoformat(),
                    "saisi_par": admin_email,
                },
            )

            # 2. LigneArticle d'encaissement (rapport comptable)
            product_vr = get_or_create_product_virement_recu()
            pricesold_vr = get_or_create_pricesold_refund(product_vr)
            LigneArticle.objects.create(
                pricesold=pricesold_vr,
                qty=1,
                amount=montant_en_centimes,
                payment_method=PaymentMethod.TRANSFER,
                status=LigneArticle.VALID,
                sale_origin=SaleOrigin.ADMIN,
                asset=asset.uuid,
                wallet=receiver_wallet,
                carte=None,
                metadata={
                    "reference_bancaire": reference_bancaire,
                    "date_virement": date_virement.isoformat(),
                    "transaction_uuid": str(tx.uuid),
                },
            )

        logger.info(
            f"Virement bancaire enregistre : {montant_en_centimes} centimes "
            f"vers tenant {tenant.schema_name} (asset {asset.name})"
        )
        return tx
