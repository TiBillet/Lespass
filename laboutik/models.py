"""
Modeles POS (Point de Vente / Cash register) pour l'app laboutik.
Points de vente, cartes maitresses, tables de restaurant.
/ POS models for the laboutik app. Points of sale, primary cards, restaurant tables.

LOCALISATION : laboutik/models.py

⚠️ CommandeSauvegarde et ClotureCaisse ne sont PAS ici (Phase 4 et 5).
"""
import uuid as uuid_module

from django.db import models
from django.utils.translation import gettext_lazy as _

from BaseBillet.models import CategorieProduct, Product
from QrcodeCashless.models import CarteCashless


# --- Point de vente ---
# / Point of sale

class PointDeVente(models.Model):
    """
    Un point de vente physique ou virtuel (bar, restaurant, kiosque, etc.).
    Chaque point de vente a ses propres produits et categories.
    / A physical or virtual point of sale (bar, restaurant, kiosk, etc.).

    LOCALISATION : laboutik/models.py
    """
    uuid = models.UUIDField(
        primary_key=True, default=uuid_module.uuid4, editable=False, unique=True, db_index=True,
    )
    name = models.CharField(
        max_length=200, unique=True,
        verbose_name=_("Name"),
        help_text=_("Point of sale name. Must be unique."),
    )
    icon = models.CharField(
        max_length=50, blank=True, null=True,
        verbose_name=_("Icon"),
        help_text=_("Icon name (e.g. Bootstrap Icons class)."),
    )

    # Comportement du point de vente
    # / Point of sale behavior mode
    DIRECT = 'D'
    KIOSK = 'K'
    CASHLESS = 'C'
    COMPORTEMENT_CHOICES = [
        (DIRECT, _('Direct')),
        (KIOSK, _('Kiosk')),
        (CASHLESS, _('Cashless')),
    ]
    comportement = models.CharField(
        max_length=1, choices=COMPORTEMENT_CHOICES, default=DIRECT,
        verbose_name=_("Behavior"),
        help_text=_("Operating mode: Direct (standard sale), Kiosk (self-service), Cashless (NFC only)."),
    )

    # Options de fonctionnement
    # / Operating options
    service_direct = models.BooleanField(
        default=True,
        verbose_name=_("Direct service"),
        help_text=_("If checked, orders are served immediately (no table service)."),
    )
    afficher_les_prix = models.BooleanField(
        default=True,
        verbose_name=_("Show prices"),
        help_text=_("Display prices on the POS interface."),
    )

    # Moyens de paiement acceptes
    # / Accepted payment methods
    accepte_especes = models.BooleanField(
        default=True,
        verbose_name=_("Accepts cash"),
    )
    accepte_carte_bancaire = models.BooleanField(
        default=True,
        verbose_name=_("Accepts credit card"),
    )
    accepte_cheque = models.BooleanField(
        default=False,
        verbose_name=_("Accepts check"),
    )
    accepte_commandes = models.BooleanField(
        default=False,
        verbose_name=_("Accepts orders"),
        help_text=_("Enable table order management for this point of sale."),
    )

    poid_liste = models.SmallIntegerField(
        default=0,
        verbose_name=_("Display order"),
        help_text=_("Lower values are displayed first."),
    )
    hidden = models.BooleanField(
        default=False,
        verbose_name=_("Hidden"),
        help_text=_("Hide this point of sale from the selection screen."),
    )

    # Produits et categories disponibles a ce point de vente
    # / Products and categories available at this point of sale
    products = models.ManyToManyField(
        Product, blank=True,
        related_name='points_de_vente',
        verbose_name=_("Products"),
        help_text=_("Products available at this point of sale."),
    )
    categories = models.ManyToManyField(
        CategorieProduct, blank=True,
        related_name='points_de_vente',
        verbose_name=_("Categories"),
        help_text=_("Product categories available at this point of sale."),
    )

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('poid_liste', 'name')
        verbose_name = _('Point of sale')
        verbose_name_plural = _('Points of sale')


# --- Carte primaire ---
# Associe une carte NFC physique a un ou plusieurs points de vente.
# Permet d'identifier l'operateur/caissier.
# / Primary card. Links a physical NFC card to one or more points of sale.

