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
- laboutik.views : ORDRE_CASCADE_FIDUCIAIRE,                              
  MAPPING_ASSET_CATEGORY_PAYMENT_METHOD, _obtenir_ou_creer_wallet, _calculer_qty_partielles
"""

import logging
import uuid as uuid_module
from decimal import Decimal

from django.db import connection, transaction

logger = logging.getLogger(__name__)

def obtenir_contexte_cashless(carte):
    """
    Résout le wallet client et la cascade d'assets fiduciaires pour un paiement tireuse.
    / Resolves the client wallet and fiduciary asset cascade for a tap payment.

    Même logique que LaBoutik : cascade TNF → TLF → FED via AssetService.
    / Same logic as LaBoutik: TNF → TLF → FED cascade via AssetService.

    :param carte: CarteCashless
    :return: dict avec wallet_client, cascade_assets (liste ordonnée).
             None si aucun asset OU si le wallet de la carte n'est pas
             résoluble (carte vierge inconnue du Fedow legacy) — le POS
             tireuse refuse alors proprement au lieu de renvoyer un 500.
             / None if no asset OR if the card wallet cannot be resolved
             (blank card unknown to legacy Fedow) — the tap POS then
             refuses cleanly instead of returning a 500.
    """
    from laboutik.views import ORDRE_CASCADE_FIDUCIAIRE, _obtenir_ou_creer_wallet
    from fedow_core.models import Asset
    from fedow_core.services import AssetService

    # --- Résoudre le wallet du client ---
    # déléguer à laboutik (logique identique, source unique)
    # PIÈGE (fix review 2026-07-06, finding C3) : _obtenir_ou_creer_wallet
    # LÈVE une Exception si la carte n'a ni user.wallet, ni wallet_ephemere,
    # et n'est pas résoluble via le Fedow legacy (can_fedow False ou carte
    # inconnue). Une carte sans wallet n'a de toute façon aucun token :
    # on transforme l'exception en refus propre (None → authorized: false).
    # / TRAP: _obtenir_ou_creer_wallet RAISES if the card has no user.wallet,
    # no wallet_ephemere, and cannot be resolved via legacy Fedow. A card
    # without a wallet has no tokens anyway: turn the exception into a clean
    # refusal (None → authorized: false).
    try:
        wallet_client = _obtenir_ou_creer_wallet(carte)
    except Exception as erreur:
        logger.warning(
            f"Tireuse : wallet non résoluble pour la carte {carte.tag_id} "
            f"— refus propre. Détail : {erreur}"
        )
        return None

    # --- Construire la cascade d'assets accessibles ---
    # / Build the cascade of accessible assets
    # Même logique que LaBoutik Phase 1 : tous les assets du tenant + fédérés.
    # / Same logic as LaBoutik Phase 1: all tenant assets + federated.
    assets_accessibles = AssetService.obtenir_assets_accessibles(connection.tenant)

    cascade_assets = []
    for categorie in ORDRE_CASCADE_FIDUCIAIRE:
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
    N LigneArticle créées (une par asset débité) avec qty proportionnelle et
        payment_method correct (TNF→LOCAL_GIFT, TLF/FED→LOCAL_EURO).
    / Cascade: debit TNF first (gift), then TLF (local), then FED (federated).
    One fedow_core Transaction is created per debited asset.
    

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
        debits_par_asset = []

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
            debits_par_asset.append((asset, montant_asset))
            restant_centimes -= montant_asset

        if restant_centimes > 0:
            # Solde insuffisant pour couvrir le montant total — ne devrait pas
            # arriver si authorize() a correctement calculé allowed_ml.
            # / Insufficient balance to cover total — shouldn't happen if
            # authorize() correctly computed allowed_ml.
            raise SoldeInsuffisant(
                f"Solde insuffisant au pour_end: manque {restant_centimes} centimes"
            )
        # Volume en centilitres pour weight_quantity (unité stock = cl)
        # / Volume in centiliters for weight_quantity (stock unit = cl)
        volume_cl = int(round(float(volume_ml) / 10))
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

        # 3. Créer N LigneArticle (1 par asset débité) — conformité LNE rapports clôture.
        # Pinte mixte 1€ TNF + 3€ TLF → 2 lignes : qty 0.25 LOCAL_GIFT + qty 0.75 LOCAL_EURO.
        # qty proportionnelle via _calculer_qty_partielles (laboutik) sur qty_totale=1 tirage.
        # weight_quantity identique sur toutes les lignes — stock décrémenté 1 seule fois.
        # / Create N LigneArticle (1 per debited asset) — LNE closing report compliance.

        from laboutik.views import MAPPING_ASSET_CATEGORY_PAYMENT_METHOD, _calculer_qty_partielles
        
        uuid_transaction = uuid_module.uuid4()

        lignes_amounts = [{"amount_centimes": montant_a} for _, montant_a in debits_par_asset]
        lignes_avec_qty = _calculer_qty_partielles(
            lignes_amounts, montant_centimes, Decimal("1")
        )

        lignes_creees = []
        premiere_ligne = None

        for i, (asset, montant_a) in enumerate(debits_par_asset):
            payment_method = MAPPING_ASSET_CATEGORY_PAYMENT_METHOD.get(
                asset.category, PaymentMethod.LOCAL_EURO
            )
            qty_partielle = lignes_avec_qty[i]["qty"]

            ligne = LigneArticle.objects.create(
                pricesold=price_sold,
                qty=qty_partielle,
                amount=montant_a,
                sale_origin=SaleOrigin.TIREUSE,
                payment_method=payment_method,
                status=LigneArticle.VALID,
                asset=asset.uuid,
                carte=carte,
                wallet=wallet_client,
                point_de_vente=tireuse.point_de_vente,
                weight_quantity=volume_cl,
                uuid_transaction=uuid_transaction,
            )
            lignes_creees.append(ligne)
            if premiere_ligne is None:
                premiere_ligne = ligne

        # 4.Session liée à la première LigneArticle (même convention que laboutik).
        # / Session linked to the first LigneArticle (same convention as laboutik).
        session.ligne_article = premiere_ligne
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
                ligne_article=premiere_ligne,  # 1 seul mouvement de stock quel que soit le nb d'assets
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
        f"montant={montant_centimes}cts assets=[{assets_debites_str}] "
        f"lignes={len(lignes_creees)} premiere_ligne={premiere_ligne.uuid if premiere_ligne else 'None'}"
    )

    return {
        "transactions": transactions_creees,
        # Compatibilité avec le code existant qui lit ["transaction"]
        # / Backward compatibility with existing code reading ["transaction"]
        "transaction": transactions_creees[0] if transactions_creees else None,
        # Compatibilité avec le code existant qui lit ["ligne_article"]
        # / Backward compatibility with existing code reading ["ligne_article"]
        "ligne_article": premiere_ligne,
        # Liste complète des N LigneArticle créées
        # / Full list of N created LigneArticle
        "lignes_articles": lignes_creees,
        "montant_centimes": montant_centimes,
    }
