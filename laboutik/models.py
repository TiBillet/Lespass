"""
Modeles POS (Point de Vente / Cash register) pour l'app laboutik.
Points de vente, cartes maitresses, tables de restaurant, commandes, cloture.
/ POS models for the laboutik app. Points of sale, primary cards, restaurant tables, orders, closure.

LOCALISATION : laboutik/models.py
"""
import uuid as uuid_module

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from solo.models import SingletonModel

from AuthBillet.models import TibilletUser
from BaseBillet.models import CategorieProduct, Price, Product
from QrcodeCashless.models import CarteCashless
from root_billet.utils import fernet_encrypt, fernet_decrypt


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

    # Identifiants Sunmi Cloud (chiffres avec Fernet)
    # Le champ stocke la valeur chiffree. Utiliser les methodes get/set pour lire/ecrire.
    # / Sunmi Cloud credentials (Fernet-encrypted)
    # The field stores the encrypted value. Use get/set methods to read/write.
    sunmi_app_id = models.CharField(
        max_length=200, blank=True, null=True,
        verbose_name=_("Sunmi App ID (encrypted)"),
        help_text=_(
            "Identifiant de l'application Sunmi Cloud (stocke chiffre). "
            "/ Sunmi Cloud application ID (stored encrypted)."
        ),
    )
    sunmi_app_key = models.CharField(
        max_length=200, blank=True, null=True,
        verbose_name=_("Sunmi App Key (encrypted)"),
        help_text=_(
            "Cle de l'application Sunmi Cloud (stockee chiffree). "
            "/ Sunmi Cloud application key (stored encrypted)."
        ),
    )

    # --- Cle HMAC pour le chainage d'integrite (conformite LNE exigence 8) ---
    # La cle est chiffree avec Fernet. L'utilisateur final n'y a jamais acces.
    # / HMAC key for integrity chaining (LNE compliance req. 8)
    # Key is Fernet-encrypted. End user never has access.
    hmac_key = models.CharField(
        max_length=200, blank=True, null=True,
        verbose_name=_("HMAC key (encrypted)"),
        help_text=_(
            "Cle HMAC pour le chainage d'integrite des donnees d'encaissement. "
            "Generee automatiquement, stockee chiffree Fernet. "
            "/ HMAC key for POS data integrity chaining. "
            "Auto-generated, Fernet-encrypted."
        ),
    )

    # --- Configuration rapports comptables ---
    # / Accounting reports configuration
    fond_de_caisse = models.IntegerField(
        default=0,
        verbose_name=_("Cash float (cents)"),
        help_text=_(
            "Montant initial du tiroir-caisse en centimes. "
            "/ Initial cash drawer amount in cents."
        ),
    )
    rapport_emails = models.JSONField(
        default=list, blank=True,
        verbose_name=_("Report email recipients"),
        help_text=_(
            "Liste d'adresses email pour l'envoi automatique des rapports. "
            "/ List of email addresses for automatic report sending."
        ),
    )
    PERIODICITE_CHOICES = [
        ('daily', _('Daily')),
        ('weekly', _('Weekly')),
        ('monthly', _('Monthly')),
        ('yearly', _('Yearly')),
    ]
    rapport_periodicite = models.CharField(
        max_length=10, choices=PERIODICITE_CHOICES, default='daily',
        verbose_name=_("Report frequency"),
        help_text=_(
            "Frequence d'envoi automatique des rapports comptables. "
            "/ Automatic accounting report sending frequency."
        ),
    )
    pied_ticket = models.TextField(
        blank=True, default='',
        verbose_name=_("Receipt footer text"),
        help_text=_(
            "Texte libre imprime en bas de chaque ticket de vente. "
            "/ Custom text printed at the bottom of every receipt."
        ),
    )

    # --- Total perpetuel (conformite LNE exigence 7) ---
    # Cumul depuis la mise en service. JAMAIS remis a 0.
    # / Cumulative total since first use. NEVER reset to 0.
    total_perpetuel = models.IntegerField(
        default=0,
        verbose_name=_("Perpetual total (cents)"),
        help_text=_(
            "Total cumule de toutes les clotures depuis la mise en service. "
            "Ne doit jamais etre remis a zero. "
            "/ Cumulative total of all closures since first use. "
            "Must never be reset to zero."
        ),
    )

    # --- Compteur sequentiel de tickets de vente (conformite LNE) ---
    # Incremente a chaque ticket de vente imprime. Global au tenant.
    # / Sequential receipt counter (LNE compliance). Incremented per printed sale ticket. Global to tenant.
    compteur_tickets = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Receipt counter"),
        help_text=_(
            "Compteur sequentiel de tickets de vente. "
            "Incremente automatiquement a chaque impression. "
            "/ Sequential receipt counter. "
            "Auto-incremented on each print."
        ),
    )

    # --- Mode ecole / formation (conformite LNE exigence 5) ---
    # Quand actif, les ventes sont marquees LABOUTIK_TEST.
    # Le bandeau "MODE ECOLE" est visible sur l'interface POS.
    # Les tickets portent la mention "SIMULATION".
    # / Training mode (LNE compliance req. 5).
    # When active, sales are marked LABOUTIK_TEST.
    # "TRAINING MODE" banner visible on POS interface.
    # Receipts carry "SIMULATION" label.
    mode_ecole = models.BooleanField(
        default=False,
        verbose_name=_("Training mode"),
        help_text=_(
            "Active le mode ecole. Les ventes sont marquees comme fictives "
            "et exclues des rapports de production. "
            "/ Enables training mode. Sales are marked as fictitious "
            "and excluded from production reports."
        ),
    )

    def get_sunmi_app_id(self):
        """Dechiffre et retourne le Sunmi App ID, ou None si vide.
        / Decrypts and returns the Sunmi App ID, or None if empty."""
        if not self.sunmi_app_id:
            return None
        return fernet_decrypt(self.sunmi_app_id)

    def set_sunmi_app_id(self, value):
        """Chiffre et stocke le Sunmi App ID.
        / Encrypts and stores the Sunmi App ID."""
        if not value:
            self.sunmi_app_id = None
        else:
            self.sunmi_app_id = fernet_encrypt(value)

    def get_sunmi_app_key(self):
        """Dechiffre et retourne la Sunmi App Key, ou None si vide.
        / Decrypts and returns the Sunmi App Key, or None if empty."""
        if not self.sunmi_app_key:
            return None
        return fernet_decrypt(self.sunmi_app_key)

    def set_sunmi_app_key(self, value):
        """Chiffre et stocke la Sunmi App Key.
        / Encrypts and stores the Sunmi App Key."""
        if not value:
            self.sunmi_app_key = None
        else:
            self.sunmi_app_key = fernet_encrypt(value)

    def get_hmac_key(self):
        """Dechiffre et retourne la cle HMAC, ou None si vide.
        / Decrypts and returns the HMAC key, or None if empty."""
        if not self.hmac_key:
            return None
        from root_billet.utils import fernet_decrypt
        return fernet_decrypt(self.hmac_key)

    def set_hmac_key(self, value):
        """Chiffre et stocke la cle HMAC.
        / Encrypts and stores the HMAC key."""
        if not value:
            self.hmac_key = None
        else:
            from root_billet.utils import fernet_encrypt
            self.hmac_key = fernet_encrypt(value)

    def get_or_create_hmac_key(self):
        """
        Retourne la cle HMAC. La genere si elle n'existe pas encore.
        Cle de 256 bits (32 octets) en hexadecimal.
        / Returns HMAC key. Generates it if not yet created.
        256-bit key (32 bytes) in hexadecimal.
        """
        cle_existante = self.get_hmac_key()
        if cle_existante:
            return cle_existante

        import secrets
        nouvelle_cle = secrets.token_hex(32)
        self.set_hmac_key(nouvelle_cle)
        self.save(update_fields=['hmac_key'])
        return nouvelle_cle

    def __str__(self):
        return "LaBoutik Configuration"

    class Meta:
        verbose_name = _("LaBoutik Configuration")


