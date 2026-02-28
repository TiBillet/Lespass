"""
fedow_core/models.py — Moteur de portefeuille et de transactions cashless.
fedow_core/models.py — Cashless wallet and transaction engine.

Cette app remplace le serveur Fedow standalone (OLD_REPOS/Fedow).
Elle vit dans SHARED_APPS (schema public PostgreSQL) pour permettre
les requetes cross-tenant (un utilisateur peut avoir des tokens
sur plusieurs lieux differents).

This app replaces the standalone Fedow server (OLD_REPOS/Fedow).
It lives in SHARED_APPS (PostgreSQL public schema) to allow
cross-tenant queries (a user can have tokens across multiple places).

REGLE CRITIQUE : toujours filtrer par tenant dans les vues tenant-scoped.
Ne jamais faire Asset.objects.all() nu dans une vue.
CRITICAL RULE: always filter by tenant in tenant-scoped views.
Never do bare Asset.objects.all() in a view.

Toutes les valeurs monetaires sont en CENTIMES (int).
All monetary values are in CENTIMES (int).
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from AuthBillet.models import Wallet
from Customers.models import Client
from QrcodeCashless.models import CarteCashless


# ---------------------------------------------------------------------------
# Asset : une monnaie ou un type de token
# Asset: a currency or a type of token
# ---------------------------------------------------------------------------

class Asset(models.Model):
    """
    Un Asset represente une monnaie ou un type de token dans le systeme.
    An Asset represents a currency or a type of token in the system.

    Exemples concrets / Concrete examples:
    - "Monnaie locale Reunion" (TLF) — adossee a l'euro, 1 token = 1 centime EUR
    - "Bon cadeau festival" (TNF) — offert, pas echangeable contre des euros
    - "TiBillet federee" (FED) — la monnaie Stripe partagee entre tous les lieux
    - "Heures benevole" (TIM) — compteur de temps de benevolat
    - "Points fidelite" (FID) — programme de fidelite d'un lieu

    Chaque Asset appartient a un tenant createur (tenant_origin) et a un
    wallet createur (wallet_origin). Un Asset peut etre partage entre
    plusieurs tenants via une Federation (cf. modele Federation).

    Each Asset belongs to a creator tenant (tenant_origin) and a creator
    wallet (wallet_origin). An Asset can be shared across multiple tenants
    via a Federation (see Federation model).
    """

    # --- Categories d'asset (v2) ---
    # --- Asset categories (v2) ---
    # BDG (badgeuse) et SUB (adhesion) ont ete retires.
    # Les adhesions sont gerees par BaseBillet.Membership.
    # BDG (badge) and SUB (subscription) were removed.
    # Subscriptions are handled by BaseBillet.Membership.
    TLF = 'TLF'  # Token Local Fiduciaire / Local Fiduciary Token
    TNF = 'TNF'   # Token Local Non-Fiduciaire / Local Non-Fiduciary Token
    FED = 'FED'   # Fiduciaire Federee / Federated Fiduciary
    TIM = 'TIM'   # Monnaie Temps / Time Currency
    FID = 'FID'   # Points de Fidelite / Loyalty Points

    CATEGORY_CHOICES = [
        # Monnaie locale adossee a l'euro. 1 token = 1 centime EUR.
        # Le lieu peut rembourser les tokens en euros (depot bancaire).
        # Local currency backed by EUR. 1 token = 1 EUR cent.
        # The venue can refund tokens in euros (bank deposit).
        (TLF, _('Token local fiduciaire')),

        # Token cadeau, bon d'achat. Pas echangeable contre des euros.
        # Utile pour les offres promotionnelles ou les dons.
        # Gift token, voucher. Not redeemable for euros.
        # Useful for promotional offers or donations.
        (TNF, _('Token local cadeau')),

        # Monnaie federee unique dans le systeme (geree via Stripe).
        # Partagee entre tous les lieux TiBillet. Un seul Asset FED existe.
        # System-wide federated currency (managed via Stripe).
        # Shared across all TiBillet venues. Only one FED Asset exists.
        (FED, _('Fiduciaire federee')),

        # Compteur de temps (heures de benevolat, temps partage, etc.)
        # Pas de valeur monetaire, sert de compteur.
        # Time counter (volunteer hours, shared time, etc.)
        # No monetary value, used as a counter.
        (TIM, _('Monnaie temps')),

        # Points de fidelite d'un lieu. Pas de valeur monetaire.
        # Loyalty points for a venue. No monetary value.
        (FID, _('Points de fidelite')),
    ]

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # Nom lisible de l'asset, affiche dans l'interface.
    # Human-readable asset name, displayed in the UI.
    name = models.CharField(
        max_length=100,
        verbose_name=_("Nom de l'asset"),
    )

    # Code devise sur 3 caracteres (norme ISO 4217 ou code libre).
    # Exemples : "EUR" pour TLF/FED, "TMP" pour TIM, "PTS" pour FID.
    # 3-character currency code (ISO 4217 standard or custom code).
    # Examples: "EUR" for TLF/FED, "TMP" for TIM, "PTS" for FID.
    currency_code = models.CharField(
        max_length=3,
        verbose_name=_('Code devise'),
        help_text=_('Code devise sur 3 caracteres : EUR, TMP, PTS, etc.'),
    )

    category = models.CharField(
        max_length=3,
        choices=CATEGORY_CHOICES,
        verbose_name=_("Categorie"),
    )

    # Le wallet du lieu ou de la personne qui a cree cet asset.
    # Pour un TLF, c'est le wallet du lieu. Pour un FED, c'est le wallet root.
    # The wallet of the venue or person who created this asset.
    # For a TLF, it's the venue's wallet. For FED, it's the root wallet.
    wallet_origin = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name='fedow_core_assets',
        verbose_name=_('Wallet createur'),
        help_text=_('Wallet du lieu ou de la personne qui a cree cet asset'),
    )

    # Le tenant (lieu/organisation) qui a cree cet asset.
    # IMPORTANT : en SHARED_APPS, ce champ sert de filtre principal.
    # The tenant (venue/organization) that created this asset.
    # IMPORTANT: in SHARED_APPS, this field is the primary filter.
    tenant_origin = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name='assets',
        verbose_name=_('Tenant createur'),
        help_text=_('Lieu ou organisation qui a cree cet asset'),
    )

    # Est-ce que cet asset est utilisable pour des transactions ?
    # Un asset inactif ne peut pas etre utilise pour payer.
    # Is this asset usable for transactions?
    # An inactive asset cannot be used to pay.
    active = models.BooleanField(
        default=True,
        verbose_name=_('Actif'),
    )

    # Est-ce que cet asset est archive (masque de l'interface) ?
    # Difference avec active : archive = masque, active = bloque.
    # Is this asset archived (hidden from the UI)?
    # Difference with active: archived = hidden, active = blocked.
    archive = models.BooleanField(
        default=False,
        verbose_name=_('Archive'),
    )

    # Identifiant Stripe du Price pour les recharges en ligne.
    # Utilise uniquement par les assets de categorie FED.
    # Stripe Price ID for online top-ups.
    # Only used by assets with category FED.
    id_price_stripe = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_('Stripe Price ID'),
        help_text=_('Identifiant Stripe du Price pour recharge (categorie FED uniquement)'),
    )

    # Lieux invites a partager cet asset (en attente d'acceptation).
    # Le createur invite d'autres lieux ; ils voient l'invitation
    # dans leur admin et cliquent "Accepter".
    # Venues invited to share this asset (pending acceptance).
    # The creator invites other venues; they see the invitation
    # in their admin and click "Accept".
    pending_invitations = models.ManyToManyField(
        Client,
        related_name='asset_invitations_pending',
        blank=True,
        verbose_name=_('Invitations en attente'),
        help_text=_("Lieux invites a partager cet asset. "
                     "Ils verront l'invitation dans leur admin et pourront accepter."),
    )

    # Lieux qui ont accepte de partager cet asset.
    # Quand un lieu accepte, il est deplace de pending_invitations vers federated_with.
    # Venues that accepted to share this asset.
    # When a venue accepts, it is moved from pending_invitations to federated_with.
    federated_with = models.ManyToManyField(
        Client,
        related_name='assets_federated',
        blank=True,
        verbose_name=_('Lieux federes'),
        help_text=_("Lieux qui ont accepte de partager cet asset."),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    last_update = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Asset')
        verbose_name_plural = _('Assets')

    def __str__(self):
        return f'{self.name} ({self.get_category_display()})'


# ---------------------------------------------------------------------------
# Token : le solde d'un wallet pour un asset donne
# Token: a wallet's balance for a given asset
# ---------------------------------------------------------------------------

class Token(models.Model):
    """
    Un Token represente le solde d'un wallet pour un asset donne.
    A Token represents a wallet's balance for a given asset.

    C'est LE modele qui repond a la question :
    "Combien cette personne a-t-elle sur sa carte pour cette monnaie ?"
    This is THE model that answers the question:
    "How much does this person have on their card for this currency?"

    Exemple / Example:
        Token(wallet=alice.wallet, asset=monnaie_locale, value=1500)
        → Alice a 15,00 EUR en monnaie locale (1500 centimes)
        → Alice has 15.00 EUR in local currency (1500 cents)

    Pour obtenir tous les soldes d'un utilisateur (tous les lieux) :
    To get all balances for a user (all venues):
        Token.objects.filter(wallet=user.wallet)

    Contrainte : un seul Token par couple (wallet, asset).
    Si Alice a de la monnaie locale ET des points fidelite,
    elle a 2 Token distincts.
    Constraint: only one Token per (wallet, asset) pair.
    If Alice has local currency AND loyalty points,
    she has 2 distinct Tokens.

    Toutes les valeurs sont en CENTIMES (int). 1500 = 15,00 EUR.
    All values are in CENTS (int). 1500 = 15.00 EUR.
    """

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # Le wallet qui possede ce solde.
    # The wallet that owns this balance.
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name='tokens',
        verbose_name=_('Wallet'),
    )

    # L'asset (monnaie/token) concerne.
    # The asset (currency/token) this balance is for.
    asset = models.ForeignKey(
        Asset,
        on_delete=models.PROTECT,
        related_name='tokens',
        verbose_name=_('Asset'),
    )

    # Le solde en centimes. Peut etre negatif dans certains cas
    # (ex: dette temporaire avant regularisation).
    # Balance in cents. Can be negative in some cases
    # (e.g. temporary debt before regularization).
    value = models.IntegerField(
        default=0,
        verbose_name=_('Solde'),
        help_text=_('Solde en centimes. 1500 = 15,00 EUR.'),
    )

    class Meta:
        verbose_name = _('Token')
        verbose_name_plural = _('Tokens')
        constraints = [
            # Un seul Token par couple (wallet, asset).
            # Only one Token per (wallet, asset) pair.
            models.UniqueConstraint(
                fields=['wallet', 'asset'],
                name='unique_token_per_wallet_asset',
            ),
        ]

    def __str__(self):
        return f'{self.wallet} / {self.asset.name} : {self.value}'


# ---------------------------------------------------------------------------
# Transaction : historique immuable des mouvements financiers
# Transaction: immutable history of financial movements
# ---------------------------------------------------------------------------

class Transaction(models.Model):
    """
    Une Transaction enregistre un mouvement financier entre deux wallets.
    A Transaction records a financial movement between two wallets.

    C'est le modele le plus critique du systeme. Il est IMMUABLE :
    une fois creee, une transaction ne doit jamais etre modifiee.
    Pour annuler, on cree une nouvelle transaction de type REFUND ou VOID.
    This is the most critical model in the system. It is IMMUTABLE:
    once created, a transaction must never be modified.
    To cancel, create a new REFUND or VOID transaction.

    Exemple concret / Concrete example:
        Transaction(
            sender=alice.wallet,        ← qui paye / who pays
            receiver=bar.wallet,        ← qui recoit / who receives
            asset=monnaie_locale,       ← quelle monnaie / which currency
            amount=350,                 ← 3,50 EUR (en centimes / in cents)
            action=Transaction.SALE,    ← type de mouvement / movement type
            card=alice_carte,           ← carte NFC utilisee / NFC card used
            tenant=festival_tenant,     ← dans quel lieu / at which venue
        )

    Integrite des donnees / Data integrity:
    - id : BigAutoField, cle primaire auto-incrementee par Django/PostgreSQL.
      Sert aussi de numero de reference humainement lisible sur les tickets.
    - uuid : identifiant unique conserve pour les imports depuis l'ancien Fedow.
      On peut toujours chercher une transaction par UUID :
      Transaction.objects.get(uuid=ancien_uuid)
    - hash : SHA256 individuel de la transaction (pas de chaine).
      Nullable pendant les Phases 1-2, NOT NULL apres Phase 3.
    - id: BigAutoField, auto-incremented primary key by Django/PostgreSQL.
      Also serves as human-readable reference number on receipts.
    - uuid: unique identifier preserved for imports from the old Fedow.
      You can still look up a transaction by UUID:
      Transaction.objects.get(uuid=old_uuid)
    - hash: individual SHA256 of the transaction (no chain).
      Nullable during Phases 1-2, NOT NULL after Phase 3.
    """

    # --- Les 10 actions de transaction (v2) ---
    # --- The 10 transaction actions (v2) ---
    #
    # BDG (badgeuse) et SUB (adhesion) ont ete retires de l'ancien Fedow.
    # Les adhesions sont desormais gerees par BaseBillet.Membership.
    # BDG (badge) and SUB (subscription) were removed from the old Fedow.
    # Subscriptions are now handled by BaseBillet.Membership.

    FIRST = 'FST'         # Genesis : premier bloc par asset (creation unique)
    CREATION = 'CRE'      # Creation de tokens (lieu → lieu, ou via Stripe)
    REFILL = 'RFL'        # Recharge d'un wallet (lieu → utilisateur, via Stripe)
    SALE = 'SAL'          # Vente cashless (utilisateur → lieu, paiement NFC)
    QRCODE_SALE = 'QRS'   # Vente par QR code (utilisateur → lieu, scan QR)
    FUSION = 'FUS'        # Fusion de wallet ephemere → wallet utilisateur
    REFUND = 'RFD'        # Remboursement (lieu → utilisateur, annulation)
    VOID = 'VOI'          # Vidage de carte (tout remettre a zero)
    DEPOSIT = 'DEP'       # Depot bancaire (lieu → wallet primaire, retrait)
    TRANSFER = 'TRF'      # Virement direct entre wallets

    ACTION_CHOICES = [
        (FIRST, _('Genesis')),
        (CREATION, _('Creation')),
        (REFILL, _('Recharge')),
        (SALE, _('Vente')),
        (QRCODE_SALE, _('Vente QR')),
        (FUSION, _('Fusion')),
        (REFUND, _('Remboursement')),
        (VOID, _('Annulation')),
        (DEPOSIT, _('Depot bancaire')),
        (TRANSFER, _('Virement')),
    ]

    # --- Cle primaire ---

    # BigAutoField : auto-increment natif Django/PostgreSQL.
    # Sert de numero de reference humainement lisible (ex: ticket #12345).
    # Pas besoin de sequence PostgreSQL manuelle, Django gere tout seul.
    # BigAutoField: native Django/PostgreSQL auto-increment.
    # Serves as human-readable reference number (e.g. ticket #12345).
    # No need for manual PostgreSQL sequence, Django handles it natively.
    id = models.BigAutoField(primary_key=True)

    # UUID conserve pour les imports de l'ancien Fedow.
    # On peut chercher une transaction par UUID :
    #   Transaction.objects.get(uuid=ancien_uuid)
    # UUID preserved for imports from the old Fedow.
    # You can look up a transaction by UUID:
    #   Transaction.objects.get(uuid=old_uuid)
    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name=_('UUID'),
        help_text=_('Identifiant unique conserve pour les imports depuis l\'ancien Fedow'),
    )

    # --- Hash d'integrite ---

    # Hash SHA256 individuel de cette transaction (pas de chaine de hash).
    # Sert de checksum pour verifier que la transaction n'a pas ete alteree.
    # Nullable pendant les phases de migration :
    #   Phase 1 (import) : hash=null, migrated=True
    #   Phase 2 (production) : hash=null, migrated=False
    #   Phase 3 (consolidation) : recalcul via management command, puis NOT NULL
    #
    # Individual SHA256 hash of this transaction (no hash chain).
    # Serves as checksum to verify the transaction has not been tampered with.
    # Nullable during migration phases:
    #   Phase 1 (import): hash=null, migrated=True
    #   Phase 2 (production): hash=null, migrated=False
    #   Phase 3 (consolidation): recalculated via management command, then NOT NULL
    hash = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        verbose_name=_('Hash SHA256'),
    )

    # Marqueur pour les transactions importees de l'ancien serveur Fedow.
    # Permet de distinguer les anciennes transactions (migrees) des nouvelles.
    # Marker for transactions imported from the old Fedow server.
    # Allows distinguishing old (migrated) transactions from new ones.
    migrated = models.BooleanField(
        default=False,
        verbose_name=_('Transaction migree'),
    )

    # --- Acteurs de la transaction ---

    # Qui paye (debite). Toujours renseigne.
    # Who pays (debited). Always set.
    sender = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name='transactions_sent',
        verbose_name=_('Emetteur'),
        help_text=_('Wallet debite (qui paye)'),
    )

    # Qui recoit (credite). Nullable pour certaines actions
    # comme VOID (vidage de carte) ou REFUND (remboursement).
    # Who receives (credited). Nullable for some actions
    # like VOID (card wipe) or REFUND (refund).
    receiver = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name='transactions_received',
        null=True,
        blank=True,
        verbose_name=_('Destinataire'),
        help_text=_('Wallet credite (qui recoit). Nullable pour VOID/REFUND.'),
    )

    # Quel asset (monnaie/token) est concerne par cette transaction.
    # Which asset (currency/token) is involved in this transaction.
    asset = models.ForeignKey(
        Asset,
        on_delete=models.PROTECT,
        related_name='transactions',
        verbose_name=_('Asset'),
    )

    # --- Montant et type ---

    # Montant en centimes. Toujours positif (PositiveIntegerField).
    # Le sens du mouvement est donne par l'action (SALE = debit sender,
    # REFILL = credit receiver, etc.)
    # Amount in cents. Always positive (PositiveIntegerField).
    # The direction is given by the action (SALE = debit sender,
    # REFILL = credit receiver, etc.)
    amount = models.PositiveIntegerField(
        verbose_name=_('Montant'),
        help_text=_('Montant en centimes. 350 = 3,50 EUR.'),
    )

    # Type de mouvement. Determine le sens du debit/credit.
    # Movement type. Determines the debit/credit direction.
    action = models.CharField(
        max_length=3,
        choices=ACTION_CHOICES,
        verbose_name=_('Action'),
    )

    # --- Carte cashless ---

    # La carte NFC utilisee pour cette transaction (si paiement cashless).
    # Nullable : pas de carte pour les recharges en ligne (Stripe).
    # The NFC card used for this transaction (if cashless payment).
    # Nullable: no card for online top-ups (Stripe).
    card = models.ForeignKey(
        CarteCashless,
        on_delete=models.PROTECT,
        related_name='transactions',
        null=True,
        blank=True,
        verbose_name=_('Carte cashless'),
        help_text=_('Carte NFC utilisee pour cette transaction'),
    )

    # La carte maitresse du point de vente qui a effectue la transaction.
    # Permet de tracer quel terminal/caissier a fait l'operation.
    # The primary card of the point of sale that performed the transaction.
    # Allows tracing which terminal/cashier did the operation.
    primary_card = models.ForeignKey(
        CarteCashless,
        on_delete=models.PROTECT,
        related_name='transactions_as_primary',
        null=True,
        blank=True,
        verbose_name=_('Carte maitresse'),
        help_text=_('Carte maitresse du point de vente (terminal/caissier)'),
    )

    # --- Horodatage et metadonnees ---

    # Date et heure de la transaction. Pas auto_now_add car on doit pouvoir
    # importer des transactions historiques avec leur date d'origine.
    # Date and time of the transaction. Not auto_now_add because we need
    # to import historical transactions with their original date.
    datetime = models.DateTimeField(
        verbose_name=_('Date et heure'),
    )

    # Commentaire libre. Utilise pour les notes de caisse, motifs de
    # remboursement, etc.
    # Free-form comment. Used for register notes, refund reasons, etc.
    comment = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Commentaire'),
    )

    # Donnees supplementaires au format JSON. Utilise pour stocker
    # des informations specifiques sans ajouter de colonnes.
    # Additional data in JSON format. Used to store specific
    # information without adding columns.
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('Metadonnees'),
    )

    # --- Champs legacy (conserves pour import) ---

    # Type d'abonnement. L'action SUBSCRIBE a ete retiree (les adhesions
    # sont maintenant dans BaseBillet.Membership), mais ce champ est
    # conserve pour pouvoir importer les anciennes transactions.
    # Subscription type. The SUBSCRIBE action was removed (subscriptions
    # are now in BaseBillet.Membership), but this field is kept
    # to import old transactions.
    subscription_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name=_("Type d'abonnement (legacy)"),
    )
    subscription_start_datetime = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Debut d'abonnement (legacy)"),
    )

    # --- Lien Stripe ---

    # UUID du Paiement_stripe associe (dans BaseBillet, app TENANT).
    # C'est un UUIDField et non une ForeignKey car :
    # 1. Paiement_stripe est en TENANT_APPS (schema par tenant)
    # 2. fedow_core est en SHARED_APPS (schema public)
    # 3. Une FK du schema public vers un schema tenant est impossible
    # 4. Certains paiements (recharges en monnaie federee TiBillet)
    #    ne sont pas stockes dans un tenant specifique.
    #
    # UUID of the associated Paiement_stripe (in BaseBillet, TENANT app).
    # This is a UUIDField, not a ForeignKey, because:
    # 1. Paiement_stripe is in TENANT_APPS (per-tenant schema)
    # 2. fedow_core is in SHARED_APPS (public schema)
    # 3. A FK from public schema to a tenant schema is not possible
    # 4. Some payments (federated TiBillet currency refills)
    #    are not stored in any specific tenant.
    checkout_stripe = models.UUIDField(
        null=True,
        blank=True,
        verbose_name=_('Paiement Stripe'),
        help_text=_('UUID du Paiement_stripe associe (pas de FK cross-schema)'),
    )

    # --- Tenant ---

    # Le tenant (lieu/organisation) concerne par cette transaction.
    # REGLE CRITIQUE : toujours filtrer par ce champ dans les vues.
    # fedow_core est en SHARED_APPS, donc il n'y a PAS d'isolation
    # automatique par schema. Sans filtre, on voit les transactions
    # de TOUS les lieux.
    #
    # The tenant (venue/organization) concerned by this transaction.
    # CRITICAL RULE: always filter by this field in views.
    # fedow_core is in SHARED_APPS, so there is NO automatic
    # schema isolation. Without filter, you see transactions
    # from ALL venues.
    tenant = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name='fedow_transactions',
        verbose_name=_('Tenant'),
        help_text=_('Lieu concerne — TOUJOURS filtrer par ce champ dans les vues'),
    )

    # Adresse IP de la requete qui a cree cette transaction.
    # IP address of the request that created this transaction.
    ip = models.GenericIPAddressField(
        default='0.0.0.0',
        verbose_name=_('Adresse IP'),
    )

    class Meta:
        verbose_name = _('Transaction')
        verbose_name_plural = _('Transactions')
        ordering = ['id']
        indexes = [
            # Index composite tenant + datetime : la requete la plus frequente
            # est "toutes les transactions de ce lieu, triees par date".
            # Composite index tenant + datetime: the most frequent query
            # is "all transactions for this venue, sorted by date".
            models.Index(fields=['tenant', 'datetime']),
            models.Index(fields=['sender', 'datetime']),
            models.Index(fields=['receiver', 'datetime']),
            models.Index(fields=['asset', 'datetime']),
            models.Index(fields=['action']),
        ]

    def __str__(self):
        return f'#{self.id} {self.get_action_display()} {self.amount}'


# ---------------------------------------------------------------------------
# Federation : partage d'assets entre plusieurs tenants (lieux)
# Federation: sharing assets across multiple tenants (venues)
# ---------------------------------------------------------------------------

class Federation(models.Model):
    """
    Une Federation regroupe plusieurs tenants (lieux) qui partagent
    des assets (monnaies/tokens). Cela permet le cashless cross-lieu :
    une carte chargee au lieu A peut payer au lieu B si les deux lieux
    sont dans la meme Federation pour le meme Asset.

    A Federation groups multiple tenants (venues) that share
    assets (currencies/tokens). This enables cross-venue cashless:
    a card loaded at venue A can pay at venue B if both venues
    are in the same Federation for the same Asset.

    Flow d'invitation / Invitation flow:
        1. Le createur (created_by) cree la federation et ajoute ses assets.
           The creator (created_by) creates the federation and adds assets.
        2. Il invite d'autres lieux via pending_tenants (M2M).
           They invite other venues via pending_tenants (M2M).
        3. Le lieu invite voit l'invitation dans son admin et clique "Accepter".
           The invited venue sees the invitation in their admin and clicks "Accept".
        4. Le lieu est deplace de pending_tenants vers tenants.
           The venue is moved from pending_tenants to tenants.

    Exemple concret / Concrete example:
        federation = Federation(name="Reseau monnaie locale Reunion")
        federation.tenants.add(bar_a, bar_b, restaurant_c)
        federation.assets.add(monnaie_locale_reunion)
        → Les cartes chargees en "monnaie locale Reunion" fonctionnent
          dans les 3 lieux.
        → Cards loaded with "monnaie locale Reunion" work
          at all 3 venues.
    """

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # Nom unique de la federation, affiche dans l'admin.
    # Unique federation name, displayed in admin.
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_('Nom'),
    )

    # Description libre pour expliquer le but de cette federation.
    # Free-form description to explain the purpose of this federation.
    description = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Description'),
    )

    # Le tenant qui a cree cette federation. Lui seul peut inviter d'autres lieux.
    # The tenant that created this federation. Only they can invite other venues.
    created_by = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name='federations_created',
        verbose_name=_('Cree par'),
        help_text=_("Le lieu qui a cree cette federation. Lui seul peut envoyer des invitations."),
        null=True,
        blank=True,
    )

    # Les tenants (lieux) qui font partie de cette federation (ont accepte).
    # The tenants (venues) that are part of this federation (accepted).
    tenants = models.ManyToManyField(
        Client,
        related_name='federations',
        blank=True,
        verbose_name=_('Tenants membres'),
        help_text=_("Lieux qui ont accepte de rejoindre cette federation."),
    )

    # Les tenants invites mais qui n'ont pas encore accepte.
    # Invited tenants that have not yet accepted.
    pending_tenants = models.ManyToManyField(
        Client,
        related_name='federation_invitations_pending',
        blank=True,
        verbose_name=_('Invitations en attente'),
        help_text=_("Lieux invites a rejoindre cette federation. "
                     "Ils verront l'invitation dans leur admin et pourront accepter."),
    )

    # Les assets (monnaies/tokens) partages dans cette federation.
    # The assets (currencies/tokens) shared in this federation.
    assets = models.ManyToManyField(
        Asset,
        related_name='federations',
        blank=True,
        verbose_name=_('Assets partages'),
    )

    class Meta:
        verbose_name = _('Federation')
        verbose_name_plural = _('Federations')

    def __str__(self):
        return self.name
