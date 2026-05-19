# SPEC — Clôture comptable V1 (Chantier 01 de l'app `comptabilite`)

> Cette spec décrit comment porter la fonctionnalité « clôture caisse »
> de la V2 (lespass-main/laboutik) vers la V1 (Lespass), en restreignant
> le périmètre aux **réservations d'événements** et aux **adhésions**
> (pas de POS, pas de Fedow, pas de cartes NFC).
>
> Référence d'inspiration : `/home/jonas/TiBillet/dev/lespass-main/laboutik/`
> Hub documentaire : [`INDEX.md`](INDEX.md)

---

## 1. Vue d'ensemble fonctionnelle

### 1.1 Ce qu'on construit

Une page admin Django Unfold accessible via la sidebar à
`/admin/comptabilite/cloturecaisse/`, qui :

- Liste toutes les clôtures (J/H/M/A) avec leur numéro séquentiel,
  date, total TTC.
- Affiche le détail d'une clôture sous forme de rapport visuel
  (sections agrégées : ventes, TVA, adhésions, billets, remboursements,
  synthèse, infos légales).
- Propose 4 boutons d'export téléchargeables : **CSV**, **Excel
  (openpyxl)**, **PDF (WeasyPrint)**, **FEC** (Fichier des Écritures
  Comptables — format français 18 colonnes), **CSV comptable** (avec
  choix d'un profil : Sage 50 ou EBP).
- Génère automatiquement chaque jour à 6h locale une clôture
  quotidienne pour chaque tenant actif (`module_billetterie` ou
  `module_adhesion` activé sur `Configuration`).
- Génère également des clôtures hebdomadaires (lundi 6h), mensuelles
  (1er du mois 6h), annuelles (1er janvier 6h) — agrégeant
  respectivement les clôtures journalières de la période.
- Envoie par email (si configuré) un rapport périodique aux adresses
  saisies dans la configuration du tenant.

### 1.2 Ce qu'on ne construit PAS

- Aucun lien avec un point de vente physique
- Aucun calcul de fond de caisse (espèces)
- Aucune statistique liée aux cartes NFC ou aux wallets Fedow
- Aucune trace d'impression thermique (ImpressionLog non porté)
- Aucune intégration LaBoutik (l'app sera portée en dernier, plus tard)

### 1.3 Public cible

L'utilisateur final est :
- Un responsable association / lieu qui veut son rapport comptable
  mensuel pour son comptable (CSV ou FEC)
- Un trésorier qui veut un récap quotidien des recettes en ligne
  (Stripe) et hors-ligne (virements, espèces, chèques, paiement à la
  porte)
- Un auditeur qui veut un historique numéroté et auditable des
  recettes

---

## 2. Modèle de données

### 2.1 `comptabilite/models.py` — modèle `ClotureCaisse`

```python
import uuid as uuid_lib
from django.db import models
from django.utils.translation import gettext_lazy as _

class ClotureCaisse(models.Model):
    """
    Justificatif immuable de clôture comptable d'un tenant.
    / Immutable accounting closure justification for a tenant.

    LOCALISATION : comptabilite/models.py

    Une clôture est un instantané agrégé des ventes (réservations + adhésions)
    sur une période fermée [datetime_debut, datetime_fin]. Elle stocke un dict
    complet (rapport_json) qui permet de regénérer tout le PDF/Excel/CSV/FEC
    sans recalculer depuis les LigneArticle.

    Le numero_sequentiel est CONTINU GLOBAL par tenant : toutes les clôtures
    (J + H + M + A) partagent le même compteur incrémental.
    Conformité LNE V2 préservée.
    """

    NIVEAU_JOURNALIER = 'J'
    NIVEAU_HEBDOMADAIRE = 'H'
    NIVEAU_MENSUEL = 'M'
    NIVEAU_ANNUEL = 'A'
    NIVEAU_CHOICES = [
        (NIVEAU_JOURNALIER, _("Daily")),
        (NIVEAU_HEBDOMADAIRE, _("Weekly")),
        (NIVEAU_MENSUEL, _("Monthly")),
        (NIVEAU_ANNUEL, _("Yearly")),
    ]

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid_lib.uuid4,
        editable=False,
    )

    niveau = models.CharField(
        max_length=1,
        choices=NIVEAU_CHOICES,
        default=NIVEAU_JOURNALIER,
        verbose_name=_("Periodicity"),
        help_text=_(
            "Daily closure aggregates one day. "
            "Weekly/monthly/yearly aggregate the matching daily closures."
        ),
    )

    numero_sequentiel = models.PositiveIntegerField(
        unique=True,  # global par tenant (1 schéma = 1 table = unicité tenant)
        verbose_name=_("Sequential number"),
        help_text=_(
            "Continuous global counter per tenant (LNE compliance). "
            "Shared across all periodicities (daily, weekly, monthly, yearly). "
            "Used to detect gaps and prove the closure log integrity."
        ),
    )

    datetime_debut = models.DateTimeField(
        verbose_name=_("Period start"),
    )

    datetime_fin = models.DateTimeField(
        verbose_name=_("Period end"),
    )

    responsable = models.ForeignKey(
        "AuthBillet.TibilletUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clotures_caisse",
        verbose_name=_("Operator"),
        help_text=_("User who triggered a manual closure. Null if Celery auto."),
    )

    total_general = models.IntegerField(
        default=0,
        verbose_name=_("Total TTC (cents)"),
    )
    total_ht = models.IntegerField(
        default=0,
        verbose_name=_("Total HT (cents)"),
    )
    total_tva = models.IntegerField(
        default=0,
        verbose_name=_("Total VAT (cents)"),
    )

    nombre_transactions = models.IntegerField(
        default=0,
        verbose_name=_("Number of transactions"),
    )

    total_perpetuel = models.IntegerField(
        default=0,
        verbose_name=_("Perpetual total (cents)"),
        help_text=_(
            "Sum of total_general of all daily closures since tenant creation. "
            "Safety check against retroactive modification."
        ),
    )

    hash_lignes = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Lines hash"),
        help_text=_(
            "SHA-256 of sorted (uuid, amount, qty, status) tuples of every "
            "LigneArticle covered. Changes if any line is altered post-closure."
        ),
    )

    rapport_json = models.JSONField(
        default=dict,
        verbose_name=_("Report payload"),
        help_text=_(
            "Full report sections (totals by payment method, sales by category, "
            "VAT breakdown, memberships, tickets, refunds, synthesis, legal info)."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-datetime_fin", "-numero_sequentiel"]
        verbose_name = _("Cash closure")
        verbose_name_plural = _("Cash closures")
        indexes = [
            models.Index(fields=["niveau", "-datetime_fin"]),
            models.Index(fields=["-numero_sequentiel"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["niveau", "datetime_debut", "datetime_fin"],
                name="unique_cloture_periode",
            ),
            # numero_sequentiel est déjà unique=True au niveau du champ.
            # / numero_sequentiel is already unique=True at the field level.
        ]

    def __str__(self):
        return f"{self.get_niveau_display()} #{self.numero_sequentiel} — {self.datetime_fin:%Y-%m-%d}"
```

### 2.2 Modification mineure de `BaseBillet.Configuration`

Ajout de **2 champs** (migration AddField) :

```python
# Dans BaseBillet/models.py, dans la classe Configuration

rapport_emails = models.TextField(
    blank=True,
    default="",
    verbose_name=_("Recipient emails for closure reports"),
    help_text=_(
        "Comma-separated emails. Leave empty to disable automatic sending."
    ),
)

PERIODICITE_NONE = 'NONE'
PERIODICITE_CHOICES = [
    (PERIODICITE_NONE, _("No email")),
    ('J', _("Daily")),
    ('H', _("Weekly")),
    ('M', _("Monthly")),
    ('A', _("Yearly")),
]
rapport_periodicite = models.CharField(
    max_length=4,
    choices=PERIODICITE_CHOICES,
    default=PERIODICITE_NONE,
    verbose_name=_("Closure report sending frequency"),
)
```

### 2.3 Aucune modification de `LigneArticle`

La feature lit les `LigneArticle` existantes via `RapportComptableService`.
Aucun champ n'est ajouté. Aucun signal n'est branché.

### 2.4 Modèles comptables paramétrables (S5)

Portés depuis V2 (`laboutik.CompteComptable`, `laboutik.MappingMoyenDePaiement`).
Permettent à chaque tenant de **modifier son plan comptable** (numéros de
comptes Sage/EBP/Paheko) sans recompiler le code.

#### 2.4.1 `CompteComptable`

```python
class CompteComptable(models.Model):
    """
    Compte comptable utilisé pour la ventilation des écritures.
    / Accounting account used to dispatch entries.

    LOCALISATION : comptabilite/models.py

    Permet au tenant de mapper ses ventes / TVA / encaissements à des
    numéros de comptes précis selon son plan comptable. Les seeds par
    défaut correspondent au plan comptable général français.
    """

    TYPE_VENTE = 'V'              # 706 prestations / 707 ventes / 756 cotisations
    TYPE_TVA = 'T'                # 4457X TVA collectée
    TYPE_TRESORERIE = 'B'         # 512 banque / 530 caisse / 511 chèque
    TYPE_CLIENT = 'C'             # 411 clients
    TYPE_AUTRE = 'X'

    TYPE_CHOICES = [
        (TYPE_VENTE, _("Sales")),
        (TYPE_TVA, _("VAT collected")),
        (TYPE_TRESORERIE, _("Cash / Bank")),
        (TYPE_CLIENT, _("Customers")),
        (TYPE_AUTRE, _("Other")),
    ]

    uuid = models.UUIDField(primary_key=True, default=uuid_lib.uuid4)
    numero = models.CharField(max_length=12, verbose_name=_("Account number"))
    libelle = models.CharField(max_length=120, verbose_name=_("Label"))
    type_compte = models.CharField(max_length=1, choices=TYPE_CHOICES)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['numero']
        constraints = [
            models.UniqueConstraint(fields=['numero'], name='unique_compte_numero'),
        ]

    def __str__(self):
        return f"{self.numero} — {self.libelle}"
```

Seed initial (data migration) — plan comptable français standard :

| Numéro | Libellé | Type |
|---|---|---|
| 411000 | Clients | C |
| 512000 | Banque | B |
| 530000 | Caisse (espèces) | B |
| 511000 | Chèques à encaisser | B |
| 4457100 | TVA collectée 5,5% | T |
| 4457200 | TVA collectée 10% | T |
| 4457300 | TVA collectée 20% | T |
| 706000 | Prestations de services (billets) | V |
| 756000 | Cotisations (adhésions) | V |

#### 2.4.2 `MappingMoyenDePaiement`

```python
class MappingMoyenDePaiement(models.Model):
    """
    Mappage d'un moyen de paiement (PaymentMethod) vers un compte
    comptable de trésorerie.
    / Maps a PaymentMethod to a treasury accounting account.

    LOCALISATION : comptabilite/models.py
    """

    payment_method = models.CharField(
        max_length=2,
        unique=True,
        verbose_name=_("Payment method"),
        help_text=_("PaymentMethod code from BaseBillet (CC, CA, CH, TR, SF, ...)"),
    )
    compte = models.ForeignKey(
        CompteComptable,
        on_delete=models.PROTECT,
        verbose_name=_("Accounting account"),
        limit_choices_to={'type_compte__in': ['B', 'C']},
    )

    def __str__(self):
        return f"{self.get_payment_method_display()} → {self.compte}"
```

Seed initial (data migration) :

| PaymentMethod | Compte |
|---|---|
| CC (CB TPE) | 512000 |
| CA (Espèces) | 530000 |
| CH (Chèque) | 511000 |
| TR (Virement) | 512000 |
| SF/SN/SP/SR (Stripe) | 512000 |
| QR (QrCode/NFC) | 512000 |
| LE/LG (Asset local) | 411000 |

### 2.5 Migrations initiales

`comptabilite/migrations/0001_initial.py` — `ClotureCaisse` seul,
créée par `makemigrations comptabilite` en S1.
Dépend de `AuthBillet.0001_initial` (FK responsable).

`comptabilite/migrations/0002_compte_mapping.py` — modèles
`CompteComptable` + `MappingMoyenDePaiement` + data migration de seed,
créée en S5.

`BaseBillet/migrations/00XX_configuration_rapport_emails_periodicite.py`
— AddField sur Configuration (2 champs), en S1.

---

## 3. Filtres de base et règles métier

### 3.1 Queryset des lignes éligibles

```python
# Une ligne entre dans le rapport si :
LigneArticle.objects.filter(
    datetime__gte=datetime_debut,
    datetime__lt=datetime_fin,
    status__in=[
        LigneArticle.VALID,        # V
        LigneArticle.PAID,         # P (payé mais pas encore confirmé webhook)
        LigneArticle.FREERES,      # F (réservation gratuite)
        LigneArticle.CREDIT_NOTE,  # N (avoir, montant négatif)
    ],
).exclude(
    sale_origin=SaleOrigin.LABOUTIK,  # exclut le futur POS (quand l'app reviendra)
)
```

### 3.2 Mappage des moyens de paiement V1 (12 valeurs)

Le rapport groupe par `PaymentMethod`. On affiche un libellé humain par
valeur. Pas d'agrégation automatique « espèces / CB / cashless » comme
en V2 — V1 a une granularité différente.

| Code | Libellé | Catégorie comptable suggérée |
|---|---|---|
| `SF` STRIPE_FED | Stripe (fédéré) | Vente en ligne |
| `SN` STRIPE_NOFED | Stripe CC | Vente en ligne |
| `SP` STRIPE_SEPA_NOFED | Stripe SEPA | Vente en ligne |
| `SR` STRIPE_RECURENT | Stripe abonnement | Vente en ligne |
| `CC` | CB (TPE physique) | Vente en présentiel |
| `CA` CASH | Espèces | Vente en présentiel |
| `CH` CHEQUE | Chèque | Vente en présentiel |
| `TR` TRANSFER | Virement | Vente différée |
| `QR` QRCODE_MA | QR/NFC | Vente en présentiel |
| `LE` LOCAL_EURO | Asset local fiat | (présent si fedow_connect) |
| `LG` LOCAL_GIFT | Asset local gift | (présent si fedow_connect) |
| `NA` FREE | Offert | Hors CA |
| `UK` UNKNOWN | Inconnu | Hors CA (anomalie) |

`fedow_connect` reste en V1 (cf. `M-To-V2/INDEX.md`) : on peut donc
voir des `LE`/`LG` si le tenant a Fedow V1 actif. On les affiche
fidèlement sans les agréger comme « cashless ».

### 3.3 Numéro séquentiel (continu global)

Décision : **un seul compteur incrémental global par tenant**, partagé
par les 4 niveaux (J + H + M + A). Conformité LNE V2 préservée.

À la création de TOUTE nouvelle clôture :

```python
with transaction.atomic():
    derniere = (
        ClotureCaisse.objects
        .select_for_update()
        .order_by('-numero_sequentiel')
        .first()
    )
    prochain_numero = (derniere.numero_sequentiel + 1) if derniere else 1
```

Verrou `select_for_update()` indispensable pour éviter les courses si
plusieurs tâches Celery se déclenchent sur le même tenant à un instant
proche (p.ex. cron_cloture_quotidienne + cron_cloture_hebdomadaire le
lundi matin). La transaction couvre la lecture du dernier numéro ET
l'insertion de la nouvelle clôture.

Exemple de progression dans un tenant :
```
#1  J  2026-05-14
#2  J  2026-05-15
#3  H  semaine 2026-05-09 / 2026-05-15
#4  J  2026-05-16
...
```

Pas de trou possible : `UniqueConstraint(numero_sequentiel)` empêche
les doublons. La vérification de continuité (numéros 1, 2, 3, ... sans
gap) se fait via une management command `verify_clotures` à créer en
S6.

### 3.4 Hash chain

```python
import hashlib

lignes = list(queryset.order_by('uuid').values('uuid', 'amount', 'qty', 'status'))
payload = "|".join(
    f"{ligne['uuid']}:{ligne['amount']}:{ligne['qty']}:{ligne['status']}"
    for ligne in lignes
)
hash_lignes = hashlib.sha256(payload.encode('utf-8')).hexdigest()
```

Le hash est calculé à la clôture et stocké. À la consultation, on
peut re-calculer le hash et signaler si une ligne a été modifiée
post-clôture (bandeau d'alerte dans l'admin).

### 3.5 Total perpétuel

```python
clotures_anterieures = ClotureCaisse.objects.filter(
    niveau=ClotureCaisse.NIVEAU_JOURNALIER,
    datetime_fin__lt=cloture.datetime_fin,
).order_by('-datetime_fin').first()

cloture.total_perpetuel = (
    (clotures_anterieures.total_perpetuel if clotures_anterieures else 0)
    + cloture.total_general
)
```

Le total perpétuel ne s'applique qu'au niveau **journalier**. Les
niveaux H/M/A le copient depuis la dernière clôture journalière incluse.

---

## 4. Service `RapportComptableService`

Fichier : `comptabilite/services.py`

### 4.1 Signature

```python
from django.db.models import Sum, F, Count, Q, Value, IntegerField
from django.db.models.functions import Coalesce

class RapportComptableService:
    """
    Calcule un rapport comptable agrégé pour une période donnée.

    LOCALISATION : comptabilite/services.py

    Le service est stateless : on l'instancie pour une période, on appelle
    generer_rapport_complet(), on récupère un dict prêt à stocker dans
    ClotureCaisse.rapport_json.
    """

    def __init__(self, datetime_debut, datetime_fin):
        self.datetime_debut = datetime_debut
        self.datetime_fin = datetime_fin
        self.queryset = self._base_queryset()

    def _base_queryset(self):
        from BaseBillet.models import LigneArticle, SaleOrigin
        return LigneArticle.objects.filter(
            datetime__gte=self.datetime_debut,
            datetime__lt=self.datetime_fin,
            status__in=[
                LigneArticle.VALID,
                LigneArticle.PAID,
                LigneArticle.FREERES,
                LigneArticle.CREDIT_NOTE,
            ],
        ).exclude(sale_origin=SaleOrigin.LABOUTIK)

    def generer_rapport_complet(self) -> dict:
        return {
            "totaux_par_moyen": self.calculer_totaux_par_moyen(),
            "detail_ventes": self.calculer_detail_ventes(),
            "tva": self.calculer_tva(),
            "adhesions": self.calculer_adhesions(),
            "billets": self.calculer_billets(),
            "remboursements": self.calculer_remboursements(),
            "synthese_operations": self.calculer_synthese_operations(),
            "infos_legales": self.calculer_infos_legales(),
            "meta": {
                "datetime_debut": self.datetime_debut.isoformat(),
                "datetime_fin": self.datetime_fin.isoformat(),
                "schema": connection.schema_name,
            },
        }

    def calculer_totaux_par_moyen(self) -> dict:
        ...
    def calculer_detail_ventes(self) -> dict:
        ...
    def calculer_tva(self) -> dict:
        ...
    def calculer_adhesions(self) -> dict:
        ...
    def calculer_billets(self) -> dict:
        ...
    def calculer_remboursements(self) -> dict:
        ...
    def calculer_synthese_operations(self) -> dict:
        ...
    def calculer_infos_legales(self) -> dict:
        ...

    def calculer_hash_lignes(self) -> str:
        ...
```

### 4.2 Structure du `rapport_json`

```python
{
  "totaux_par_moyen": {
    "STRIPE_FED": {"label": "Online: federated Stripe", "total": 12500, "nb": 7},
    "STRIPE_NOFED": {"label": "Online: Stripe CC", "total": 0, "nb": 0},
    "CC": {"label": "Credit card: POS terminal", "total": 2400, "nb": 3},
    "CASH": {"label": "Cash", "total": 1500, "nb": 2},
    ...
    "total": 16400,
    "currency_code": "EUR"
  },

  "detail_ventes": {
    "Catégorie A (uuid)": {
      "nom_categorie": "Concerts",
      "articles": [
        {
          "nom_produit": "Concert Jazz - tarif réduit",
          "qty_payants": 4.0,
          "qty_offerts": 1.0,
          "qty_total": 5.0,
          "total_ttc": 4000,
          "total_ht": 3791,
          "total_tva": 209,
          "taux_tva": 5.50,
        },
        ...
      ],
      "total_ttc": 4000
    },
    ...
  },

  "tva": {
    "5.50": {"taux": 5.50, "total_ttc": 4000, "total_ht": 3791, "total_tva": 209},
    "10.00": {...},
    "20.00": {...}
  },

  "adhesions": {
    "detail": {
      "<uuid_produit>__<uuid_tarif>__<moyen>": {
        "nom_produit": "Adhésion 2026",
        "nom_tarif": "Solidaire",
        "moyen_paiement": "STRIPE_FED",
        "moyen_paiement_label": "Online: federated Stripe",
        "total": 1500,
        "nb": 1
      }
    },
    "total": 1500,
    "nb": 1
  },

  "billets": {
    "detail": {
      "<uuid_event>__<uuid_produit>__<uuid_tarif>": {
        "nom_event": "Concert Jazz",
        "date_event": "2026-05-20 20:30",
        "nom_produit": "Concert Jazz - tarif réduit",
        "nom_tarif": "Réduit",
        "nb": 4,
        "total": 4000
      }
    },
    "nb": 4,
    "total": 4000
  },

  "remboursements": {
    "refunded": {"total": -1500, "nb": 1},
    "credit_notes": {"total": -800, "nb": 1}
  },

  "synthese_operations": {
    "vente_billets": {"STRIPE_FED": 4000, "CASH": 0, ...},
    "vente_adhesions": {"STRIPE_FED": 1500, ...},
    "remboursements": {"STRIPE_FED": -1500, ...}
  },

  "infos_legales": {
    "organisation": "Association XYZ",
    "adresse": "12 rue de la Liberté",
    "code_postal": "44000",
    "ville": "Nantes",
    "siren": "123456789",
    "tva_number": "FR12345678901",
    "email": "contact@assoc.fr",
    "phone": "+33240000000"
  },

  "meta": {
    "datetime_debut": "2026-05-14T00:00:00+00:00",
    "datetime_fin": "2026-05-15T00:00:00+00:00",
    "schema": "lespass"
  }
}
```

**Convention montants** : tout en **centimes (int)**, jamais float.
Conversion `int(amount * qty)` partout. Affichage `value / 100` avec
deux décimales dans les templates.

---

## 5. Admin Unfold

### 5.1 `comptabilite/admin.py`

```python
from django.contrib import admin
from django.urls import path
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from unfold.admin import ModelAdmin

from Administration.admin.site import staff_admin_site
from Administration.utils import TenantAdminPermissionWithRequest
from comptabilite.models import ClotureCaisse


@admin.register(ClotureCaisse, site=staff_admin_site)
class ClotureCaisseAdmin(ModelAdmin):
    list_display = (
        "datetime_fin",
        "niveau_badge",
        "numero_sequentiel",
        "responsable",
        "ca_ttc_euros",
        "nombre_transactions",
    )
    list_filter = ("niveau",)
    search_fields = ("responsable__email",)
    ordering = ("-datetime_fin",)

    change_form_before_template = "comptabilite/admin/change_form_before.html"
    changelist_before_template = "comptabilite/admin/changelist_before.html"

    fieldsets = ()  # fieldsets cachés (rapport visuel à la place)

    # --- Permissions read-only ---
    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return False  # création uniquement via Celery ou management command

    def has_change_permission(self, request, obj=None):
        return False  # immuable

    def has_delete_permission(self, request, obj=None):
        return False  # immuable

    # --- Helpers affichage (au niveau module, pas méthodes) ---
    @admin.display(description=_("Total TTC"))
    def ca_ttc_euros(self, obj):
        return f"{obj.total_general / 100:.2f} €"

    @admin.display(description=_("Periodicity"))
    def niveau_badge(self, obj):
        return obj.get_niveau_display()

    # --- URLs custom (exports) ---
    def get_urls(self):
        urls_base = super().get_urls()
        custom = [
            path(
                "<uuid:object_id>/exporter-csv/",
                self.admin_site.admin_view(self.exporter_csv),
                name="comptabilite_cloturecaisse_csv",
            ),
            path(
                "<uuid:object_id>/exporter-excel/",
                self.admin_site.admin_view(self.exporter_excel),
                name="comptabilite_cloturecaisse_excel",
            ),
            path(
                "<uuid:object_id>/exporter-pdf/",
                self.admin_site.admin_view(self.exporter_pdf),
                name="comptabilite_cloturecaisse_pdf",
            ),
            path(
                "<uuid:object_id>/exporter-fec/",
                self.admin_site.admin_view(self.exporter_fec),
                name="comptabilite_cloturecaisse_fec",
            ),
            path(
                "<uuid:object_id>/exporter-csv-comptable/",
                self.admin_site.admin_view(self.exporter_csv_comptable),
                name="comptabilite_cloturecaisse_csv_comptable",
            ),
            path(
                "rapport-temps-reel/",
                self.admin_site.admin_view(self.rapport_temps_reel),
                name="comptabilite_cloturecaisse_temps_reel",
            ),
        ]
        return custom + urls_base

    def exporter_csv(self, request, object_id):
        ...
    def exporter_excel(self, request, object_id):
        ...
    def exporter_pdf(self, request, object_id):
        ...
    def exporter_fec(self, request, object_id):
        ...
    def exporter_csv_comptable(self, request, object_id):
        ...
    def rapport_temps_reel(self, request):
        ...

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        extra_context = extra_context or {}
        if object_id:
            cloture = get_object_or_404(ClotureCaisse, pk=object_id)
            extra_context["cloture"] = cloture
            extra_context["rapport"] = cloture.rapport_json
        return super().changeform_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["url_temps_reel"] = "rapport-temps-reel/"
        return super().changelist_view(request, extra_context)
```

### 5.2 Templates Unfold

`comptabilite/templates/comptabilite/admin/changelist_before.html` :

> Card Unfold avec 1 lien « Real-time report » vers
> `/admin/comptabilite/cloturecaisse/rapport-temps-reel/`. Pas de bandeau
> d'export global (les exports sont sur la fiche détail).

`comptabilite/templates/comptabilite/admin/change_form_before.html` :

> Le rapport visuel complet, **section par section**. Chaque section
> est conditionnelle (`{% if rapport.detail_ventes %}`). Boutons
> d'export en sticky-header. CSS inline (cf. `djc.md` règle Unfold).
> Style : utilise `var(--color-primary-600)`, `var(--color-base-0)`
> de Unfold.

`comptabilite/templates/comptabilite/admin/export_csv_comptable_form.html` :

> Formulaire HTMX partial (GET → form, POST → CSV stream). Champs :
> date_debut, date_fin (optionnels, par défaut période de la clôture),
> profil (select : sage_50, ebp).

### 5.3 Intégration sidebar

Dans `Administration/admin/dashboard.py:543-584`, modifier la section
*Sales & accounting* pour insérer **AVANT** *Entries* :

```python
"items": [
    {
        "title": _("Cash closure"),
        "icon": "lock",
        "link": reverse_lazy(
            "staff_admin:comptabilite_cloturecaisse_changelist"
        ),
        "permission": admin_permission,
    },
    {
        "title": _("Entries"),
        "icon": "receipt_long",
        "link": reverse_lazy(
            "staff_admin:BaseBillet_lignearticle_changelist"
        ),
        "permission": admin_permission,
    },
    # ... items V2 commentés (Operation logs, Accounting codes, ...)
],
```

---

## 6. Exports

### 6.1 CSV (`comptabilite/csv_export.py`)

- Format : `;` séparateur, UTF-8 BOM
- Source : `cloture.rapport_json` (pas de recalcul)
- Sections concaténées : en-tête → totaux par moyen → ventes par
  catégorie → TVA → adhésions → billets → remboursements
- Pattern de V2 réutilisé tel quel (~100 lignes), juste adapté aux
  clés V1

### 6.2 Excel (`comptabilite/excel_export.py`)

- `openpyxl.Workbook`, 1 feuille « Rapport »
- Styles V2 conservés : en-têtes section blanc/gris #333333,
  en-têtes colonnes #F0F0F0, lignes bordées
- Auto-width colonnes
- Retour `bytes` via `io.BytesIO`

### 6.3 PDF (`comptabilite/pdf.py`)

- Template `comptabilite/pdf/rapport_comptable.html`
- WeasyPrint (`weasyprint.HTML().write_pdf()`)
- Styles inline obligatoires (WeasyPrint sans CSS externe pour
  fiabilité)
- A4, marges 1cm
- Contenu : 8 sections (mêmes que rapport visuel admin)

### 6.4 FEC (`comptabilite/fec.py`)

Le **Fichier des Écritures Comptables** est un format réglementaire
français : 18 colonnes tabulées, encodage UTF-8 ou CP1252,
séparateur `|` ou tab.

Colonnes obligatoires : `JournalCode`, `JournalLib`, `EcritureNum`,
`EcritureDate`, `CompteNum`, `CompteLib`, `CompAuxNum`, `CompAuxLib`,
`PieceRef`, `PieceDate`, `EcritureLib`, `Debit`, `Credit`,
`EcritureLet`, `DateLet`, `ValidDate`, `Montantdevise`, `Idevise`.

Implémentation portée depuis V2 — **adapter le mapping comptable** :
- Stripe → compte 411 (clients) puis 512 (banque)
- Espèces → 530
- Chèque → 511
- Virement → 512
- Ventes billets → 706 (prestations)
- Ventes adhésions → 756 (cotisations)
- TVA collectée → 4457X

Note : le tenant peut ne pas avoir paramétré ses comptes comptables.
Dans ce cas, on utilise les comptes par défaut ci-dessus et on génère
des **avertissements** retournés à l'admin.

### 6.5 CSV comptable (`comptabilite/csv_comptable.py` + `profils_csv.py`)

- **8 profils ciblés sur le chantier** :
  - **Phase A (S5)** : Sage 50, EBP, Paheko
  - **Phase B (S6)** : Dolibarr, PennyLane, CIEL, ODOO, DOKO
- Architecture extensible : 1 dict de config par profil
  (séparateur, décimal, encodage, mode débit/crédit ou montant signé,
  format dates, mapping colonnes spécifique).
- Ventilation comptable : 1 ligne par moyen de paiement (débit
  trésorerie) + 1 ligne par catégorie de vente (crédit 706/756) +
  1 ligne par taux TVA (crédit 4457X), avec un **journal** par tenant
  (paramétré dans `Configuration` — à ajouter aussi en S5).
- **Lookup compte** : passe par les modèles `CompteComptable` et
  `MappingMoyenDePaiement` (§2.4). Si un compte manque, génération
  d'avertissements retournés à l'admin avec l'export.
- Modes montant supportés :
  - `DEBIT_CREDIT` (Sage 50, Dolibarr, PennyLane) : 2 colonnes
  - `MONTANT_SENS` (EBP) : 1 colonne montant + 1 colonne D/C
  - `MONTANT_UNIQUE` (Paheko) : 1 colonne montant avec compte_débit
    et compte_crédit séparés
  - (CIEL, ODOO, DOKO à étudier finement en S6)

Squelette `profils_csv.py` :

```python
PROFILS = {
    'sage_50': {
        'nom_affiche': "Sage 50",
        'separateur': ';',
        'decimal': '.',
        'encodage': 'utf-8-sig',
        'mode_montant': 'DEBIT_CREDIT',
        'format_date': '%d/%m/%Y',
        'colonnes': ['JournalCode', 'EcritureDate', 'CompteNum',
                     'CompteLib', 'PieceRef', 'EcritureLib',
                     'Debit', 'Credit'],
        'extension': '.csv',
    },
    'ebp': {
        'nom_affiche': "EBP Compta",
        'separateur': ',',
        'decimal': '.',
        'encodage': 'cp1252',
        'mode_montant': 'MONTANT_SENS',
        'format_date': '%d/%m/%Y',
        'colonnes': ['Date', 'Journal', 'Compte', 'Libelle',
                     'Montant', 'Sens'],
        'extension': '.txt',
    },
    'paheko': {
        'nom_affiche': "Paheko / Garradin",
        'separateur': ';',
        'decimal': ',',
        'encodage': 'utf-8',
        'mode_montant': 'MONTANT_UNIQUE',
        'format_date': '%Y-%m-%d',
        'colonnes': ['date', 'libelle', 'compte_debit',
                     'compte_credit', 'montant'],
        'extension': '.csv',
    },
    # S6 : 'dolibarr', 'pennylane', 'ciel', 'odoo', 'doko'
}
```

---

## 7. Tâches Celery

### 7.1 `comptabilite/tasks.py`

```python
import logging
from celery import shared_task
from django_tenants.utils import tenant_context
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def generer_cloture_pour_tenant(schema_name, niveau, datetime_debut_iso=None, datetime_fin_iso=None):
    """
    Génère 1 clôture pour 1 tenant donné.
    / Generate 1 closure for 1 given tenant.

    LOCALISATION : comptabilite/tasks.py

    Appelée depuis le wrapper Celery beat ou la management command.
    Itère NON — c'est le wrapper qui itère sur les tenants.
    """
    from Customers.models import Client
    tenant = Client.objects.get(schema_name=schema_name)
    with tenant_context(tenant):
        from comptabilite.services import RapportComptableService
        from comptabilite.models import ClotureCaisse
        from BaseBillet.models import Configuration
        config = Configuration.get_solo()

        # Si aucun module pertinent activé, on saute
        if not (config.module_billetterie or config.module_adhesion):
            return

        # Calcul des bornes selon niveau
        datetime_debut, datetime_fin = _bornes_pour_niveau(niveau, datetime_debut_iso, datetime_fin_iso)

        # Idempotence : si déjà créée, on saute
        if ClotureCaisse.objects.filter(
            niveau=niveau,
            datetime_debut=datetime_debut,
            datetime_fin=datetime_fin,
        ).exists():
            return

        # Génération
        service = RapportComptableService(datetime_debut, datetime_fin)
        rapport = service.generer_rapport_complet()
        cloture = ClotureCaisse.objects.create(
            niveau=niveau,
            datetime_debut=datetime_debut,
            datetime_fin=datetime_fin,
            numero_sequentiel=_prochain_numero(niveau),
            total_general=rapport["totaux_par_moyen"]["total"],
            total_ht=rapport["tva"].get("__total_ht", 0),
            total_tva=rapport["tva"].get("__total_tva", 0),
            nombre_transactions=service.queryset.count(),
            total_perpetuel=_calcul_total_perpetuel(niveau, rapport["totaux_par_moyen"]["total"]),
            hash_lignes=service.calculer_hash_lignes(),
            rapport_json=rapport,
        )

        # Email si configuré
        if config.rapport_periodicite == niveau and config.rapport_emails:
            envoyer_email_cloture.delay(schema_name, str(cloture.uuid))


@shared_task
def envoyer_email_cloture(schema_name, cloture_uuid):
    """Envoie le rapport (PDF + Excel attachés) aux emails configurés."""
    ...
```

### 7.2 Wrappers Celery beat

Dans `TiBillet/celery.py`, ajouter (pattern `cron_morning` existant) :

```python
@app.task
def cron_cloture_quotidienne():
    call_command('generer_cloture', '--niveau=J')

@app.task
def cron_cloture_hebdomadaire():
    call_command('generer_cloture', '--niveau=H')

@app.task
def cron_cloture_mensuelle():
    call_command('generer_cloture', '--niveau=M')

@app.task
def cron_cloture_annuelle():
    call_command('generer_cloture', '--niveau=A')


# Dans setup_periodic_tasks(sender):
sender.add_periodic_task(
    crontab(hour=6, minute=0),  # 6h UTC = ~7h Paris l'hiver, 8h été
    cron_cloture_quotidienne.s(),
    name='cron_cloture_quotidienne',
)
sender.add_periodic_task(
    crontab(day_of_week=1, hour=6, minute=15),
    cron_cloture_hebdomadaire.s(),
    name='cron_cloture_hebdomadaire',
)
sender.add_periodic_task(
    crontab(day_of_month=1, hour=6, minute=30),
    cron_cloture_mensuelle.s(),
    name='cron_cloture_mensuelle',
)
sender.add_periodic_task(
    crontab(month_of_year=1, day_of_month=1, hour=6, minute=45),
    cron_cloture_annuelle.s(),
    name='cron_cloture_annuelle',
)
```

### 7.3 Management command

`comptabilite/management/commands/generer_cloture.py`

```python
class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--niveau', choices=['J', 'H', 'M', 'A'], required=True)
        parser.add_argument('--tenant', help="schema_name to limit to (else all tenants)")
        parser.add_argument('--datetime-debut', help="ISO datetime (override auto)")
        parser.add_argument('--datetime-fin', help="ISO datetime (override auto)")

    def handle(self, *args, **opts):
        from Customers.models import Client
        from comptabilite.tasks import generer_cloture_pour_tenant

        if opts.get('tenant'):
            tenants = Client.objects.filter(schema_name=opts['tenant'])
        else:
            tenants = Client.objects.exclude(schema_name='public')

        for tenant in tenants:
            generer_cloture_pour_tenant(
                schema_name=tenant.schema_name,
                niveau=opts['niveau'],
                datetime_debut_iso=opts.get('datetime_debut'),
                datetime_fin_iso=opts.get('datetime_fin'),
            )
```

### 7.4 Calcul des bornes par niveau

- **J** : `[hier 00:00, aujourd'hui 00:00)` en heure locale tenant
- **H** : `[lundi semaine dernière 00:00, lundi semaine courante 00:00)`
- **M** : `[1er du mois précédent 00:00, 1er du mois courant 00:00)`
- **A** : `[1er janvier année précédente 00:00, 1er janvier année courante 00:00)`

Timezone : `Configuration.language` ne suffit pas — V1 a un champ
`time_zone` à vérifier dans Configuration. À défaut, UTC.

### 7.5 Idempotence

`UniqueConstraint(niveau, datetime_debut, datetime_fin)` empêche les
doublons. La tâche vérifie en plus avant insertion pour éviter une
erreur d'intégrité.

---

## 8. Vue rapport temps réel

### 8.1 URL et template

`/admin/comptabilite/cloturecaisse/rapport-temps-reel/`
→ vue `rapport_temps_reel(request)` dans `ClotureCaisseAdmin`

### 8.2 Logique

```python
def rapport_temps_reel(self, request):
    # Bornes : depuis la dernière clôture journalière OU début de la journée
    derniere_cloture = ClotureCaisse.objects.filter(
        niveau=ClotureCaisse.NIVEAU_JOURNALIER
    ).order_by('-datetime_fin').first()

    if derniere_cloture:
        datetime_debut = derniere_cloture.datetime_fin
    else:
        datetime_debut = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)

    datetime_fin = timezone.now()

    service = RapportComptableService(datetime_debut, datetime_fin)
    rapport = service.generer_rapport_complet()

    return render(request, "comptabilite/views/rapport_temps_reel.html", {
        "rapport": rapport,
        "datetime_debut": datetime_debut,
        "datetime_fin": datetime_fin,
        "nb_transactions": service.queryset.count(),
    })
```

### 8.3 Template

Réutilise les mêmes partials que `change_form_before.html` (sections
visuelles). Ajoute un `hx-get` automatique toutes les 30s pour
rafraîchir la zone (anti-blink). Pattern HTMX classique :

```html
<div id="rapport-temps-reel"
     hx-get="{% url 'staff_admin:comptabilite_cloturecaisse_temps_reel' %}"
     hx-trigger="every 30s"
     aria-live="polite">
  {% include "comptabilite/admin/_sections_rapport.html" %}
</div>
```

---

## 9. Plan de découpage en sessions

### S1 — Squelette modèle + admin + sidebar

**Sortie :** `/admin/comptabilite/cloturecaisse/` accessible, liste vide.

- [ ] Créer app `comptabilite/` (`apps.py`, `__init__.py`)
- [ ] Modèle `ClotureCaisse` complet + 2 AddField sur Configuration
- [ ] Migration `comptabilite/migrations/0001_initial.py`
- [ ] Migration `BaseBillet/migrations/XXXX_configuration_rapport_emails.py`
- [ ] Ajouter `'comptabilite'` dans `TENANT_APPS` dans `TiBillet/settings.py`
- [ ] Admin Unfold minimal : `ClotureCaisseAdmin` avec list_display,
  permissions read-only
- [ ] Entrée sidebar dans `Administration/admin/dashboard.py`
  (section *Sales & accounting*, AVANT *Entries*)
- [ ] `manage.py check` OK
- [ ] `migrate_schemas` appliquée
- [ ] Visite manuelle de l'admin : page s'affiche, vide

### S2 — Service rapport + management command + tests pytest

**Sortie :** `manage.py generer_cloture --niveau=J --tenant=lespass`
crée une clôture en base avec un `rapport_json` valide.

- [ ] `comptabilite/services.py` : `RapportComptableService` complet
  (8 méthodes calculer_*)
- [ ] `comptabilite/management/commands/generer_cloture.py`
- [ ] `comptabilite/tasks.py` : `generer_cloture_pour_tenant` (Celery shared_task)
- [ ] Tests pytest `tests/pytest/test_comptabilite_service.py` :
  - Test fixture : créer 3 LigneArticle de statuts variés
  - Test : générer une clôture, vérifier `total_general`, `nombre_transactions`
  - Test : statuts CANCELED/UNPAID exclus
  - Test : sale_origin=LABOUTIK exclu
  - Test : hash_lignes change si une ligne modifiée
  - Test : numéro séquentiel sans trou sur 3 clôtures successives
  - Test : idempotence (2x appel même période = 1 clôture)

### S3 — Templates admin + vue rapport temps réel

**Sortie :** Détail d'une clôture lisible dans l'admin avec toutes
les sections. Page temps réel fonctionnelle.

- [ ] `comptabilite/templates/comptabilite/admin/change_form_before.html`
  (rapport visuel complet, 8 sections, CSS inline Unfold)
- [ ] `comptabilite/templates/comptabilite/admin/_sections_rapport.html`
  (partial réutilisable, inclus par change_form_before et temps réel)
- [ ] `comptabilite/templates/comptabilite/admin/changelist_before.html`
  (lien temps réel)
- [ ] Vue `rapport_temps_reel(request)` dans admin
- [ ] Template `comptabilite/templates/comptabilite/views/rapport_temps_reel.html`
  (HTMX every 30s + base admin Unfold)
- [ ] `data-testid` sur boutons et zones (cf. djc.md)
- [ ] `aria-live` sur zone HTMX
- [ ] Tests pytest `test_comptabilite_admin.py` : vues s'affichent (smoke tests)
- [ ] Vérification manuelle visuelle

### S4 — Exports CSV/Excel/PDF/FEC

**Sortie :** 4 boutons d'export téléchargeables depuis la fiche clôture.

- [ ] `comptabilite/csv_export.py` (port V2 simplifié)
- [ ] `comptabilite/excel_export.py` (port V2 conservé tel quel, styles)
- [ ] `comptabilite/pdf.py` + `comptabilite/templates/comptabilite/pdf/rapport_comptable.html`
  (WeasyPrint A4, styles inline)
- [ ] `comptabilite/fec.py` (port V2 adapté : retirer recharges/habitus,
  garder ventes/adhésions/billets)
- [ ] URLs admin enregistrées (`get_urls()` dans `ClotureCaisseAdmin`)
- [ ] Boutons dans `change_form_before.html` (Unfold style)
- [ ] Tests pytest : 4 exports retournent une réponse 200 avec le bon
  Content-Type

### S5 — Celery + email + modèles comptables + 3 profils CSV

**Sortie :** Génération auto J/H/M/A + email + plan comptable
paramétrable + 3 profils CSV (Sage 50, EBP, Paheko).

- [ ] Wrappers `@app.task cron_cloture_*` dans `TiBillet/celery.py`
- [ ] `add_periodic_task` pour 4 niveaux
- [ ] Logique calcul bornes par niveau (J/H/M/A)
- [ ] `comptabilite/tasks.py:envoyer_email_cloture` (Brevo via tenant)
- [ ] **Modèles `CompteComptable` + `MappingMoyenDePaiement`** (§2.4)
- [ ] Migration `0002_compte_mapping.py` avec data migration de seed
  (plan comptable français par défaut)
- [ ] Admin Unfold pour `CompteComptable` (read+write, dans la même
  section sidebar « Sales & accounting ») et `MappingMoyenDePaiement`
- [ ] `comptabilite/csv_comptable.py` + `comptabilite/profils_csv.py`
  (Sage 50, EBP, Paheko)
- [ ] Vue admin + formulaire HTMX `export_csv_comptable_form.html`
  (select profil parmi les 3)
- [ ] Tests pytest : tâche Celery génère bien la clôture J avec mock
  des bornes
- [ ] Tests pytest : 3 profils CSV produisent un fichier valide

### S6 — 5 profils CSV restants + polish

**Sortie :** Tous les profils CSV livrés + management commands de
vérification + tests finaux.

- [ ] Profil **Dolibarr** (CSV, séparateur `,`)
- [ ] Profil **PennyLane** (CSV, format moderne)
- [ ] Profil **CIEL Compta** (à investiguer format précis)
- [ ] Profil **ODOO** (CSV import compta)
- [ ] Profil **DOKO** (à investiguer)
- [ ] Management command `verify_clotures` (continuité numéros
  séquentiels + recalcul hash chain pour audit)
- [ ] Documentation utilisateur dans `TECH_DOC/cloture-comptable.md`
- [ ] CHANGELOG.md mise à jour
- [ ] Tests pytest couverture 5 profils CSV
- [ ] Tests E2E Playwright (optionnel) : navigation admin → export
  CSV téléchargé

---

## 10. Vérifications recommandées

À chaque session :

```bash
# Type-check Django
docker exec lespass_django poetry run python /DjangoFiles/manage.py check

# Migrations
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations cloture --check --dry-run
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas

# Tests
docker exec lespass_django poetry run pytest tests/pytest/test_comptabilite_*.py -v

# Vérification visuelle (le maintainer pilote le navigateur)
# 1. /admin/comptabilite/cloturecaisse/ -> liste s'affiche
# 2. Cliquer une clôture -> détail s'affiche
# 3. /admin/comptabilite/cloturecaisse/rapport-temps-reel/ -> page s'affiche
# 4. Exports : télécharger CSV/Excel/PDF/FEC -> fichiers valides
```

À la fin de chaque session, lancer le **i18n workflow** complet
(makemessages → editer .po → compilemessages) si des chaînes
`{% translate %}` ou `_()` ont été ajoutées.

---

## 11. Pièges anticipés

1. **Numéro séquentiel race condition** — Si deux tâches Celery
   tournent simultanément pour le même tenant et le même niveau, on
   peut avoir une collision sur `numero_sequentiel`. Solution :
   `select_for_update()` sur la dernière clôture + retry une fois.

2. **Hash chain vs migration des `LigneArticle.uuid`** — Si V1 a des
   `LigneArticle.uuid` qui sont des entiers (PK BigInt selon
   exploration), le hash utilise `pk` au lieu de `uuid`. À vérifier
   et adapter le calcul.

3. **`paiement_stripe` nullable** — Beaucoup de lignes (adhésions
   manuelles, billets gratuits) n'ont pas de `paiement_stripe`.
   Ne pas faire de `paiement_stripe__user__email` direct ; utiliser
   `Coalesce(paiement_stripe__user__email, membership__user__email)`.

4. **`vat` est un décimal sur LigneArticle** — Donc TVA = 5.5 et pas
   0.055. Faire `amount * qty * vat / (100 + vat) * 100` pour
   retrancher la TVA d'un TTC.

5. **WeasyPrint et fonts** — V1 a déjà WeasyPrint installé pour les
   tickets PDF. Vérifier que les fonts (Roboto, etc.) sont accessibles
   ; sinon ajouter un `<style>@font-face ...</style>` inline.

6. **Multi-tenant et `connection.schema_name`** — Toujours obtenir le
   schéma via `connection.schema_name` dans le service (pas de cache
   inter-tenant).

7. **Idempotence Celery beat** — Si Celery beat redémarre, il peut
   relancer une tâche déjà passée. La `UniqueConstraint` empêche le
   doublon en DB, mais on doit catcher `IntegrityError` et logger.

8. **Bornes journalières en heure locale tenant** — `timezone.now()`
   est UTC. Conversion via `timezone.localtime()` + truncate à minuit.
   Tester avec un tenant en zone non-Europe (DOM-TOM, etc.).

9. **Idle vs créé** — `manage.py check` peut passer alors qu'une vue
   admin custom mal nommée crashe au runtime. Toujours visiter
   manuellement après ajout d'URL admin.

10. **fedow_connect reste actif en V1** — Les `payment_method=LE/LG`
    peuvent apparaître dans le rapport. C'est OK, on les affiche
    fidèlement (pas de tentative de calcul cashless V2).

---

## 12. Notes pour le futur

Cette spec n'inclut **pas** :

- Mode école (V2 a `sale_origin=LABOUTIK_TEST` pour formation, V1
  n'en a pas besoin).
- Archivage long terme (V2 a un système d'archivage 10 ans).
  Pour V1, on garde tout en DB sans expiration. Possible amélioration
  future.
- Signature électronique des clôtures (V2 a un système HMAC pour
  conformité LNE caisse française — pas pertinent en V1 sans POS).
- Intégration Sentry pour observabilité dédiée (à intégrer dans le
  chantier observabilité global, cf. IDEAS Atomic).

---

## 13. Décisions maintainer (tranchées 2026-05-15)

- [x] **Nom app** : `comptabilite` (englobe futurs modèles `CompteComptable`
  et `MappingMoyenDePaiement`)
- [x] **Comptes comptables** : **paramétrables dès S5** via modèles
  `CompteComptable` + `MappingMoyenDePaiement` (cf. §2.4), avec seed
  initial du plan comptable général français
- [x] **Profils CSV** : 7 profils ciblés sur 2 phases
  - S5 : Sage 50, EBP, Paheko
  - S6 : Dolibarr, PennyLane, CIEL, ODOO, DOKO
- [x] **Numéro séquentiel** : **continu global tenant**, partagé par
  les 4 niveaux (J + H + M + A). `UniqueConstraint(numero_sequentiel)`,
  `select_for_update()` à la lecture du dernier numéro. Conformité
  LNE V2 préservée.

### Encore à arbitrer (mais non bloquant pour S1) :

- [ ] **Heure de génération des clôtures** : par défaut 6h UTC
  (~7h-8h Europe selon DST). À confirmer ou choix d'une autre heure
  qui colle aux usages (ex. 4h UTC pour avoir le rapport prêt avant
  l'ouverture du lieu).
- [ ] **Niveau de tests pytest** : couverture complète des 8 sections
  du rapport recommandée vs smoke tests seulement (recommandation :
  couverture complète, vu l'importance comptable).
- [ ] **Tâche `envoyer_rapports_clotures_recentes`** de V2 (récap
  multi-clotures envoyé en bloc) : à porter en S5 ou skipper ?
  Recommandation : skipper en S5 (1 email = 1 clôture), revoir en S6.