# --- Imprimante ---
# / Printer

class Printer(models.Model):
    """
    Imprimante thermique pour tickets de vente ou commandes cuisine.
    Trois types : Sunmi Cloud (SC, via HTTPS), Sunmi Inner (SI, via WebSocket),
    Sunmi LAN (LN, via HTTP direct sur le reseau local).
    / Thermal printer for sale tickets or kitchen order tickets.
    Three types: Sunmi Cloud (SC, via HTTPS), Sunmi Inner (SI, via WebSocket),
    Sunmi LAN (LN, via direct HTTP on local network).

    LOCALISATION : laboutik/models.py
    """
    uuid = models.UUIDField(
        primary_key=True, default=uuid_module.uuid4, editable=False, unique=True, db_index=True,
    )
    name = models.CharField(
        max_length=100,
        verbose_name=_("Name"),
        help_text=_("Printer name (e.g. Kitchen, Bar, Main)."),
    )

    # Type d'imprimante
    # SC = Sunmi Cloud (HTTPS HMAC, imprimante distante via le cloud Sunmi)
    # SI = Sunmi Inner (WebSocket, imprimante integree dans la tablette Sunmi)
    # LN = Sunmi LAN (HTTP direct sur le reseau local, sans authentification)
    # MK = Mock (affichage ASCII dans la console Celery, pour le dev/test)
    # / Printer type
    # SC = Sunmi Cloud (HTTPS HMAC, remote printer via Sunmi cloud)
    # SI = Sunmi Inner (WebSocket, built-in printer on Sunmi tablet)
    # LN = Sunmi LAN (direct HTTP on local network, no authentication)
    # MK = Mock (ASCII pretty-print in Celery console, for dev/test)
    SUNMI_CLOUD = 'SC'
    SUNMI_INNER = 'SI'
    SUNMI_LAN = 'LN'
    MOCK = 'MK'
    PRINTER_TYPE_CHOICES = [
        (SUNMI_CLOUD, _('Sunmi Cloud')),
        (SUNMI_INNER, _('Sunmi Inner')),
        (SUNMI_LAN, _('Sunmi LAN')),
        (MOCK, _('Mock (console)')),
    ]
    printer_type = models.CharField(
        max_length=2, choices=PRINTER_TYPE_CHOICES, default=SUNMI_CLOUD,
        verbose_name=_("Printer type"),
        help_text=_(
            "Sunmi Cloud: remote printer via HTTPS. "
            "Sunmi Inner: built-in printer on Sunmi tablet via WebSocket. "
            "Sunmi LAN: direct printing on local network (same subnet)."
        ),
    )

    # Nombre de dots par ligne — depend du modele d'imprimante.
    # NT31x (80mm kitchen cloud) = 576 dots
    # NT21x (58mm cloud) = 384 dots
    # 57mm = 240 dots
    # / Dots per line — depends on the printer model.
    dots_per_line = models.SmallIntegerField(
        default=576,
        verbose_name=_("Dots per line"),
        help_text=_(
            "Number of dots per line. "
            "576 for 80mm NT31x (kitchen cloud), "
            "384 for 58mm NT21x, "
            "240 for 57mm."
        ),
    )

    # Numero de serie Sunmi (pour Sunmi Cloud uniquement)
    # / Sunmi serial number (Sunmi Cloud only)
    sunmi_serial_number = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name=_("Sunmi serial number"),
        help_text=_("Serial number (SN) of the Sunmi Cloud printer. Not needed for Sunmi Inner."),
    )

    # Adresse IP pour l'impression en reseau local (mode LAN uniquement).
    # L'imprimante et le serveur doivent etre sur le meme sous-reseau.
    # / IP address for local network printing (LAN mode only).
    # The printer and server must be on the same subnet.
    ip_address = models.GenericIPAddressField(
        blank=True, null=True,
        verbose_name=_("IP address"),
        help_text=_(
            "IP address for LAN printing (same subnet). "
            "Not needed for Cloud or Inner."
        ),
    )

    active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_("Uncheck to disable printing on this printer."),
    )

    def __str__(self):
        return f"{self.name} ({self.get_printer_type_display()})"

    class Meta:
        ordering = ('name',)
        verbose_name = _('Printer')
        verbose_name_plural = _('Printers')


