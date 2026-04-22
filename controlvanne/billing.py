"""
Facturation des tirages de bière via fedow_core.
/ Billing for beer pours via fedow_core.

LOCALISATION : controlvanne/billing.py

Ce module encapsule la logique de facturation spécifique à la tireuse.
Le ViewSet appelle ces fonctions — séparation ViewSet / logique métier.
/ This module encapsulates tap-specific billing logic.
The ViewSet calls these functions — separation of ViewSet / business logic.

Cascade fiduciaire : même ordre que LaBoutik — TNF → TLF → FED.
Les assets fédérés (FED) sont inclus si accessibles via une Fédération.
/ Fiduciary cascade: same order as LaBoutik — TNF → TLF → FED.
Federated assets (FED) are included if accessible via a Federation.

Dépendances :
- fedow_core.services : AssetService, WalletService, TransactionService
- fedow_core.models : Asset, Token, Transaction
- BaseBillet.models : LigneArticle, ProductSold, PriceSold, PaymentMethod, SaleOrigin
- inventaire.services : StockService
- QrcodeCashless.models : CarteCashless
- AuthBillet.models : Wallet
"""

import logging
import uuid as uuid_module
from decimal import Decimal

from django.db import connection, transaction

logger = logging.getLogger(__name__)

# Ordre de débit fiduciaire : cadeau → local → fédéré.
# Identique à ORDRE_CASCADE_FIDUCIAIRE dans laboutik/views.py.
# / Fiduciary debit order: gift → local → federated.
# Identical to ORDRE_CASCADE_FIDUCIAIRE in laboutik/views.py.
ORDRE_CASCADE_FIDUCIAIRE = None  # résolu dynamiquement après import Asset / resolved dynamically after Asset import


def _ordre_cascade():
    """Retourne la liste des catégories d'assets dans l'ordre de cascade.
    / Returns the list of asset categories in cascade order."""
    from fedow_core.models import Asset
    return [Asset.TNF, Asset.TLF, Asset.FED]


def obtenir_contexte_cashless(carte):
    """
    Résout le wallet client et la cascade d'assets fiduciaires pour un paiement tireuse.
    / Resolves the client wallet and fiduciary asset cascade for a tap payment.

    Même logique que LaBoutik : cascade TNF → TLF → FED via AssetService.
    / Same logic as LaBoutik: TNF → TLF → FED cascade via AssetService.

    :param carte: CarteCashless
    :return: dict avec wallet_client, cascade_assets (liste ordonnée). None si aucun asset.
    """
    from AuthBillet.models import Wallet
    from fedow_core.models import Asset
    from fedow_core.services import AssetService, WalletService

    # --- Résoudre le wallet du client ---
    # / Resolve client wallet
    # Priorité : user.wallet > wallet_ephemere > créer éphémère
    # / Priority: user.wallet > wallet_ephemere > create ephemeral
    wallet_client = None

    if carte.user and hasattr(carte.user, "wallet") and carte.user.wallet:
        wallet_client = carte.user.wallet
    elif carte.wallet_ephemere:
        wallet_client = carte.wallet_ephemere
    else:
        # Créer un wallet éphémère pour cette carte anonyme
        # / Create an ephemeral wallet for this anonymous card
        wallet_client = Wallet.objects.create(
            origin=connection.tenant,
            name=f"Éphémère - {carte.tag_id}",
        )
        carte.wallet_ephemere = wallet_client
        carte.save(update_fields=["wallet_ephemere"])

    # --- Construire la cascade d'assets accessibles ---
    # / Build the cascade of accessible assets
    # Même logique que LaBoutik Phase 1 : tous les assets du tenant + fédérés.
    # / Same logic as LaBoutik Phase 1: all tenant assets + federated.
    assets_accessibles = AssetService.obtenir_assets_accessibles(connection.tenant)

    cascade_assets = []
    for categorie in _ordre_cascade():
        asset = assets_accessibles.filter(category=categorie).first()
        if asset is not None:
            cascade_assets.append(asset)

    if not cascade_assets:
        logger.warning(
            f"Aucun asset fiduciaire (TNF/TLF/FED) pour le tenant {connection.tenant.name}"
        )
        return None

    return {
        "wallet_client": wallet_client,
        "cascade_assets": cascade_assets,
    }


