"""
BaseBillet/services_refund.py — Helpers partages pour les remboursements de cartes.
BaseBillet/services_refund.py — Shared helpers for card refunds.

Utilise par :
- Administration/views_cards.py (admin web, Phase 1)
- laboutik/views.py (POS Cashless, Phase 3)

Le Product systeme "Remboursement carte" et son PriceSold associe sont crees
a la demande au premier appel, puis reutilises pour toutes les LigneArticle
de remboursement (TLF + FED + sortie cash).
"""
from decimal import Decimal

from django.utils.translation import gettext_lazy as _

from BaseBillet.models import Price, PriceSold, Product, ProductSold


def get_or_create_product_remboursement() -> Product:
    """
    Retourne le Product systeme "Remboursement carte" du tenant courant.
    Returns the system Product "Card refund" for the current tenant.

    Cree le Product la premiere fois, le reutilise ensuite.
    Identifie par methode_caisse=VIDER_CARTE (un seul par tenant).

    Utilise get_or_create pour eviter une race condition entre le filter
    et le create sur deux appels concurrents.
    / Uses get_or_create to avoid a race condition between filter and create
    on two concurrent calls.
    """
    product, _created = Product.objects.get_or_create(
        methode_caisse=Product.VIDER_CARTE,
        defaults={
            "name": str(_("Remboursement carte")),
            "publish": False,
        },
    )
    return product


def get_or_create_pricesold_refund(product: Product) -> PriceSold:
    """
    Retourne le PriceSold systeme associe au Product de remboursement.
    Returns the system PriceSold associated with the refund Product.

    Cree un Price a 0 et un PriceSold a 0 si necessaire (le montant reel
    est porte par LigneArticle.amount).

    Creates a Price at 0 and a PriceSold at 0 if needed (real amount carried
    by LigneArticle.amount).
    """
    # Price systeme partage : nom fixe "Refund", prix=0 (montant reel sur LigneArticle)
    # / Shared system Price: fixed name "Refund", prix=0 (real amount on LigneArticle)
    price, _created_price = Price.objects.get_or_create(
        product=product,
        name="Refund",
        defaults={"prix": Decimal(0)},
    )

    productsold, _created_ps = ProductSold.objects.get_or_create(
        product=product,
        event=None,
        defaults={"categorie_article": product.categorie_article},
    )

    pricesold, _created_pxs = PriceSold.objects.get_or_create(
        productsold=productsold,
        price=price,
        defaults={"prix": Decimal(0)},
    )
    return pricesold


def get_or_create_product_virement_recu() -> Product:
    """
    Retourne le Product systeme "Virement pot central" du tenant courant.
    Returns the system Product "Central pot transfer" for the current tenant.

    Cree le Product la premiere fois, le reutilise ensuite.
    Identifie par methode_caisse=VIREMENT_RECU (un seul par tenant).

    Created on first call, reused thereafter.
    Identified by methode_caisse=VIREMENT_RECU (one per tenant).

    Le helper get_or_create_pricesold_refund (existant) est reutilisable tel quel
    pour creer le PriceSold associe a ce Product.
    """
    product, _created = Product.objects.get_or_create(
        methode_caisse=Product.VIREMENT_RECU,
        defaults={
            "name": str(_("Virement pot central")),
            "publish": False,
        },
    )
    return product