# --- Point de vente ---
# / Point of sale

class PointDeVente(models.Model):
    """
    Un point de vente physique ou virtuel (bar, restaurant, billetterie, etc.).
    Le type du PV (comportement) determine le chargement automatique des articles.
    Les articles du M2M products sont toujours charges en plus.
    / A physical or virtual point of sale (bar, restaurant, ticketing, etc.).
    The POS type (comportement) determines automatic article loading.
    M2M products are always loaded in addition.

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

    # Type du point de vente — determine le chargement automatique des articles.
    # DIRECT : articles du M2M products uniquement (bar, restaurant, etc.)
    # ADHESION : charge automatiquement tous les Product(categorie_article=ADHESION)
    # CASHLESS : charge automatiquement toutes les recharges
    # BILLETTERIE : construit les articles depuis les evenements futurs
    # AVANCE : mode commande restaurant (reserve, pas code)
    # Les articles du M2M products sont toujours charges EN PLUS du chargement automatique.
    # / POS type — determines automatic article loading.
    # DIRECT: M2M products only (bar, restaurant, etc.)
    # ADHESION: auto-loads all Product(categorie_article=ADHESION)
    # CASHLESS: auto-loads all top-up products
    # BILLETTERIE: builds articles from future events
    # AVANCE: restaurant order mode (reserved, not coded)
    # M2M products are always loaded IN ADDITION to automatic loading.
    DIRECT = 'D'
    ADHESION = 'A'
    CASHLESS = 'C'
    BILLETTERIE = 'T'
    AVANCE = 'V'
    COMPORTEMENT_CHOICES = [
        (DIRECT, _('Direct')),
        (ADHESION, _('Memberships')),
        (CASHLESS, _('Cashless')),
        (BILLETTERIE, _('Ticketing')),
        (AVANCE, _('Advanced')),
    ]
    comportement = models.CharField(
        max_length=1, choices=COMPORTEMENT_CHOICES, default=DIRECT,
        verbose_name=_("POS type"),
        help_text=_(
            "Determines how articles are loaded. "
            "Direct: M2M only. Memberships: auto-loads membership products. "
            "Cashless: auto-loads top-ups. Ticketing: builds from future events. "
            "Advanced: restaurant order mode."
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

    # Imprimante pour les tickets de vente de ce point de vente
    # / Printer for sale tickets at this point of sale
    printer = models.ForeignKey(
        Printer, on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='points_de_vente',
        verbose_name=_("Ticket printer"),
        help_text=_("Printer used for sale tickets at this point of sale."),
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
    Rapport de cloture de caisse. GLOBAL au tenant (couvre tous les PV).
    Un rapport est cree a chaque fin de soiree/service.
    Les totaux sont en centimes (int).
    La ventilation par PV est dans rapport_json['ventilation_par_pv'].
    / Cash register closure report. GLOBAL to the tenant (covers all POS).
    A report is created at the end of each evening/service.
    All totals are in cents (int).
    Per-POS breakdown is in rapport_json['ventilation_par_pv'].

    LOCALISATION : laboutik/models.py
    """
    uuid = models.UUIDField(
        primary_key=True, default=uuid_module.uuid4, editable=False, unique=True, db_index=True,
    )

    # Point de vente depuis lequel la cloture a ete declenchee (informatif).
    # Nullable : la cloture couvre TOUT le tenant, pas un seul PV.
    # La ventilation par PV est dans rapport_json['ventilation_par_pv'].
    # / Point of sale from which the closure was triggered (informational).
    # Nullable: the closure covers the ENTIRE tenant, not a single POS.
    # Per-POS breakdown is in rapport_json['ventilation_par_pv'].
    point_de_vente = models.ForeignKey(
        PointDeVente, on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='clotures',
        verbose_name=_("Triggered from POS"),
        help_text=_(
            "Point de vente depuis lequel la cloture a ete declenchee (informatif). "
            "La cloture couvre tout le tenant. "
            "/ POS from which closure was triggered (informational). "
            "Closure covers the entire tenant."
        ),
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

    # Moment de la cloture (explicite, pas auto_now_add)
    # / Closure timestamp (explicit, not auto_now_add)
    datetime_cloture = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Closure datetime"),
        help_text=_("Moment of the closure. Set explicitly, not auto_now_add."),
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

    # --- Niveau de cloture (conformite LNE exigence 6) ---
    # J = journaliere (declenchee par le caissier)
    # M = mensuelle (automatique Celery Beat, agrege les J du mois)
    # A = annuelle (automatique Celery Beat, agrege les M de l'annee)
    # / Closure level (LNE compliance req. 6)
    JOURNALIERE = 'J'
    HEBDOMADAIRE = 'H'
    MENSUELLE = 'M'
    ANNUELLE = 'A'
    NIVEAU_CHOICES = [
        (JOURNALIERE, _('Daily')),
        (HEBDOMADAIRE, _('Weekly')),
        (MENSUELLE, _('Monthly')),
        (ANNUELLE, _('Annual')),
    ]
    niveau = models.CharField(
        max_length=1, choices=NIVEAU_CHOICES, default=JOURNALIERE,
        verbose_name=_("Closure level"),
        help_text=_(
            "J = journaliere (caissier), M = mensuelle (auto), A = annuelle (auto). "
            "/ J = daily (cashier), M = monthly (auto), A = annual (auto)."
        ),
    )

    # Numero sequentiel par niveau, sans trou (conformite LNE exigence 6)
    # Global au tenant — pas par PV (la cloture couvre tout le tenant).
    # / Sequential number per level, no gap (LNE compliance req. 6)
    # Global to the tenant — not per POS (closure covers the entire tenant).
    numero_sequentiel = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Sequential number"),
        help_text=_(
            "Numero sequentiel par niveau de cloture. Sans trou. Global au tenant. "
            "/ Sequential number per closure level. No gap. Global to tenant."
        ),
    )

    # Total perpetuel snapshot au moment de la cloture (conformite LNE exigence 7)
    # / Perpetual total snapshot at closure time (LNE compliance req. 7)
    total_perpetuel = models.IntegerField(
        default=0,
        verbose_name=_("Perpetual total (cents)"),
        help_text=_(
            "Total cumule depuis la mise en service, snapshot au moment de cette cloture. "
            "/ Cumulative total since first use, snapshot at this closure time."
        ),
    )

    # Hash SHA-256 des LigneArticle couvertes (filet de securite)
    # / SHA-256 hash of covered LigneArticle (safety net)
    hash_lignes = models.CharField(
        max_length=64, blank=True, default='',
        verbose_name=_("Lines integrity hash"),
        help_text=_(
            "SHA-256 des LigneArticle couvertes. Filet de securite. "
            "/ SHA-256 of covered LigneArticle. Safety net."
        ),
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


# --- Journal des impressions (conformite LNE exigence 9) ---
# Chaque impression physique ou electronique d'un justificatif est tracee.
# / Print audit log (LNE compliance req. 9).
# Every physical or electronic printing of a receipt is recorded.

class ImpressionLog(models.Model):
    """
    Journal d'audit des impressions de justificatifs (tickets de vente, clotures, billets).
    Chaque impression — y compris les duplicatas — est tracee de facon immutable.
    Requis par la certification LNE (exigence 9 : tracabilite des impressions).
    / Audit log for receipt printing (sale tickets, closures, event tickets).
    Every print — including duplicates — is recorded immutably.
    Required by LNE certification (req. 9: print traceability).

    LOCALISATION : laboutik/models.py
    """

    uuid = models.UUIDField(
        primary_key=True, default=uuid_module.uuid4, editable=False, unique=True, db_index=True,
    )

    # Horodatage de l'impression — pose automatiquement a la creation.
    # / Print timestamp — set automatically on creation.
    datetime = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Print datetime"),
    )

    # Ligne d'article imprimee (nullable : pour les clotures ou billets sans LigneArticle)
    # / Printed article line (nullable: for closures or tickets without a LigneArticle)
    ligne_article = models.ForeignKey(
        'BaseBillet.LigneArticle',
        on_delete=models.PROTECT,
        blank=True, null=True,
        related_name='impressions',
        verbose_name=_("Article line"),
        help_text=_(
            "Ligne d'article concernee par cette impression. "
            "Null pour les clotures et billets. "
            "/ Article line for this print. Null for closures and tickets."
        ),
    )

    # UUID de transaction — regroupe plusieurs lignes d'un meme ticket de vente.
    # Un ticket multi-articles peut couvrir N LigneArticle avec le meme uuid_transaction.
    # / Transaction UUID — groups multiple lines of the same sale receipt.
    # A multi-article receipt may cover N LigneArticle with the same uuid_transaction.
    uuid_transaction = models.UUIDField(
        blank=True, null=True, db_index=True,
        verbose_name=_("Transaction UUID"),
        help_text=_(
            "Identifiant de transaction pour regrouper les lignes d'un meme ticket. "
            "/ Transaction identifier to group lines of the same receipt."
        ),
    )

    # Cloture de caisse associee (uniquement pour les justificatifs de cloture)
    # / Associated cash register closure (only for closure receipts)
    cloture = models.ForeignKey(
        ClotureCaisse,
        on_delete=models.PROTECT,
        blank=True, null=True,
        related_name='impressions',
        verbose_name=_("Closure"),
        help_text=_(
            "Cloture de caisse concernee par cette impression. "
            "Null pour les tickets de vente et billets. "
            "/ Cash register closure for this print. Null for sale tickets and event tickets."
        ),
    )

    # Operateur qui a declenche l'impression (caissier connecte au moment de l'impression)
    # / Operator who triggered the print (cashier logged in at print time)
    operateur = models.ForeignKey(
        TibilletUser,
        on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='impressions',
        verbose_name=_("Operator"),
        help_text=_(
            "Caissier connecte au moment de l'impression. "
            "/ Cashier who triggered this print."
        ),
    )

    # Imprimante utilisee (peut etre nulle si impression electronique)
    # / Printer used (may be null for electronic receipts)
    printer = models.ForeignKey(
        Printer,
        on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='impressions',
        verbose_name=_("Printer"),
        help_text=_(
            "Imprimante physique utilisee pour cette impression. "
            "Null pour les emissions electroniques. "
            "/ Physical printer used for this print. Null for electronic receipts."
        ),
    )

    # Type de justificatif imprime
    # VENTE : ticket de vente (transaction POS)
    # CLOTURE : rapport de cloture de caisse
    # COMMANDE : bon de commande cuisine / bar
    # BILLET : billet d'entree evenement
    # / Type of receipt printed
    # VENTE: sale receipt (POS transaction)
    # CLOTURE: cash register closure report
    # COMMANDE: kitchen / bar order ticket
    # BILLET: event entry ticket
    VENTE = 'VENTE'
    CLOTURE = 'CLOT'
    COMMANDE = 'COMM'
    BILLET = 'BILL'
    TYPE_JUSTIFICATIF_CHOICES = [
        (VENTE, _('Sale receipt')),
        (CLOTURE, _('Closure report')),
        (COMMANDE, _('Order ticket')),
        (BILLET, _('Event ticket')),
    ]
    type_justificatif = models.CharField(
        max_length=10, choices=TYPE_JUSTIFICATIF_CHOICES, default=VENTE,
        verbose_name=_("Receipt type"),
        help_text=_(
            "Type de justificatif imprime : VENTE, CLOT, COMM ou BILL. "
            "/ Type of printed receipt: VENTE, CLOT, COMM or BILL."
        ),
    )

    # Duplicata : True si cette impression est une re-impression d'un justificatif deja emis.
    # Chaque duplicata doit etre mentionne sur le ticket (exigence LNE).
    # / Duplicate: True if this print is a re-print of an already-issued receipt.
    # Each duplicate must be mentioned on the ticket (LNE requirement).
    is_duplicata = models.BooleanField(
        default=False,
        verbose_name=_("Duplicate"),
        help_text=_(
            "Cocher si cette impression est un duplicata (re-impression). "
            "/ Check if this print is a duplicate (re-print)."
        ),
    )

    # Format d'emission : P = papier (imprimante thermique), E = electronique (email/PDF)
    # / Emission format: P = paper (thermal printer), E = electronic (email/PDF)
    PAPIER = 'P'
    ELECTRONIQUE = 'E'
    FORMAT_EMISSION_CHOICES = [
        (PAPIER, _('Paper')),
        (ELECTRONIQUE, _('Electronic')),
    ]
    format_emission = models.CharField(
        max_length=1, choices=FORMAT_EMISSION_CHOICES, default=PAPIER,
        verbose_name=_("Emission format"),
        help_text=_(
            "P = papier (imprimante thermique), E = electronique (email/PDF). "
            "/ P = paper (thermal printer), E = electronic (email/PDF)."
        ),
    )

    def __str__(self):
        duplicata_label = f" [{_('DUPLICATE')}]" if self.is_duplicata else ""
        return f"{self.get_type_justificatif_display()}{duplicata_label} — {self.datetime:%Y-%m-%d %H:%M}"

    class Meta:
        ordering = ('-datetime',)
        verbose_name = _('Print log')
        verbose_name_plural = _('Print logs')