def calculer_solde_total_cascade(wallet_client, cascade_assets):
    """
    Somme les soldes de tous les assets de la cascade pour ce wallet.
    / Sum balances of all cascade assets for this wallet.

    :param wallet_client: Wallet
    :param cascade_assets: liste ordonnée d'Asset (TNF, TLF, FED…)
    :return: int — solde total en centimes
    """
    from fedow_core.services import WalletService

    total = 0
    for asset in cascade_assets:
        total += WalletService.obtenir_solde(wallet_client, asset)
    return total


def calculer_volume_autorise_ml(
    solde_centimes, prix_litre_decimal, reservoir_disponible_ml
):
    """
    Calcule le volume maximum autorisé en ml depuis le solde wallet.
    / Computes the maximum allowed volume in ml from wallet balance.

    Formule : (solde_centimes / prix_centimes_par_litre) * 1000 ml
    / Formula: (balance_cents / price_cents_per_liter) * 1000 ml

    :param solde_centimes: int — solde total (tous assets cascade) en centimes
    :param prix_litre_decimal: Decimal — prix au litre en EUR (ex: Decimal("3.50"))
    :param reservoir_disponible_ml: float — volume restant dans la tireuse en ml
    :return: Decimal — volume autorisé en ml (arrondi à 2 décimales)
    """
    if prix_litre_decimal <= 0:
        return Decimal("0.00")

    # Prix au litre en centimes / Price per liter in cents
    prix_centimes_par_litre = int(round(prix_litre_decimal * 100))
    if prix_centimes_par_litre <= 0:
        return Decimal("0.00")

    # Volume max selon le solde / Max volume based on balance
    volume_max_solde_ml = (
        Decimal(str(solde_centimes)) / Decimal(str(prix_centimes_par_litre)) * 1000
    )

    # Limiter au réservoir disponible / Cap at available reservoir
    volume_max_ml = min(volume_max_solde_ml, Decimal(str(reservoir_disponible_ml)))

    return max(Decimal("0.00"), volume_max_ml.quantize(Decimal("0.01")))


