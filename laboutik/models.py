"""
Modeles POS (Point de Vente / Cash register) pour l'app laboutik.
Points de vente, cartes maitresses, tables de restaurant, commandes, cloture.
/ POS models for the laboutik app. Points of sale, primary cards, restaurant tables, orders, closure.

LOCALISATION : laboutik/models.py
"""
import uuid as uuid_module

from django.db import models
from django.utils.translation import gettext_lazy as _
from solo.models import SingletonModel

from AuthBillet.models import TibilletUser
from BaseBillet.models import CategorieProduct, Price, Product
from QrcodeCashless.models import CarteCashless


# --- Configuration globale de l'interface caisse ---
# / Global configuration for the POS interface

class LaboutikConfiguration(SingletonModel):
    """
    Configuration globale de l'application caisse LaBoutik.
    Il n'existe qu'une seule instance par tenant (SingletonModel).
    / Global configuration for the LaBoutik POS application.
    Only one instance exists per tenant (SingletonModel).

    LOCALISATION : laboutik/models.py
    """

    # Taille de police pour les noms d'articles sur l'interface POS
    # / Font size for article names on the POS interface
    TAILLE_POLICE_CHOICES = [
        (18, _("18")),
        (20, _("20")),
        (22, _("22")),
        (24, _("24")),
        (26, _("26")),
        (28, _("28")),
    ]
    taille_police_articles = models.SmallIntegerField(
        choices=TAILLE_POLICE_CHOICES,
        default=22,
        verbose_name=_("Article font size"),
        help_text=_(
            "Taille de la police des noms d'articles sur l'interface caisse. "
            "/ Font size for article names on the POS interface."
        ),
    )

    def __str__(self):
        return "LaBoutik Configuration"

    class Meta:
        verbose_name = _("LaBoutik Configuration")


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
    ADHESION = 'A'
    COMPORTEMENT_CHOICES = [
        (DIRECT, _('Direct')),
        (KIOSK, _('Kiosk')),
        (CASHLESS, _('Cashless')),
        (ADHESION, _('Membership')),
    ]
    comportement = models.CharField(
        max_length=1, choices=COMPORTEMENT_CHOICES, default=DIRECT,
        verbose_name=_("Behavior"),
        help_text=_(
            "Operating mode: Direct (standard sale), Kiosk (self-service), "
            "Cashless (NFC only), Membership (subscriptions and memberships)."
        ),
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


# --- Commandes de restaurant ---
# / Restaurant orders

class CommandeSauvegarde(models.Model):
    """
    Commande sauvegardee pour le mode restaurant (table service).
    Chaque commande est liee a une table et contient des articles.
    / Saved order for restaurant mode (table service).
    Each order is linked to a table and contains articles.

    LOCALISATION : laboutik/models.py

    Cycle de vie / Lifecycle :
    OPEN → SERVED → PAID (→ archive=True apres cloture)
    OPEN → CANCEL (annulation)
    """
    uuid = models.UUIDField(
        primary_key=True, default=uuid_module.uuid4, editable=False, unique=True, db_index=True,
    )

    # Identifiant du service en cours (un service = une periode de travail du PV)
    # Current service identifier (a service = a POS work period)
    service = models.UUIDField(
        blank=True, null=True,
        verbose_name=_("Service"),
        help_text=_("Service session identifier (UUID). Groups orders by work period."),
    )

    # Responsable (caissier / serveur) qui a cree la commande
    # Responsible (cashier / waiter) who created the order
    responsable = models.ForeignKey(
        TibilletUser, on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='commandes_sauvegardees',
        verbose_name=_("Operator"),
        help_text=_("Cashier or waiter who created this order."),
    )

    # Table associee (nullable pour les commandes sans table)
    # Associated table (nullable for orders without a table)
    table = models.ForeignKey(
        Table, on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='commandes',
        verbose_name=_("Table"),
        help_text=_("Restaurant table for this order. Null for takeaway."),
    )

    datetime = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Creation date"),
    )

    # Statut de la commande
    # / Order status
    OPEN = 'OP'
    SERVED = 'SV'
    PAID = 'PA'
    CANCEL = 'AN'
    STATUT_CHOICES = [
        (OPEN, _('Open')),
        (SERVED, _('Served')),
        (PAID, _('Paid')),
        (CANCEL, _('Cancelled')),
    ]
    statut = models.CharField(
        max_length=2, choices=STATUT_CHOICES, default=OPEN,
        verbose_name=_("Status"),
    )

    # Note libre pour la cuisine ou le serveur
    # / Free note for the kitchen or waiter
    commentaire = models.TextField(
        blank=True, default='',
        verbose_name=_("Comment"),
        help_text=_("Kitchen notes or special requests."),
    )

    archive = models.BooleanField(
        default=False,
        verbose_name=_("Archived"),
    )

    def __str__(self):
        table_name = self.table.name if self.table else _("No table")
        return f"{table_name} — {self.get_statut_display()} ({self.datetime:%H:%M})"

    class Meta:
        ordering = ('-datetime',)
        verbose_name = _('Saved order')
        verbose_name_plural = _('Saved orders')