# --- Correction de moyen de paiement ---
# Trace d'audit pour chaque correction de moyen de paiement sur une LigneArticle.
# Requis par la certification LNE (exigence 4 : pas de modification directe,
# seulement des operations tracees). Le HMAC chain est casse volontairement
# par la correction — ce modele sert de preuve pour distinguer une correction
# tracee d'une falsification (voir integrity.py verifier_chaine()).
# / Payment method correction audit trail.
# Required by LNE certification (req. 4: no direct modification,
# only traced operations). The HMAC chain is intentionally broken
# by the correction — this model serves as proof to distinguish
# a traced correction from tampering (see integrity.py verifier_chaine()).

class CorrectionPaiement(models.Model):
    """
    Trace d'audit immutable pour une correction de moyen de paiement.
    Chaque correction est enregistree avec l'ancien moyen, le nouveau moyen,
    la raison et l'operateur. Seules les corrections ESP <-> CB <-> CHQ sont
    autorisees. Les paiements NFC (cashless) ne peuvent pas etre corriges.
    / Immutable audit trail for a payment method correction.
    Only CASH <-> CC <-> CHECK corrections are allowed.
    NFC (cashless) payments cannot be corrected.

    LOCALISATION : laboutik/models.py
    """
    uuid = models.UUIDField(
        primary_key=True, default=uuid_module.uuid4, editable=False,
        unique=True, db_index=True,
    )

    # Ligne d'article concernee par la correction
    # / Article line affected by the correction
    ligne_article = models.ForeignKey(
        'BaseBillet.LigneArticle', on_delete=models.PROTECT,
        related_name='corrections',
        verbose_name=_("Article line"),
        help_text=_(
            "Ligne d'article dont le moyen de paiement a ete corrige. "
            "/ Article line whose payment method was corrected."
        ),
    )

    # Ancien moyen de paiement (code PaymentMethod, ex: 'CA', 'CC', 'CH')
    # / Previous payment method code
    ancien_moyen = models.CharField(
        max_length=10,
        verbose_name=_("Previous payment method"),
        help_text=_(
            "Code du moyen de paiement avant correction (ex: CA, CC, CH). "
            "/ Payment method code before correction."
        ),
    )

    # Nouveau moyen de paiement
    # / New payment method code
    nouveau_moyen = models.CharField(
        max_length=10,
        verbose_name=_("New payment method"),
        help_text=_(
            "Code du moyen de paiement apres correction. "
            "/ Payment method code after correction."
        ),
    )

    # Raison de la correction (obligatoire, conformite LNE)
    # / Correction reason (mandatory, LNE compliance)
    raison = models.TextField(
        verbose_name=_("Reason"),
        help_text=_(
            "Raison de la correction. Obligatoire pour la tracabilite. "
            "/ Correction reason. Mandatory for traceability."
        ),
    )

    # Operateur qui a effectue la correction
    # / Operator who performed the correction
    operateur = models.ForeignKey(
        TibilletUser, on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='corrections_paiement',
        verbose_name=_("Operator"),
        help_text=_(
            "Caissier qui a effectue la correction. "
            "/ Cashier who performed the correction."
        ),
    )

    # Horodatage de la correction
    # / Correction timestamp
    datetime = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Correction date"),
    )

    def __str__(self):
        return f"{self.ancien_moyen} → {self.nouveau_moyen} ({self.datetime:%Y-%m-%d %H:%M})"

    class Meta:
        ordering = ('-datetime',)
        verbose_name = _('Payment correction')
        verbose_name_plural = _('Payment corrections')