def facturer_tirage(
    session, tireuse, carte, volume_ml, contexte_cashless, ip="0.0.0.0"
):
    """
    Facture un tirage de bière en cascade TNF → TLF → FED.
    / Bills a beer pour using TNF → TLF → FED cascade.

    Appelé au pour_end quand le volume final est connu.
    / Called at pour_end when the final volume is known.

    Cascade : débit TNF en premier (cadeau/gift), puis TLF (local), puis FED (fédéré).
    Une Transaction fedow_core est créée par asset débité.
    Une seule LigneArticle est créée pour le montant total.
    / Cascade: debit TNF first (gift), then TLF (local), then FED (federated).
    One fedow_core Transaction is created per debited asset.
    A single LigneArticle is created for the total amount.

    :param session: RfidSession — la session de service
    :param tireuse: TireuseBec — la tireuse
    :param carte: CarteCashless — la carte NFC du client
    :param volume_ml: Decimal — volume servi en ml
    :param contexte_cashless: dict retourné par obtenir_contexte_cashless()
    :param ip: str — IP du Raspberry Pi
    :return: dict avec transactions, ligne_article, montant_centimes. None si volume=0.
    """
    from fedow_core.services import TransactionService, WalletService
    from fedow_core.exceptions import SoldeInsuffisant
    from BaseBillet.models import (
        LigneArticle,
        ProductSold,
        PriceSold,
        PaymentMethod,
        SaleOrigin,
    )

    if volume_ml <= 0:
        return None

    prix_litre = tireuse.prix_litre  # Decimal, EUR
    if prix_litre <= 0:
        logger.warning(
            f"Tireuse {tireuse.nom_tireuse} : prix_litre=0, pas de facturation"
        )
        return None

    # Calculer le montant total en centimes / Calculate total amount in cents
    # montant = volume_ml * prix_litre / 1000 * 100
    # Ex: 250ml * 3.50 EUR/L = 0.250L * 3.50 = 0.875 EUR = 88 centimes
    montant_eur = volume_ml * prix_litre / Decimal("1000")
    montant_centimes = int(round(montant_eur * 100))

    if montant_centimes <= 0:
        return None

    wallet_client = contexte_cashless["wallet_client"]
    cascade_assets = contexte_cashless["cascade_assets"]
    tenant_courant = connection.tenant

    # --- Wallet receveur : wallet du lieu (pas asset.wallet_origin qui peut être erroné) ---
    # Même convention que LaBoutik (WalletService.get_or_create_wallet_tenant).
    # asset.wallet_origin représente le wallet de genèse de l'asset, qui peut
    # accidentellement pointer sur un wallet utilisateur — ce qui ferait s'annuler
    # débit et crédit (solde non décrémenté).
    # / Receiver wallet: venue wallet (not asset.wallet_origin which may be wrong).
    # Same convention as LaBoutik (WalletService.get_or_create_wallet_tenant).
    # asset.wallet_origin is the asset genesis wallet, which may accidentally
    # point to a user wallet — causing debit and credit to cancel out (balance unchanged).
    wallet_lieu = WalletService.get_or_create_wallet_tenant(tenant_courant)

    # --- Bloc atomique : transactions cascade + LigneArticle + stock ---
    # / Atomic block: cascade transactions + LigneArticle + stock
    with transaction.atomic():

        # 1. Débiter en cascade TNF → TLF → FED
        # / Debit in cascade TNF → TLF → FED
        restant_centimes = montant_centimes
        transactions_creees = []
        asset_principal = None  # asset le plus utilisé (pour la LigneArticle)

        for asset in cascade_assets:
            if restant_centimes <= 0:
                break

            solde_asset = WalletService.obtenir_solde(wallet_client, asset)
            if solde_asset <= 0:
                continue

            montant_asset = min(solde_asset, restant_centimes)

            tx = TransactionService.creer_vente(
                sender_wallet=wallet_client,
                receiver_wallet=wallet_lieu,
                asset=asset,
                montant_en_centimes=montant_asset,
                tenant=tenant_courant,
                card=carte,
                ip=ip,
                comment=(
                    f"Tirage {tireuse.nom_tireuse}: {float(volume_ml):.0f}ml"
                    f" [{asset.category}]"
                ),
            )
            transactions_creees.append(tx)
            restant_centimes -= montant_asset

            if asset_principal is None:
                asset_principal = asset

        if restant_centimes > 0:
            # Solde insuffisant pour couvrir le montant total — ne devrait pas
            # arriver si authorize() a correctement calculé allowed_ml.
            # / Insufficient balance to cover total — shouldn't happen if
            # authorize() correctly computed allowed_ml.
            raise SoldeInsuffisant(
                f"Solde insuffisant au pour_end: manque {restant_centimes} centimes"
            )

        # 2. Snapshots ProductSold / PriceSold
        # / ProductSold / PriceSold snapshots
        produit = tireuse.fut_actif
        prix_obj = produit.prices.filter(poids_mesure=True).first()

        product_sold, _ = ProductSold.objects.get_or_create(
            product=produit,
            event=None,
            defaults={"categorie_article": produit.categorie_article},
        )

        price_sold, _ = PriceSold.objects.get_or_create(
            productsold=product_sold,
            price=prix_obj,
            defaults={"prix": prix_obj.prix},
        )

        # 3. Créer la LigneArticle (montant total, asset principal)
        # / Create LigneArticle (total amount, primary asset)
        # Volume en centilitres pour weight_quantity (unité stock = cl)
        # / Volume in centiliters for weight_quantity (stock unit = cl)
        volume_cl = int(round(float(volume_ml) / 10))

        uuid_transaction = uuid_module.uuid4()

        ligne = LigneArticle.objects.create(
            pricesold=price_sold,
            qty=1,
            amount=montant_centimes,
            sale_origin=SaleOrigin.TIREUSE,
            payment_method=PaymentMethod.LOCAL_EURO,
            status=LigneArticle.VALID,
            asset=asset_principal.uuid,
            carte=carte,
            wallet=wallet_client,
            point_de_vente=tireuse.point_de_vente,
            weight_quantity=volume_cl,
            uuid_transaction=uuid_transaction,
        )

        # 4. Lier la session à la ligne / Link session to line
        session.ligne_article = ligne
        session.save(update_fields=["ligne_article"])

        # 5. Décrémenter le stock inventaire si le produit en a un
        # / Decrement inventory stock if the product has one
        try:
            stock_du_produit = produit.stock_inventaire
            from inventaire.services import StockService

            StockService.decrementer_pour_vente(
                stock=stock_du_produit,
                contenance=volume_cl,
                qty=1,
                ligne_article=ligne,
            )
        except Exception:
            # Pas de stock géré — comportement normal
            # / No stock managed — normal behavior
            pass

    assets_debites_str = ", ".join(
        f"{tx.asset.category}" for tx in transactions_creees
    ) if transactions_creees else "aucun"

    logger.info(
        f"Facturation cascade: tireuse={tireuse.nom_tireuse} volume={float(volume_ml):.0f}ml "
        f"montant={montant_centimes}cts assets=[{assets_debites_str}] ligne={ligne.uuid}"
    )

    # ── Sync optionnelle vers fedow_django ──────────────────────────────────
    # Les transactions locales (fedow_core) et fedow_django sont deux DBs disjointes.
    # On pousse ici les débits FED/TLF vers fedow_django pour que "Ma Tirelire"
    # reflète les consommations tireuse.
    # Les tokens TNF (cadeaux locaux) ne sont pas connus de fedow_django : skip.
    # Nécessite une carte liée à un user — les cartes anonymes ne peuvent pas signer.
    # Tous les échecs fedow_django sont loggés mais n'interrompent PAS la facturation.
    #
    # / Optional sync to fedow_django.
    # Local transactions (fedow_core) and fedow_django are two disjoint DBs.
    # We push FED/TLF debits here so that "Ma Tirelire" reflects tap debits.
    # TNF tokens (local gifts) are unknown to fedow_django: skip.
    # Requires a user-linked card — anonymous cards cannot sign the request.
    # All fedow_django failures are logged but do NOT interrupt billing.
    try:
        from fedow_connect.models import FedowConfig
        from fedow_core.models import Asset as AssetLocal

        fedow_config = FedowConfig.get_solo()
        carte_a_un_user = carte.user is not None
        user_a_un_wallet = carte_a_un_user and bool(carte.user.wallet)
        fedow_est_configure = fedow_config.can_fedow()

        if fedow_est_configure and carte_a_un_user and user_a_un_wallet:
            from fedow_connect.fedow_api import FedowAPI

            fedow_api = FedowAPI()

            for tx in transactions_creees:
                # Seul l'asset FED (Stripe fédéré) est présent dans fedow_django.
                # TNF (cadeaux locaux) et TLF (monnaie locale) sont ignorés :
                # fedow_django ne les connaît pas pour ce wallet.
                # / Only FED (Stripe federated) asset exists in fedow_django.
                # TNF (local gifts) and TLF (local currency) are skipped:
                # fedow_django does not know them for this wallet.
                if tx.asset.category != AssetLocal.FED:
                    continue

                # fedow_django n'accepte que asset_type="EURO" sur /qrcodescanpay/
                # (valeur unique pour tous les assets fiduciaires dans l'ancienne API).
                # / fedow_django only accepts asset_type="EURO" on /qrcodescanpay/
                # (single value for all fiduciary assets in the legacy API).
                fedow_api.transaction.to_place_from_qrcode(
                    user=carte.user,
                    amount=tx.amount,
                    asset_type="EURO",
                    comment=(
                        f"Tirage {tireuse.nom_tireuse}: {float(volume_ml):.0f}ml"
                        f" [FED]"
                    ),
                )
                logger.info(
                    f"Sync fedow_django: {tx.amount}cts [FED→EURO]"
                    f" wallet={carte.user.wallet.uuid}"
                )
        elif not fedow_est_configure:
            logger.debug("Sync fedow_django ignorée : FedowConfig non configuré")
        elif not carte_a_un_user:
            logger.debug(
                f"Sync fedow_django ignorée : carte {carte.tag_id} anonyme (user=None)"
            )
        elif not user_a_un_wallet:
            logger.debug(
                f"Sync fedow_django ignorée : user {carte.user.email} sans wallet"
            )

    except Exception as erreur_fedow:
        # Sync fedow_django non-bloquante : l'échec ne doit jamais annuler la vente.
        # / Non-blocking fedow_django sync: failure must never cancel the sale.
        logger.warning(
            f"Sync fedow_django non-bloquante échouée"
            f" (tireuse={tireuse.nom_tireuse}): {erreur_fedow}"
        )

    return {
        "transactions": transactions_creees,
        # Compatibilité avec le code existant qui lit ["transaction"]
        # / Backward compatibility with existing code reading ["transaction"]
        "transaction": transactions_creees[0] if transactions_creees else None,
        "ligne_article": ligne,
        "montant_centimes": montant_centimes,
    }
