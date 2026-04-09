"""
Facturation des tirages de bière via fedow_core.
/ Billing for beer pours via fedow_core.

LOCALISATION : controlvanne/billing.py

Ce module encapsule la logique de facturation spécifique à la tireuse.
Le ViewSet appelle ces fonctions — séparation ViewSet / logique métier.
/ This module encapsulates tap-specific billing logic.
The ViewSet calls these functions — separation of ViewSet / business logic.

Dépendances :
- fedow_core.services : WalletService, TransactionService
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


def obtenir_contexte_cashless(carte):
    """
    Résout le wallet et l'asset TLF pour un paiement cashless tireuse.
    / Resolves the wallet and TLF asset for a tap cashless payment.

    Même logique que _obtenir_ou_creer_wallet() dans laboutik/views.py
    mais retourne aussi l'asset TLF et le wallet du lieu.
    / Same logic as _obtenir_ou_creer_wallet() in laboutik/views.py
    but also returns the TLF asset and the venue wallet.

    :param carte: CarteCashless
    :return: dict avec wallet_client, asset_tlf, wallet_lieu. None si pas d'asset TLF.
    """
    from AuthBillet.models import Wallet
    from fedow_core.models import Asset

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

    # --- Trouver l'asset TLF actif du tenant ---
    # / Find the active TLF asset for this tenant
    asset_tlf = Asset.objects.filter(
        tenant_origin=connection.tenant,
        category=Asset.TLF,
        active=True,
    ).first()

    if not asset_tlf:
        logger.warning(f"Pas d'asset TLF actif pour le tenant {connection.tenant.name}")
        return None

    wallet_lieu = asset_tlf.wallet_origin

    return {
        "wallet_client": wallet_client,
        "asset_tlf": asset_tlf,
        "wallet_lieu": wallet_lieu,
    }


def calculer_volume_autorise_ml(
    solde_centimes, prix_litre_decimal, reservoir_disponible_ml
):
    """
    Calcule le volume maximum autorisé en ml depuis le solde wallet.
    / Computes the maximum allowed volume in ml from wallet balance.

    Formule : (solde_centimes / prix_centimes_par_litre) * 1000 ml
    / Formula: (balance_cents / price_cents_per_liter) * 1000 ml

    :param solde_centimes: int — solde du wallet en centimes
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
    Facture un tirage de bière : Transaction + LigneArticle + MouvementStock.
    / Bills a beer pour: Transaction + LigneArticle + MouvementStock.

    Appelé au pour_end quand le volume final est connu.
    / Called at pour_end when the final volume is known.

    :param session: RfidSession — la session de service
    :param tireuse: TireuseBec — la tireuse
    :param carte: CarteCashless — la carte NFC du client
    :param volume_ml: Decimal — volume servi en ml
    :param contexte_cashless: dict retourné par obtenir_contexte_cashless()
    :param ip: str — IP du Raspberry Pi
    :return: dict avec transaction, ligne_article, montant_centimes. None si volume=0.
    """
    from fedow_core.services import TransactionService
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

    # Calculer le montant en centimes / Calculate amount in cents
    # montant = volume_ml * prix_litre / 1000 * 100
    # Ex: 250ml * 3.50 EUR/L = 0.250L * 3.50 = 0.875 EUR = 88 centimes
    montant_eur = volume_ml * prix_litre / Decimal("1000")
    montant_centimes = int(round(montant_eur * 100))

    if montant_centimes <= 0:
        return None

    wallet_client = contexte_cashless["wallet_client"]
    wallet_lieu = contexte_cashless["wallet_lieu"]
    asset_tlf = contexte_cashless["asset_tlf"]
    tenant_courant = connection.tenant

    # --- Bloc atomique : transaction + LigneArticle + stock ---
    # / Atomic block: transaction + LigneArticle + stock
    with transaction.atomic():
        # 1. Créer la transaction fedow_core (débit client → crédit lieu)
        # / Create fedow_core transaction (debit client → credit venue)
        tx = TransactionService.creer_vente(
            sender_wallet=wallet_client,
            receiver_wallet=wallet_lieu,
            asset=asset_tlf,
            montant_en_centimes=montant_centimes,
            tenant=tenant_courant,
            card=carte,
            ip=ip,
            comment=f"Tirage {tireuse.nom_tireuse}: {float(volume_ml):.0f}ml",
        )

        # 2. Snapshots ProductSold / PriceSold
        # Le fut actif est un Product, le prix est un Price avec poids_mesure=True
        # / The active keg is a Product, the price is a Price with poids_mesure=True
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

        # 3. Créer la LigneArticle / Create the LigneArticle
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
            asset=asset_tlf.uuid,
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

    logger.info(
        f"Facturation: tireuse={tireuse.nom_tireuse} volume={float(volume_ml):.0f}ml "
        f"montant={montant_centimes}cts tx={tx.id} ligne={ligne.uuid}"
    )

    return {
        "transaction": tx,
        "ligne_article": ligne,
        "montant_centimes": montant_centimes,
    }