class CartePrimaire(models.Model):
    """
    Carte NFC d'un operateur de caisse.
    Le scan de cette carte identifie le caissier et charge ses points de vente.
    / POS operator NFC card. Scanning identifies the cashier and loads their points of sale.

    LOCALISATION : laboutik/models.py
    """
    uuid = models.UUIDField(
        primary_key=True, default=uuid_module.uuid4, editable=False, unique=True, db_index=True,
    )
    # Carte NFC physique associee
    # / Associated physical NFC card
    carte = models.OneToOneField(
        CarteCashless, on_delete=models.CASCADE,
        related_name='carte_primaire',
        verbose_name=_("NFC card"),
        help_text=_("Physical NFC card associated with this primary card."),
    )
    # Points de vente accessibles avec cette carte
    # / Points of sale accessible with this card
    points_de_vente = models.ManyToManyField(
        PointDeVente, blank=True,
        related_name='cartes_primaires',
        verbose_name=_("Points of sale"),
        help_text=_("Points of sale this operator can access."),
    )
    # Mode edition : permet de modifier les produits/prix depuis l'interface POS
    # / Edit mode: allows modifying products/prices from the POS interface
    edit_mode = models.BooleanField(
        default=False,
        verbose_name=_("Edit mode"),
        help_text=_("Allow this operator to modify products and prices from the POS interface."),
    )
    datetime = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Creation date"),
    )

    def __str__(self):
        return f"{self.carte} (primary)"

    class Meta:
        verbose_name = _('Primary card')
        verbose_name_plural = _('Primary cards')


# --- Tables de restaurant ---
# / Restaurant tables

class CategorieTable(models.Model):
    """
    Categorie de table (salle, terrasse, bar, etc.).
    / Table category (indoor, terrace, bar, etc.).

    LOCALISATION : laboutik/models.py
    """
    name = models.CharField(
        max_length=200, unique=True,
        verbose_name=_("Name"),
        help_text=_("Category name (e.g. Indoor, Terrace, Bar)."),
    )
    icon = models.CharField(
        max_length=50, blank=True, null=True,
        verbose_name=_("Icon"),
        help_text=_("Icon name (e.g. Bootstrap Icons class)."),
    )

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)
        verbose_name = _('Table category')
        verbose_name_plural = _('Table categories')


class Table(models.Model):
    """
    Table de restaurant. Peut etre positionnee sur un plan de salle.
    / Restaurant table. Can be positioned on a floor plan.

    LOCALISATION : laboutik/models.py
    """
    uuid = models.UUIDField(
        primary_key=True, default=uuid_module.uuid4, editable=False, unique=True, db_index=True,
    )
    name = models.CharField(
        max_length=200, unique=True,
        verbose_name=_("Name"),
        help_text=_("Table name or number (e.g. Table 1, Bar 3)."),
    )
    categorie = models.ForeignKey(
        CategorieTable, on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='tables',
        verbose_name=_("Category"),
    )
    poids = models.SmallIntegerField(
        default=0,
        verbose_name=_("Display order"),
        help_text=_("Lower values are displayed first."),
    )

    # Statut de la table
    # / Table status
    LIBRE = 'L'
    OCCUPEE = 'O'
    SERVIE = 'S'
    STATUT_CHOICES = [
        (LIBRE, _('Free')),
        (OCCUPEE, _('Occupied')),
        (SERVIE, _('Served')),
    ]
    statut = models.CharField(
        max_length=1, choices=STATUT_CHOICES, default=LIBRE,
        verbose_name=_("Status"),
    )

    # Table temporaire (creee a la volee pour un service)
    # / Temporary table (created on the fly for a service)
    ephemere = models.BooleanField(
        default=False,
        verbose_name=_("Temporary"),
        help_text=_("Temporary table created for a single service."),
    )
    archive = models.BooleanField(
        default=False,
        verbose_name=_("Archived"),
    )

    # Position sur le plan de salle (pixels)
    # / Position on the floor plan (pixels)
    position_top = models.IntegerField(
        blank=True, null=True,
        verbose_name=_("Top position"),
        help_text=_("Vertical position in pixels on the floor plan."),
    )
    position_left = models.IntegerField(
        blank=True, null=True,
        verbose_name=_("Left position"),
        help_text=_("Horizontal position in pixels on the floor plan."),
    )

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('poids', 'name')
        verbose_name = _('Table')
        verbose_name_plural = _('Tables')