# --- Sortie de caisse (retrait especes) ---
# Enregistre chaque retrait d'especes du tiroir-caisse avec une ventilation
# detaillee par coupure (billets et pieces). Le total est recalcule cote
# serveur pour eviter toute manipulation.
# / Cash withdrawal record.
# Records each cash withdrawal from the register with a detailed
# breakdown by denomination (bills and coins). Total is recalculated
# server-side to prevent manipulation.

class SortieCaisse(models.Model):
    """
    Sortie de caisse : retrait d'especes avec ventilation par coupure.
    Le montant total est recalcule cote serveur (ne jamais faire confiance
    au total envoye par le client).
    / Cash withdrawal with breakdown by denomination.
    Total amount is recalculated server-side.

    LOCALISATION : laboutik/models.py
    """
    uuid = models.UUIDField(
        primary_key=True, default=uuid_module.uuid4, editable=False,
        unique=True, db_index=True,
    )

    # Point de vente depuis lequel le retrait est effectue
    # / Point of sale from which the withdrawal is made
    point_de_vente = models.ForeignKey(
        'laboutik.PointDeVente', on_delete=models.PROTECT,
        related_name='sorties_caisse',
        verbose_name=_("Point of sale"),
        help_text=_(
            "Point de vente depuis lequel le retrait d'especes est effectue. "
            "/ Point of sale from which cash is withdrawn."
        ),
    )

    # Operateur qui a effectue le retrait
    # / Operator who performed the withdrawal
    operateur = models.ForeignKey(
        TibilletUser, on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='sorties_caisse',
        verbose_name=_("Operator"),
        help_text=_(
            "Caissier qui a effectue le retrait d'especes. "
            "/ Cashier who performed the cash withdrawal."
        ),
    )

    # Horodatage du retrait
    # / Withdrawal timestamp
    datetime = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Withdrawal date"),
    )

    # Montant total retire en centimes (recalcule cote serveur)
    # / Total amount withdrawn in cents (recalculated server-side)
    montant_total = models.IntegerField(
        verbose_name=_("Total amount (cents)"),
        help_text=_(
            "Montant total retire en centimes. Recalcule cote serveur. "
            "/ Total withdrawn amount in cents. Recalculated server-side."
        ),
    )

    # Ventilation par coupure : cle = valeur de la coupure en centimes,
    # valeur = nombre de coupures de ce type.
    # Exemple : {"50000": 1, "20000": 2, "500": 3} = 1x500€ + 2x200€ + 3x5€
    # / Breakdown by denomination: key = denomination value in cents,
    # value = number of that denomination.
    ventilation = models.JSONField(
        default=dict,
        verbose_name=_("Denomination breakdown"),
        help_text=_(
            "Ventilation par coupure. Cle = valeur en centimes, valeur = quantite. "
            "/ Denomination breakdown. Key = value in cents, value = quantity."
        ),
    )

    # Note libre (optionnelle)
    # / Optional note
    note = models.TextField(
        blank=True, default='',
        verbose_name=_("Note"),
        help_text=_(
            "Note libre sur le retrait d'especes. "
            "/ Optional note about the cash withdrawal."
        ),
    )

    def __str__(self):
        montant_euros = self.montant_total / 100
        return f"{montant_euros:.2f} € ({self.datetime:%Y-%m-%d %H:%M})"

    class Meta:
        ordering = ('-datetime',)
        verbose_name = _('Cash withdrawal')
        verbose_name_plural = _('Cash withdrawals')
