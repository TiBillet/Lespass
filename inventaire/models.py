"""
Modèles pour la gestion de stock des produits POS.
/ Models for POS product stock management.

LOCALISATION : inventaire/models.py
"""

import uuid as uuid_module

from django.db import models
from django.utils.translation import gettext_lazy as _


# Unités de mesure pour le stock / Stock measurement units
class UniteStock(models.TextChoices):
    UN = "UN", _("Pièces / Units")
    CL = "CL", _("Centilitres")
    GR = "GR", _("Grammes / Grams")


# Types de mouvement de stock / Stock movement types
class TypeMouvement(models.TextChoices):
    VE = "VE", _("Vente / Sale")
    RE = "RE", _("Réception / Reception")
    AJ = "AJ", _("Ajustement / Adjustment")
    OF = "OF", _("Offert / Offered")
    PE = "PE", _("Perte/casse / Loss/breakage")
    DM = "DM", _("Débit mètre / Meter debit")


class StockInsuffisant(Exception):
    """
    Levée quand on tente de vendre un produit en rupture de stock
    et que la vente hors stock n'est pas autorisée.
    / Raised when selling an out-of-stock product and out-of-stock sales are not allowed.
    """

    def __init__(self, product, quantite_demandee, stock_actuel):
        self.product = product
        self.quantite_demandee = quantite_demandee
        self.stock_actuel = stock_actuel
        super().__init__(
            f"Stock insuffisant pour {product.name} : "
            f"demandé={quantite_demandee}, disponible={stock_actuel}"
        )


class Stock(models.Model):
    """
    Stock d'un produit POS. Un seul enregistrement par produit (OneToOne).
    / POS product stock. One record per product (OneToOne).
    """

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid_module.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    # Produit lié / Linked product
    product = models.OneToOneField(
        "BaseBillet.Product",
        on_delete=models.CASCADE,
        related_name="stock_inventaire",
        verbose_name=_("Produit / Product"),
        help_text=_(
            "Le produit POS associé à ce stock / The POS product linked to this stock"
        ),
    )

    # Quantité en stock, en unités choisies. Peut être négatif.
    # / Current stock quantity in chosen units. Can be negative.
    quantite = models.IntegerField(
        default=0,
        verbose_name=_("Quantité / Quantity"),
        help_text=_(
            "Quantité actuelle en stock (peut être négative) / Current stock quantity (can be negative)"
        ),
    )

    # Unité de mesure / Measurement unit
    unite = models.CharField(
        max_length=2,
        choices=UniteStock.choices,
        default=UniteStock.UN,
        verbose_name=_("Unité / Unit"),
        help_text=_("Unité de mesure du stock / Stock measurement unit"),
    )

    # Seuil d'alerte. Si null, pas d'alerte.
    # / Alert threshold. If null, no alert.
    seuil_alerte = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Seuil d'alerte / Alert threshold"),
        help_text=_(
            "Alerte quand le stock descend sous ce seuil (vide = pas d'alerte) "
            "/ Alert when stock drops below this threshold (empty = no alert)"
        ),
    )

    # Autoriser la vente même si le stock est à 0 ou négatif
    # / Allow sales even when stock is 0 or negative
    autoriser_vente_hors_stock = models.BooleanField(
        default=True,
        verbose_name=_("Autoriser vente hors stock / Allow out-of-stock sales"),
        help_text=_(
            "Si coché, la vente reste possible même en rupture de stock "
            "/ If checked, sales remain possible even when out of stock"
        ),
    )

    class Meta:
        verbose_name = _("Stock")
        verbose_name_plural = _("Stocks")

    def est_en_alerte(self):
        """
        Vrai si le stock est sous le seuil d'alerte (mais pas en rupture).
        / True if stock is below alert threshold (but not at zero).
        """
        if self.seuil_alerte is None:
            return False
        return 0 < self.quantite <= self.seuil_alerte

    def est_en_rupture(self):
        """
        Vrai si le stock est à 0 ou négatif.
        / True if stock is at 0 or negative.
        """
        return self.quantite <= 0

    def __str__(self):
        return f"{self.product.name} — {self.quantite} {self.get_unite_display()}"


class MouvementStock(models.Model):
    """
    Trace chaque modification de stock : vente, réception, ajustement, etc.
    / Tracks every stock change: sale, reception, adjustment, etc.
    """

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid_module.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    # Stock concerné / Related stock
    stock = models.ForeignKey(
        Stock,
        on_delete=models.CASCADE,
        related_name="mouvements",
        verbose_name=_("Stock"),
        help_text=_(
            "Le stock concerné par ce mouvement / The stock affected by this movement"
        ),
    )

    # Type de mouvement / Movement type
    type_mouvement = models.CharField(
        max_length=2,
        choices=TypeMouvement.choices,
        verbose_name=_("Type de mouvement / Movement type"),
        help_text=_("Nature du mouvement de stock / Nature of the stock movement"),
    )

    # Delta signé : négatif pour les sorties, positif pour les entrées
    # / Signed delta: negative for outgoing, positive for incoming
    quantite = models.IntegerField(
        verbose_name=_("Quantité (delta) / Quantity (delta)"),
        help_text=_(
            "Variation signée du stock (négatif = sortie, positif = entrée) "
            "/ Signed stock change (negative = outgoing, positive = incoming)"
        ),
    )

    # Quantité en stock AVANT ce mouvement / Stock quantity BEFORE this movement
    quantite_avant = models.IntegerField(
        verbose_name=_("Quantité avant / Quantity before"),
        help_text=_(
            "Niveau de stock avant ce mouvement / Stock level before this movement"
        ),
    )

    # Motif libre / Free-text reason
    motif = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name=_("Motif / Reason"),
        help_text=_(
            "Raison du mouvement (optionnel) / Reason for the movement (optional)"
        ),
    )

    # Liens optionnels / Optional links
    ligne_article = models.ForeignKey(
        "BaseBillet.LigneArticle",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="mouvements_stock",
        verbose_name=_("Ligne article / Order line"),
        help_text=_("Ligne de vente liée (si vente) / Related sale line (if sale)"),
    )

    cloture = models.ForeignKey(
        "laboutik.ClotureCaisse",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="mouvements_stock",
        verbose_name=_("Clôture de caisse / Cash register closure"),
        help_text=_(
            "Clôture pendant laquelle ce mouvement a eu lieu / Closure during which this movement occurred"
        ),
    )

    cree_par = models.ForeignKey(
        "AuthBillet.TibilletUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="mouvements_stock_crees",
        verbose_name=_("Créé par / Created by"),
        help_text=_(
            "Utilisateur ayant effectué ce mouvement / User who performed this movement"
        ),
    )

    cree_le = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Créé le / Created at"),
        help_text=_(
            "Date et heure de création du mouvement / Movement creation date and time"
        ),
    )

    class Meta:
        verbose_name = _("Mouvement de stock / Stock movement")
        verbose_name_plural = _("Mouvements de stock / Stock movements")
        ordering = ["-cree_le"]
        indexes = [
            models.Index(fields=["-cree_le"], name="idx_mvt_cree_le"),
            models.Index(fields=["type_mouvement"], name="idx_mvt_type"),
        ]

    def __str__(self):
        return (
            f"{self.get_type_mouvement_display()} "
            f"{self.quantite:+d} — "
            f"{self.stock.product.name}"
        )
