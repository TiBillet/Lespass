"""
Signal post_save sur fedow_core.Asset.
Cree automatiquement un Product de recharge multi-tarif
quand un Asset TLF/TNF/TIM est cree.

/ post_save signal on fedow_core.Asset.
Auto-creates a multi-rate top-up Product
when a TLF/TNF/TIM Asset is created.

LOCALISATION : fedow_core/signals.py
"""

import logging
from decimal import Decimal

from django.db.models.signals import post_save
from django.dispatch import receiver

from fedow_core.models import Asset

logger = logging.getLogger(__name__)

# Mapping : Asset.category → (Product.methode_caisse, prefixe du nom)
# / Mapping: Asset.category → (Product.methode_caisse, name prefix)
CATEGORY_TO_RECHARGE = {
    Asset.TLF: ("RE", "Recharge"),
    Asset.TNF: ("RC", "Recharge cadeau"),
    Asset.TIM: ("TM", "Recharge temps"),
}

# Tarifs par defaut pour les produits de recharge auto-crees
# / Default prices for auto-created top-up products
TARIFS_DEFAUT = [
    {"name": "1", "prix": Decimal("1.00"), "free_price": False, "order": 1},
    {"name": "5", "prix": Decimal("5.00"), "free_price": False, "order": 2},
    {"name": "10", "prix": Decimal("10.00"), "free_price": False, "order": 3},
    {"name": "Libre", "prix": Decimal("0"), "free_price": True, "order": 4},
]

# Couleurs par defaut pour les boutons POS selon la categorie
# / Default POS button colors by category
COULEURS_PAR_CATEGORIE = {
    Asset.TLF: {"fond": "#10B981", "texte": "#FFFFFF", "icon": "fa-coins"},
    Asset.TNF: {"fond": "#EC4899", "texte": "#FFFFFF", "icon": "fa-gift"},
    Asset.TIM: {"fond": "#8B5CF6", "texte": "#FFFFFF", "icon": "fa-clock"},
}


@receiver(post_save, sender=Asset)
def creer_ou_mettre_a_jour_product_recharge(sender, instance, created, **kwargs):
    """
    Signal post_save sur Asset.
    - Creation (TLF/TNF/TIM) : cree un Product + 4 Prices + attache aux PV CASHLESS.
    - Modification : propage archivage et renommage.

    / post_save signal on Asset.
    - Creation (TLF/TNF/TIM): creates Product + 4 Prices + attaches to CASHLESS POS.
    - Modification: propagates archiving and renaming.
    """
    # Import ici pour eviter les imports circulaires
    # / Import here to avoid circular imports
    from django.db import connection

    from BaseBillet.models import CategorieProduct, Price, Product
    from laboutik.models import PointDeVente

    # Les tables Product, Price, CategorieProduct, PointDeVente sont dans TENANT_APPS.
    # Elles n'existent pas dans le schema public.
    # Si on est dans le schema public (ex: tests fedow_core), on ne fait rien.
    # / Product, Price, CategorieProduct, PointDeVente are TENANT_APPS tables.
    # They don't exist in the public schema.
    # If we're in public schema (e.g. fedow_core tests), skip.
    schema_courant = connection.schema_name
    if schema_courant == "public":
        return

    categorie_asset = instance.category

    # Seuls TLF, TNF, TIM generent des produits de recharge
    # / Only TLF, TNF, TIM generate top-up products
    if categorie_asset not in CATEGORY_TO_RECHARGE:
        return

    methode_caisse, prefixe_nom = CATEGORY_TO_RECHARGE[categorie_asset]
    nom_produit = f"{prefixe_nom} {instance.name}"

    if created:
        # --- Creation : nouveau Product + Prices + PV ---
        # / Creation: new Product + Prices + POS

        # Trouver ou creer la CategorieProduct "Cashless"
        # / Find or create the "Cashless" CategorieProduct
        categorie_cashless, _ = CategorieProduct.objects.get_or_create(
            name="Cashless",
            defaults={
                "icon": "fa-wallet",
                "couleur_texte": "#FFFFFF",
                "couleur_fond": "#10B981",
            },
        )

        couleurs = COULEURS_PAR_CATEGORIE.get(categorie_asset, {})

        produit = Product.objects.create(
            name=nom_produit,
            methode_caisse=methode_caisse,
            asset=instance,
            categorie_pos=categorie_cashless,
            couleur_fond_pos=couleurs.get("fond", "#10B981"),
            couleur_texte_pos=couleurs.get("texte", "#FFFFFF"),
            icon_pos=couleurs.get("icon", "fa-coins"),
        )

        # Creer les 4 tarifs par defaut (1, 5, 10, Libre)
        # / Create the 4 default prices (1, 5, 10, Free)
        for tarif in TARIFS_DEFAUT:
            Price.objects.create(
                product=produit,
                name=tarif["name"],
                prix=tarif["prix"],
                free_price=tarif["free_price"],
                publish=True,
                order=tarif["order"],
            )

        # Ajouter le Product a tous les PV CASHLESS du tenant
        # / Add the Product to all CASHLESS POS of the tenant
        pvs_cashless = PointDeVente.objects.filter(
            comportement=PointDeVente.CASHLESS,
        )
        for pv in pvs_cashless:
            pv.products.add(produit)

        logger.info(
            f"Product de recharge cree : '{produit.name}' "
            f"(methode={methode_caisse}) pour Asset '{instance.name}' "
            f"({instance.category}), attache a {pvs_cashless.count()} PV CASHLESS"
        )

    else:
        # --- Modification : propager archivage et renommage ---
        # / Modification: propagate archiving and renaming
        produit = Product.objects.filter(asset=instance).first()
        if produit is None:
            return

        champs_a_mettre_a_jour = []

        # Propagation archivage (pas de propagation de `active` : le filtre POS
        # dans _construire_donnees_articles lit asset.active directement au query time,
        # donc pas besoin de dupliquer l'etat sur le Product)
        # / Archive propagation (no `active` propagation: the POS filter in
        # _construire_donnees_articles reads asset.active at query time directly)
        if produit.archive != instance.archive:
            produit.archive = instance.archive
            champs_a_mettre_a_jour.append("archive")

        # Propagation renommage
        # / Name propagation
        nom_attendu = f"{prefixe_nom} {instance.name}"
        if produit.name != nom_attendu:
            produit.name = nom_attendu
            champs_a_mettre_a_jour.append("name")

        if champs_a_mettre_a_jour:
            produit.save(update_fields=champs_a_mettre_a_jour)
            logger.info(
                f"Product '{produit.name}' mis a jour : {champs_a_mettre_a_jour}"
            )