class ArticleCommandeSauvegarde(models.Model):
    """
    Ligne d'article dans une commande sauvegardee.
    / Article line in a saved order.

    LOCALISATION : laboutik/models.py

    Cycle de vie / Lifecycle :
    EN_ATTENTE → EN_COURS → PRET → SERVI
    EN_ATTENTE → ANNULE
    """
    commande = models.ForeignKey(
        CommandeSauvegarde, on_delete=models.CASCADE,
        related_name='articles',
        verbose_name=_("Order"),
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT,
        related_name='articles_commande',
        verbose_name=_("Product"),
    )
    price = models.ForeignKey(
        Price, on_delete=models.PROTECT,
        related_name='articles_commande',
        verbose_name=_("Price"),
    )

    qty = models.SmallIntegerField(
        default=1,
        verbose_name=_("Quantity"),
    )

    # Montant restant a payer en centimes (utile pour paiement partiel)
    # Remaining amount to pay in cents (useful for partial payment)
    reste_a_payer = models.IntegerField(
        default=0,
        verbose_name=_("Remaining to pay (cents)"),
        help_text=_("Remaining amount in cents. 0 = not yet billed."),
    )

    # Nombre d'unites restant a servir
    # Number of units remaining to serve
    reste_a_servir = models.SmallIntegerField(
        default=0,
        verbose_name=_("Remaining to serve"),
    )

    # Statut de l'article dans la commande
    # / Article status in the order
    EN_ATTENTE = 'AT'
    EN_COURS = 'EC'
    PRET = 'PR'
    SERVI = 'SV'
    ANNULE = 'AN'
    STATUT_CHOICES = [
        (EN_ATTENTE, _('Waiting')),
        (EN_COURS, _('In progress')),
        (PRET, _('Ready')),
        (SERVI, _('Served')),
        (ANNULE, _('Cancelled')),
    ]
    statut = models.CharField(
        max_length=2, choices=STATUT_CHOICES, default=EN_ATTENTE,
        verbose_name=_("Status"),
    )

    def __str__(self):
        return f"{self.product.name} x{self.qty} ({self.get_statut_display()})"

    class Meta:
        ordering = ('commande', 'product__name')
        verbose_name = _('Order article')
        verbose_name_plural = _('Order articles')


# --- Cloture de caisse ---
# / Cash register closure

class ClotureCaisse(models.Model):
    """
    Rapport de cloture de caisse.
    Un rapport est cree a chaque fin de service pour un point de vente.
    Les totaux sont en centimes (int).
    / Cash register closure report.
    A report is created at the end of each service for a point of sale.
    All totals are in cents (int).

    LOCALISATION : laboutik/models.py
    """
    uuid = models.UUIDField(
        primary_key=True, default=uuid_module.uuid4, editable=False, unique=True, db_index=True,
    )

    # Point de vente qui a declenche la cloture
    # / Point of sale that triggered the closure
    point_de_vente = models.ForeignKey(
        PointDeVente, on_delete=models.PROTECT,
        related_name='clotures',
        verbose_name=_("Point of sale"),
        help_text=_("Point of sale that triggered this closure."),
    )

    # Responsable (caissier) qui a declenche la cloture
    # / Operator (cashier) who triggered the closure
    responsable = models.ForeignKey(
        TibilletUser, on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='clotures_caisse',
        verbose_name=_("Operator"),
        help_text=_("Cashier who performed the closure."),
    )

    # Debut du service couvert par cette cloture
    # / Start of the service period covered by this closure
    datetime_ouverture = models.DateTimeField(
        verbose_name=_("Service start"),
        help_text=_("Start of the service period covered by this closure."),
    )

    # Moment de la cloture (automatique a la creation)
    # / Closure timestamp (automatic on creation)
    datetime_cloture = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Closure datetime"),
    )

    # Totaux par moyen de paiement — en centimes (ex: 50.10€ = 5010)
    # / Totals by payment method — in cents (e.g. 50.10€ = 5010)
    total_especes = models.IntegerField(
        default=0,
        verbose_name=_("Cash total (cents)"),
        help_text=_("Total cash amount in cents."),
    )
    total_carte_bancaire = models.IntegerField(
        default=0,
        verbose_name=_("Credit card total (cents)"),
        help_text=_("Total credit card amount in cents."),
    )
    total_cashless = models.IntegerField(
        default=0,
        verbose_name=_("Cashless total (cents)"),
        help_text=_("Total cashless/NFC amount in cents."),
    )
    total_general = models.IntegerField(
        default=0,
        verbose_name=_("Grand total (cents)"),
        help_text=_("Grand total in cents (cash + card + cashless)."),
    )

    nombre_transactions = models.IntegerField(
        default=0,
        verbose_name=_("Transaction count"),
        help_text=_("Number of LigneArticle records in this period."),
    )

    # Detail complet du rapport (par categorie, produit, moyen de paiement, commandes)
    # / Full report detail (by category, product, payment method, orders)
    rapport_json = models.JSONField(
        default=dict, blank=True,
        verbose_name=_("JSON report"),
        help_text=_("Detailed report: par_categorie, par_produit, par_moyen_paiement, commandes."),
    )

    def __str__(self):
        return f"{self.point_de_vente.name} — {self.datetime_cloture}"

    class Meta:
        ordering = ('-datetime_cloture',)
        verbose_name = _('Cash register closure')
        verbose_name_plural = _('Cash register closures')
