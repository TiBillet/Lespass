# Session 20 — Export comptable (mapping + FEC) : Plan d'implementation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre aux lieux d'exporter leurs donnees de caisse au format FEC (fichier comptable standard francais) en mappant leurs categories d'articles et moyens de paiement sur des comptes du plan comptable.

**Architecture:** 2 nouveaux modeles dans `laboutik/models.py` (CompteComptable + MappingMoyenDePaiement), 1 FK ajoutee sur `BaseBillet/models.py` (CategorieProduct.compte_comptable), 1 generateur FEC dans `laboutik/fec.py`, 1 management command pour charger les fixtures, admin Unfold, action ViewSet pour l'export.

**Tech Stack:** Django 4.2, django-tenants, DRF, Unfold admin, pytest (FastTenantTestCase), csv/io.

**Spec:** `TECH DOC/Laboutik sessions/Session 02 - Billetterie POS et ventes/specs/2026-04-02-export-comptable-mapping-fec-design.md`

---

## Fichiers

| Action | Fichier | Responsabilite |
|--------|---------|----------------|
| Modifier | `laboutik/models.py` | Ajouter CompteComptable + MappingMoyenDePaiement |
| Modifier | `BaseBillet/models.py` (~ligne 943) | Ajouter FK compte_comptable sur CategorieProduct |
| Creer | `laboutik/migrations/0018_comptecomptable_mappingmoyendepaiement.py` | Migration laboutik |
| Creer | `BaseBillet/migrations/XXXX_categorieproduct_compte_comptable.py` | Migration BaseBillet |
| Creer | `laboutik/fec.py` | Generateur FEC 18 colonnes |
| Creer | `laboutik/management/commands/charger_plan_comptable.py` | Fixtures par defaut |
| Modifier | `laboutik/views.py` | Action ViewSet export_fec + charger_plan |
| Modifier | `Administration/admin/laboutik.py` | Admins CompteComptable + MappingMoyenDePaiement |
| Creer | `Administration/templates/admin/comptable/changelist_before.html` | Bandeau chargement plan |
| Creer | `Administration/templates/admin/cloture/export_fec_form.html` | Formulaire HTMX inline |
| Creer | `tests/pytest/test_export_comptable.py` | 11 tests |
| Creer | `TECH DOC/A DOCUMENTER/export-comptable-guide-utilisateur.md` | Doc utilisateur |

---

## Task 1 : Modeles CompteComptable + MappingMoyenDePaiement

**Files:**
- Modify: `laboutik/models.py` (ajouter apres HistoriqueFondDeCaisse)

- [ ] **Step 1: Ajouter CompteComptable**

Ajouter a la fin de `laboutik/models.py` :

```python
# --- Comptes comptables pour l'export FEC ---
# Chaque lieu a sa propre liste de comptes du plan comptable (PCG).
# TiBillet ne gere PAS un plan comptable complet : on stocke uniquement
# les comptes utiles pour l'export vers le logiciel du cabinet comptable.
# / Accounting codes for FEC export.
# Each venue has its own list of accounting codes (French PCG).
# TiBillet does NOT manage a full chart of accounts: we only store
# the codes needed for export to the accounting firm's software.

class CompteComptable(models.Model):
    """
    Un compte du plan comptable (PCG) configurable par lieu.
    / A configurable accounting code from the French chart of accounts (PCG).

    LOCALISATION : laboutik/models.py

    Le premier chiffre du numero indique la classe :
    - 4xx : Tiers (TVA collectee)
    - 5xx : Tresorerie (banque, caisse)
    - 6xx : Charges (ecarts de gestion -)
    - 7xx : Produits / Ventes (boissons, alimentaire)
    / First digit indicates the class:
    - 4xx: Third parties (collected VAT)
    - 5xx: Treasury (bank, cash register)
    - 6xx: Expenses (negative discrepancies)
    - 7xx: Revenue / Sales (beverages, food)
    """
    VENTE = 'VENTE'
    TVA = 'TVA'
    TRESORERIE = 'TRESORERIE'
    TIERS = 'TIERS'
    CHARGE = 'CHARGE'
    PRODUIT_EXCEPTIONNEL = 'PRODUIT_EXCEPTIONNEL'
    SPECIAL = 'SPECIAL'
    NATURE_CHOICES = [
        (VENTE, _('Sales account (class 7)')),
        (TVA, _('VAT account (class 44)')),
        (TRESORERIE, _('Treasury account (class 5)')),
        (TIERS, _('Third-party account (class 4)')),
        (CHARGE, _('Expense account (class 6)')),
        (PRODUIT_EXCEPTIONNEL, _('Exceptional income (class 7)')),
        (SPECIAL, _('Special account (discounts, discrepancies)')),
    ]

    uuid = models.UUIDField(
        primary_key=True, default=uuid_module.uuid4, editable=False,
        unique=True, db_index=True,
    )

    # Le numero de compte PCG (ex: "7072000", "445712", "5300000")
    # / PCG account number
    numero_de_compte = models.CharField(
        max_length=20,
        verbose_name=_("Account number"),
        help_text=_("Numero du compte dans le plan comptable (ex: 7072000). / PCG account number."),
    )

    # Le libelle du compte (ex: "Boissons a 20%", "TVA 20%")
    # / Account label
    libelle_du_compte = models.CharField(
        max_length=200,
        verbose_name=_("Account label"),
        help_text=_("Intitule du compte tel qu'il apparaitra dans l'export. / Account label as it will appear in the export."),
    )

    # La nature du compte, pour faciliter le filtrage et le lookup
    # / Account nature, for filtering and lookup
    nature_du_compte = models.CharField(
        max_length=30,
        choices=NATURE_CHOICES,
        verbose_name=_("Account nature"),
    )

    # Taux de TVA : utilise pour les comptes VENTE (taux applicable) et TVA (taux collecte)
    # Permet le lookup : CompteComptable.objects.get(nature='TVA', taux_de_tva=20.00)
    # Null si pas applicable (comptes TRESORERIE, SPECIAL, etc.)
    # / VAT rate: used for VENTE accounts (applicable rate) and TVA accounts (collected rate)
    taux_de_tva = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        verbose_name=_("VAT rate (%)"),
        help_text=_("Taux de TVA en % (ex: 20.00, 10.00, 5.50). Vide si non applicable. / VAT rate in %. Empty if not applicable."),
    )

    # Compte actif ou pas (pour desactiver sans supprimer)
    # / Active flag (to deactivate without deleting)
    est_actif = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
    )

    def __str__(self):
        return f"{self.numero_de_compte} — {self.libelle_du_compte}"

    class Meta:
        ordering = ['numero_de_compte']
        verbose_name = _('Accounting code')
        verbose_name_plural = _('Accounting codes')


class MappingMoyenDePaiement(models.Model):
    """
    Associe un code PaymentMethod a un compte comptable de tresorerie.
    Plusieurs moyens peuvent pointer vers le meme compte (ex: CB + Stripe → 512000).
    Si compte_de_tresorerie est null, ce moyen est ignore a l'export
    (ex: cashless NFC = argent deja encaisse lors de la recharge).
    / Maps a PaymentMethod code to a treasury accounting code.
    Multiple methods can point to the same account (e.g. CC + Stripe → 512000).
    If compte_de_tresorerie is null, this method is ignored in export
    (e.g. cashless NFC = money already collected during top-up).

    LOCALISATION : laboutik/models.py
    """
    uuid = models.UUIDField(
        primary_key=True, default=uuid_module.uuid4, editable=False,
        unique=True, db_index=True,
    )

    # Le code du moyen de paiement (reprend les codes PaymentMethod de BaseBillet)
    # / The payment method code (uses BaseBillet PaymentMethod codes)
    moyen_de_paiement = models.CharField(
        max_length=10,
        unique=True,
        verbose_name=_("Payment method code"),
        help_text=_("Code PaymentMethod (CA=Especes, CC=CB, CH=Cheque, etc.). / PaymentMethod code."),
    )

    # Libelle humain du moyen de paiement
    # / Human-readable label
    libelle_moyen = models.CharField(
        max_length=100,
        verbose_name=_("Payment method label"),
        help_text=_("Libelle affiche dans l'admin (ex: Especes, Carte bancaire). / Display label."),
    )

    # Le compte comptable de tresorerie associe (null = moyen ignore)
    # / Associated treasury account (null = method ignored in export)
    compte_de_tresorerie = models.ForeignKey(
        CompteComptable, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='moyens_de_paiement',
        verbose_name=_("Treasury account"),
        help_text=_(
            "Compte de tresorerie pour ce moyen de paiement. "
            "Laisser vide pour ignorer ce moyen a l'export (ex: cashless). "
            "/ Treasury account for this payment method. "
            "Leave empty to ignore this method in export (e.g. cashless)."
        ),
    )

    def __str__(self):
        compte_label = self.compte_de_tresorerie or _("(ignored)")
        return f"{self.libelle_moyen} → {compte_label}"

    class Meta:
        ordering = ['moyen_de_paiement']
        verbose_name = _('Payment method mapping')
        verbose_name_plural = _('Payment method mappings')
```

- [ ] **Step 2: Ajouter FK compte_comptable sur CategorieProduct**

Dans `BaseBillet/models.py`, apres le champ `printer` de CategorieProduct (~ligne 943), ajouter :

```python
    # Compte comptable de vente associe a cette categorie (export FEC/CSV)
    # FK vers laboutik.CompteComptable — meme schema tenant, pas de probleme cross-app
    # (meme pattern que le champ printer ci-dessus).
    # / Sales accounting code for this category (FEC/CSV export)
    # FK to laboutik.CompteComptable — same tenant schema, no cross-app issue.
    compte_comptable = models.ForeignKey(
        'laboutik.CompteComptable', on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='categories_produit',
        verbose_name=_("Accounting code"),
        help_text=_(
            "Compte comptable de vente (classe 7) pour l'export FEC. "
            "/ Sales accounting code (class 7) for FEC export."
        ),
    )
```

- [ ] **Step 3: Generer les migrations**

```bash
docker exec lespass_django poetry run python manage.py makemigrations laboutik --name comptecomptable_mappingmoyendepaiement
docker exec lespass_django poetry run python manage.py makemigrations BaseBillet --name categorieproduct_compte_comptable
```

- [ ] **Step 4: Appliquer les migrations**

```bash
docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing
```

- [ ] **Step 5: Verifier**

```bash
docker exec lespass_django poetry run python manage.py check
```

---

## Task 2 : Admin Unfold pour CompteComptable + MappingMoyenDePaiement

**Files:**
- Modify: `Administration/admin/laboutik.py`
- Create: `Administration/templates/admin/comptable/changelist_before.html`

- [ ] **Step 1: Ajouter les imports**

Ajouter aux imports existants de `laboutik.models` :

```python
from laboutik.models import (
    ...,  # imports existants
    CompteComptable,
    MappingMoyenDePaiement,
)
```

- [ ] **Step 2: Ajouter CompteComptableAdmin**

```python
@admin.register(CompteComptable, site=staff_admin_site)
class CompteComptableAdmin(ModelAdmin):
    """
    Admin CRUD pour les comptes comptables du lieu.
    / CRUD admin for the venue's accounting codes.
    LOCALISATION : Administration/admin/laboutik.py
    """
    compressed_fields = True
    warn_unsaved_form = True

    list_display = [
        'numero_de_compte', 'libelle_du_compte', 'nature_du_compte',
        'taux_de_tva', 'est_actif',
    ]
    list_filter = ['nature_du_compte', 'est_actif']
    search_fields = ['numero_de_compte', 'libelle_du_compte']
    ordering = ['numero_de_compte']

    list_before_template = "admin/comptable/changelist_before.html"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['charger_plan_url'] = '/laboutik/caisse/charger-plan-comptable/'
        return super().changelist_view(request, extra_context)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
```

- [ ] **Step 3: Ajouter MappingMoyenDePaiementAdmin**

```python
@admin.register(MappingMoyenDePaiement, site=staff_admin_site)
class MappingMoyenDePaiementAdmin(ModelAdmin):
    """
    Admin CRUD pour le mapping moyen de paiement → compte de tresorerie.
    / CRUD admin for payment method → treasury account mapping.
    LOCALISATION : Administration/admin/laboutik.py
    """
    compressed_fields = True
    warn_unsaved_form = True

    list_display = ['moyen_de_paiement', 'libelle_moyen', 'compte_de_tresorerie']
    autocomplete_fields = ['compte_de_tresorerie']

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)
```

- [ ] **Step 4: Ajouter le champ compte_comptable dans l'admin CategorieProduct**

Chercher l'admin de `CategorieProduct` (dans `Administration/admin/` ou `admin_tenant.py`) et ajouter `compte_comptable` dans ses fieldsets avec `autocomplete_fields`.

- [ ] **Step 5: Creer le template changelist_before pour CompteComptable**

```html
{% load i18n unfold %}
{# Bandeau chargement plan comptable par defaut #}
{# / Default chart of accounts loading banner #}

{% if charger_plan_url %}
<div class="p-4 flex flex-col gap-4" data-testid="bandeau-charger-plan">
    {% component "unfold/components/card.html" with title=_("Load a default chart of accounts") %}
        <div id="zone-charger-plan">
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 py-2">
                <span class="text-sm text-font-subtle-light dark:text-font-subtle-dark">
                    {% translate "Load preconfigured accounts for your type of venue." %}
                </span>
                <div class="flex gap-2 flex-shrink-0">
                    <button type="button"
                            hx-post="{{ charger_plan_url }}"
                            hx-vals='{"jeu": "bar_resto"}'
                            hx-target="#zone-charger-plan"
                            hx-swap="innerHTML"
                            hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'
                            class="font-medium flex items-center gap-2 px-4 py-2 rounded-default cursor-pointer bg-primary-600 text-white hover:bg-primary-700 transition-colors"
                            data-testid="btn-charger-bar-resto">
                        <span class="material-symbols-outlined" style="font-size: 18px;" aria-hidden="true">restaurant</span>
                        {% translate "Bar / Restaurant" %}
                    </button>
                    <button type="button"
                            hx-post="{{ charger_plan_url }}"
                            hx-vals='{"jeu": "association"}'
                            hx-target="#zone-charger-plan"
                            hx-swap="innerHTML"
                            hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'
                            class="font-medium flex items-center gap-2 px-4 py-2 rounded-default cursor-pointer bg-base-600 text-white hover:bg-base-700 transition-colors"
                            data-testid="btn-charger-association">
                        <span class="material-symbols-outlined" style="font-size: 18px;" aria-hidden="true">groups</span>
                        {% translate "Association / Community space" %}
                    </button>
                </div>
            </div>
        </div>
    {% endcomponent %}
</div>
{% endif %}
```

- [ ] **Step 6: Ajouter les entrees sidebar**

Dans la section "Caisse LaBoutik" de la sidebar, ajouter :

```python
{
    "title": _("Accounting codes"),
    "icon": "account_balance",
    "link": reverse_lazy("admin:laboutik_comptecomptable_changelist"),
},
{
    "title": _("Payment method mapping"),
    "icon": "swap_horiz",
    "link": reverse_lazy("admin:laboutik_mappingmoyendepaiement_changelist"),
},
```

- [ ] **Step 7: Verifier**

```bash
docker exec lespass_django poetry run python manage.py check
```

---

## Task 3 : Management command `charger_plan_comptable`

**Files:**
- Create: `laboutik/management/commands/charger_plan_comptable.py`

- [ ] **Step 1: Creer la command**

```python
"""
Charge un jeu de comptes comptables par defaut (bar/resto ou association).
/ Loads a default set of accounting codes (bar/restaurant or association).

LOCALISATION : laboutik/management/commands/charger_plan_comptable.py

Usage :
    docker exec lespass_django poetry run python manage.py charger_plan_comptable \
        --schema=lespass --jeu=bar_resto
"""
from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context

from Customers.models import Client


# Jeu "Bar / Restaurant" — 15 comptes
# / "Bar / Restaurant" fixture — 15 accounts
PLAN_BAR_RESTO = [
    {'numero': '7072000', 'libelle': 'Boissons a 20%', 'nature': 'VENTE', 'tva': '20.00'},
    {'numero': '7071000', 'libelle': 'Boissons a 10%', 'nature': 'VENTE', 'tva': '10.00'},
    {'numero': '7011000', 'libelle': 'Alimentaire a 10%', 'nature': 'VENTE', 'tva': '10.00'},
    {'numero': '7010500', 'libelle': 'Alimentaire a emporter 5,5%', 'nature': 'VENTE', 'tva': '5.50'},
    {'numero': '51120001', 'libelle': 'Paiement CB', 'nature': 'TRESORERIE', 'tva': None},
    {'numero': '5300000', 'libelle': 'Paiement Especes', 'nature': 'TRESORERIE', 'tva': None},
    {'numero': '51120002', 'libelle': 'Paiement Tickets Restaurants', 'nature': 'TRESORERIE', 'tva': None},
    {'numero': '51120000', 'libelle': 'Paiement en cheque', 'nature': 'TRESORERIE', 'tva': None},
    {'numero': '445712', 'libelle': 'TVA 20%', 'nature': 'TVA', 'tva': '20.00'},
    {'numero': '445710', 'libelle': 'TVA 10%', 'nature': 'TVA', 'tva': '10.00'},
    {'numero': '445705', 'libelle': 'TVA 5,5%', 'nature': 'TVA', 'tva': '5.50'},
    {'numero': '709000', 'libelle': 'Remises', 'nature': 'SPECIAL', 'tva': None},
    {'numero': '5811000', 'libelle': 'Caisse (mouvements especes)', 'nature': 'SPECIAL', 'tva': None},
    {'numero': '758000', 'libelle': 'Ecart de gestion +', 'nature': 'PRODUIT_EXCEPTIONNEL', 'tva': None},
    {'numero': '658000', 'libelle': 'Ecart de gestion -', 'nature': 'CHARGE', 'tva': None},
]

# Jeu "Association / Tiers-lieu" — 10 comptes
# / "Association / Community space" fixture — 10 accounts
PLAN_ASSOCIATION = [
    {'numero': '706000', 'libelle': 'Prestations de services', 'nature': 'VENTE', 'tva': '20.00'},
    {'numero': '707000', 'libelle': 'Ventes de marchandises', 'nature': 'VENTE', 'tva': '20.00'},
    {'numero': '706300', 'libelle': 'Billetterie', 'nature': 'VENTE', 'tva': '5.50'},
    {'numero': '756000', 'libelle': 'Cotisations', 'nature': 'VENTE', 'tva': None},
    {'numero': '512000', 'libelle': 'Banque', 'nature': 'TRESORERIE', 'tva': None},
    {'numero': '530000', 'libelle': 'Caisse', 'nature': 'TRESORERIE', 'tva': None},
    {'numero': '419100', 'libelle': 'Avances clients (cashless)', 'nature': 'TIERS', 'tva': None},
    {'numero': '445710', 'libelle': 'TVA collectee 20%', 'nature': 'TVA', 'tva': '20.00'},
    {'numero': '445712', 'libelle': 'TVA collectee 5,5%', 'nature': 'TVA', 'tva': '5.50'},
    {'numero': '709000', 'libelle': 'Remises', 'nature': 'SPECIAL', 'tva': None},
]

# Mapping moyens de paiement par defaut (commun aux 2 jeux)
# / Default payment method mapping (shared by both fixtures)
MAPPING_MOYENS_DEFAUT = [
    {'code': 'CA', 'libelle': 'Especes', 'compte_numero': '5300000'},
    {'code': 'CC', 'libelle': 'Carte bancaire', 'compte_numero': '51120001'},
    {'code': 'CH', 'libelle': 'Cheque', 'compte_numero': '51120000'},
    {'code': 'LE', 'libelle': 'Cashless (monnaie locale)', 'compte_numero': None},
    {'code': 'LG', 'libelle': 'Cashless (cadeau)', 'compte_numero': None},
    {'code': 'QR', 'libelle': 'QR/NFC', 'compte_numero': None},
    {'code': 'SN', 'libelle': 'Stripe en ligne', 'compte_numero': '51120001'},
    {'code': 'NA', 'libelle': 'Offert', 'compte_numero': None},
]


class Command(BaseCommand):
    help = 'Charge un plan comptable par defaut / Loads a default chart of accounts'

    def add_arguments(self, parser):
        parser.add_argument('--schema', type=str, required=True, help='Schema du tenant')
        parser.add_argument(
            '--jeu', type=str, required=True, choices=['bar_resto', 'association'],
            help='Jeu de comptes a charger (bar_resto ou association)',
        )
        parser.add_argument(
            '--reset', action='store_true',
            help='Supprime les comptes existants avant de charger',
        )

    def handle(self, *args, **options):
        schema = options['schema']
        jeu = options['jeu']
        reset = options['reset']

        try:
            Client.objects.get(schema_name=schema)
        except Client.DoesNotExist:
            raise CommandError(f"Tenant '{schema}' introuvable.")

        with schema_context(schema):
            from decimal import Decimal
            from laboutik.models import CompteComptable, MappingMoyenDePaiement

            # Garde anti-doublon
            # / Anti-duplicate guard
            nb_existants = CompteComptable.objects.count()
            if nb_existants > 0 and not reset:
                self.stdout.write(self.style.WARNING(
                    f"[{schema}] {nb_existants} comptes existent deja. "
                    f"Utilisez --reset pour les remplacer."
                ))
                return

            if reset:
                CompteComptable.objects.all().delete()
                MappingMoyenDePaiement.objects.all().delete()
                self.stdout.write(f"[{schema}] Comptes et mappings supprimes.")

            # Charger les comptes
            # / Load accounts
            plan = PLAN_BAR_RESTO if jeu == 'bar_resto' else PLAN_ASSOCIATION
            comptes_crees = {}
            for compte_data in plan:
                tva_value = Decimal(compte_data['tva']) if compte_data['tva'] else None
                compte = CompteComptable.objects.create(
                    numero_de_compte=compte_data['numero'],
                    libelle_du_compte=compte_data['libelle'],
                    nature_du_compte=compte_data['nature'],
                    taux_de_tva=tva_value,
                )
                comptes_crees[compte_data['numero']] = compte

            self.stdout.write(self.style.SUCCESS(
                f"[{schema}] {len(plan)} comptes charges (jeu: {jeu})"
            ))

            # Charger les mappings moyens de paiement
            # Le numero de compte utilise depend du jeu :
            # - bar_resto : 51120001 (CB), 51120000 (cheque), 5300000 (especes)
            # - association : 512000 (banque = CB+Stripe), 530000 (caisse = especes)
            # / Payment method mappings depend on the fixture:
            nb_mappings = 0
            for mapping_data in MAPPING_MOYENS_DEFAUT:
                compte_numero = mapping_data['compte_numero']
                compte_obj = None
                if compte_numero:
                    compte_obj = comptes_crees.get(compte_numero)
                    if not compte_obj:
                        # Chercher par numero dans la base (peut exister d'un autre jeu)
                        # / Look up by number in DB (may exist from another fixture)
                        compte_obj = CompteComptable.objects.filter(
                            numero_de_compte=compte_numero,
                        ).first()

                MappingMoyenDePaiement.objects.create(
                    moyen_de_paiement=mapping_data['code'],
                    libelle_moyen=mapping_data['libelle'],
                    compte_de_tresorerie=compte_obj,
                )
                nb_mappings += 1

            self.stdout.write(self.style.SUCCESS(
                f"[{schema}] {nb_mappings} mappings moyens de paiement charges"
            ))
```

- [ ] **Step 2: Verifier**

```bash
docker exec lespass_django poetry run python manage.py charger_plan_comptable --help
```

---

## Task 4 : Generateur FEC

**Files:**
- Create: `laboutik/fec.py`

- [ ] **Step 1: Creer le module**

```python
"""
Generateur de fichier FEC (Fichier des Ecritures Comptables).
Format obligatoire en France, accepte par : PennyLane, Odoo, EBP Hubbix, Paheko, Sage.
/ FEC (Fichier des Ecritures Comptables) file generator.
Mandatory format in France, accepted by: PennyLane, Odoo, EBP Hubbix, Paheko, Sage.

LOCALISATION : laboutik/fec.py

Chaque cloture (ticket Z) = 1 ecriture comptable equilibree.
Debits (moyens de paiement) = Credits (ventes HT + TVA).
/ Each closure (Z-ticket) = 1 balanced accounting entry.
Debits (payment methods) = Credits (sales excl. tax + VAT).
"""
import io
from decimal import Decimal

from django.utils.translation import gettext_lazy as _

from BaseBillet.models import CategorieProduct, Configuration
from laboutik.models import CompteComptable, MappingMoyenDePaiement


# En-tetes des 18 colonnes FEC
# / 18-column FEC headers
ENTETES_FEC = [
    'JournalCode', 'JournalLib', 'EcritureNum', 'EcritureDate',
    'CompteNum', 'CompteLib', 'CompAuxNum', 'CompAuxLib',
    'PieceRef', 'PieceDate', 'EcritureLib',
    'Debit', 'Credit',
    'EcritureLet', 'DateLet', 'ValidDate',
    'Montantdevise', 'Idevise',
]


def _formater_montant(centimes):
    """
    Convertit des centimes (int) en string avec virgule decimale.
    Ex: 15000 → "150,00" ; 0 → "0,00"
    / Converts cents (int) to string with comma decimal separator.
    """
    euros = Decimal(centimes) / 100
    return f"{euros:.2f}".replace('.', ',')


def _formater_date(dt):
    """
    Formate un datetime en AAAAMMJJ (sans separateur).
    Ex: 2026-03-31 14:30 → "20260331"
    / Formats a datetime as YYYYMMDD (no separator).
    """
    return dt.strftime('%Y%m%d')


def _generer_ligne_fec(
    code_journal, libelle_journal,
    numero_ecriture, date_ecriture,
    numero_compte, libelle_compte,
    reference_piece, libelle_ecriture,
    montant_debit_centimes, montant_credit_centimes,
    date_validation,
):
    """
    Genere une ligne FEC (18 champs separes par tabulation).
    / Generates one FEC line (18 tab-separated fields).

    LOCALISATION : laboutik/fec.py
    """
    les_18_champs = [
        code_journal,                                   # 1. JournalCode
        libelle_journal,                                # 2. JournalLib
        numero_ecriture,                                # 3. EcritureNum
        _formater_date(date_ecriture),                  # 4. EcritureDate
        numero_compte,                                  # 5. CompteNum
        libelle_compte,                                 # 6. CompteLib
        '',                                             # 7. CompAuxNum (vide)
        '',                                             # 8. CompAuxLib (vide)
        reference_piece,                                # 9. PieceRef
        _formater_date(date_ecriture),                  # 10. PieceDate
        libelle_ecriture,                               # 11. EcritureLib
        _formater_montant(montant_debit_centimes),      # 12. Debit
        _formater_montant(montant_credit_centimes),     # 13. Credit
        '',                                             # 14. EcritureLet (vide)
        '',                                             # 15. DateLet (vide)
        _formater_date(date_validation),                # 16. ValidDate
        '',                                             # 17. Montantdevise (vide)
        '',                                             # 18. Idevise (vide)
    ]
    return '\t'.join(les_18_champs)


def generer_fec(clotures_queryset, schema_name):
    """
    Genere un fichier FEC complet a partir d'un queryset de ClotureCaisse.
    Chaque cloture = 1 ecriture comptable equilibree (debits = credits).
    / Generates a complete FEC file from a ClotureCaisse queryset.
    Each closure = 1 balanced accounting entry (debits = credits).

    LOCALISATION : laboutik/fec.py

    :param clotures_queryset: QuerySet de ClotureCaisse, ordonne par datetime_cloture
    :param schema_name: str — schema tenant (pour le nom du fichier)
    :return: tuple (bytes contenu_fec, str nom_fichier, list avertissements)
    """
    config = Configuration.get_solo()

    # Charger tous les mappings moyens de paiement (en memoire, peu d'enregistrements)
    # / Load all payment method mappings (in memory, few records)
    mappings_moyens = {}
    for mapping in MappingMoyenDePaiement.objects.select_related('compte_de_tresorerie').all():
        mappings_moyens[mapping.moyen_de_paiement] = mapping

    # Charger les comptes TVA (lookup par taux)
    # / Load VAT accounts (lookup by rate)
    comptes_tva = {}
    for compte in CompteComptable.objects.filter(nature_du_compte=CompteComptable.TVA, est_actif=True):
        cle_tva = f"{float(compte.taux_de_tva):.2f}" if compte.taux_de_tva else None
        if cle_tva:
            comptes_tva[cle_tva] = compte

    avertissements = []
    lignes_fec = []

    # En-tete
    # / Header
    lignes_fec.append('\t'.join(ENTETES_FEC))

    code_journal = 'VE'
    libelle_journal = 'Journal de ventes'

    for cloture in clotures_queryset.order_by('datetime_cloture'):
        rapport = cloture.rapport_json or {}
        date_cloture = cloture.datetime_cloture
        num_seq = cloture.numero_sequentiel or 0
        date_str = _formater_date(date_cloture)

        numero_ecriture = f"VE-{date_str}-{num_seq:03d}"
        reference_piece = f"Z-{date_str}-{num_seq:03d}"

        total_debits = 0
        total_credits = 0

        # --- DEBITS : moyens de paiement ---
        # / --- DEBITS: payment methods ---
        totaux_par_moyen = rapport.get('totaux_par_moyen', {})

        # Especes / Cash
        montant_especes = totaux_par_moyen.get('especes', 0)
        if montant_especes > 0:
            mapping = mappings_moyens.get('CA')
            if mapping and mapping.compte_de_tresorerie:
                compte = mapping.compte_de_tresorerie
                lignes_fec.append(_generer_ligne_fec(
                    code_journal, libelle_journal,
                    numero_ecriture, date_cloture,
                    compte.numero_de_compte, compte.libelle_du_compte,
                    reference_piece,
                    f"Encaissement especes du {date_cloture.strftime('%d/%m/%Y')}",
                    montant_especes, 0,
                    date_cloture,
                ))
                total_debits += montant_especes

        # Carte bancaire / Credit card
        montant_cb = totaux_par_moyen.get('carte_bancaire', 0)
        if montant_cb > 0:
            mapping = mappings_moyens.get('CC')
            if mapping and mapping.compte_de_tresorerie:
                compte = mapping.compte_de_tresorerie
                lignes_fec.append(_generer_ligne_fec(
                    code_journal, libelle_journal,
                    numero_ecriture, date_cloture,
                    compte.numero_de_compte, compte.libelle_du_compte,
                    reference_piece,
                    f"Encaissement CB du {date_cloture.strftime('%d/%m/%Y')}",
                    montant_cb, 0,
                    date_cloture,
                ))
                total_debits += montant_cb

        # Cheque / Check
        montant_cheque = totaux_par_moyen.get('cheque', 0)
        if montant_cheque > 0:
            mapping = mappings_moyens.get('CH')
            if mapping and mapping.compte_de_tresorerie:
                compte = mapping.compte_de_tresorerie
                lignes_fec.append(_generer_ligne_fec(
                    code_journal, libelle_journal,
                    numero_ecriture, date_cloture,
                    compte.numero_de_compte, compte.libelle_du_compte,
                    reference_piece,
                    f"Encaissement cheque du {date_cloture.strftime('%d/%m/%Y')}",
                    montant_cheque, 0,
                    date_cloture,
                ))
                total_debits += montant_cheque

        # Cashless (NFC) — ignore si mapping null
        # / Cashless (NFC) — ignored if mapping null
        montant_cashless = totaux_par_moyen.get('cashless', 0)
        if montant_cashless > 0:
            mapping_le = mappings_moyens.get('LE')
            if mapping_le and mapping_le.compte_de_tresorerie:
                compte = mapping_le.compte_de_tresorerie
                lignes_fec.append(_generer_ligne_fec(
                    code_journal, libelle_journal,
                    numero_ecriture, date_cloture,
                    compte.numero_de_compte, compte.libelle_du_compte,
                    reference_piece,
                    f"Encaissement cashless du {date_cloture.strftime('%d/%m/%Y')}",
                    montant_cashless, 0,
                    date_cloture,
                ))
                total_debits += montant_cashless

        # --- CREDITS : ventes HT par categorie ---
        # / --- CREDITS: sales excl. tax by category ---
        detail_ventes = rapport.get('detail_ventes', {})

        for nom_categorie, donnees_categorie in detail_ventes.items():
            articles = donnees_categorie.get('articles', [])
            total_ht_categorie = 0

            for article in articles:
                total_ht_categorie += article.get('total_ht', 0)

            if total_ht_categorie <= 0:
                continue

            # Chercher le compte comptable de la categorie
            # / Look up the category's accounting code
            categorie_obj = CategorieProduct.objects.filter(
                name=nom_categorie,
            ).select_related('compte_comptable').first()

            if categorie_obj and categorie_obj.compte_comptable:
                compte = categorie_obj.compte_comptable
            else:
                # Categorie non mappee : compte generique + warning
                # / Unmapped category: generic account + warning
                avertissements.append(
                    f"Categorie '{nom_categorie}' sans compte comptable"
                )
                compte = None

            numero_compte = compte.numero_de_compte if compte else '000000'
            libelle_compte = compte.libelle_du_compte if compte else f'** {nom_categorie} (NON MAPPE) **'

            lignes_fec.append(_generer_ligne_fec(
                code_journal, libelle_journal,
                numero_ecriture, date_cloture,
                numero_compte, libelle_compte,
                reference_piece,
                f"Ventes {nom_categorie} du {date_cloture.strftime('%d/%m/%Y')}",
                0, total_ht_categorie,
                date_cloture,
            ))
            total_credits += total_ht_categorie

        # --- CREDITS : TVA par taux ---
        # / --- CREDITS: VAT by rate ---
        tva_data = rapport.get('tva', {})

        for cle_tva, donnees_tva in tva_data.items():
            montant_tva = donnees_tva.get('total_tva', 0)
            taux = donnees_tva.get('taux', 0)

            if montant_tva <= 0:
                continue

            taux_cle = f"{float(taux):.2f}"
            compte_tva = comptes_tva.get(taux_cle)

            if compte_tva:
                numero_compte = compte_tva.numero_de_compte
                libelle_compte = compte_tva.libelle_du_compte
            else:
                avertissements.append(
                    f"Pas de compte TVA pour le taux {taux}%"
                )
                numero_compte = '000000'
                libelle_compte = f'** TVA {taux}% (NON MAPPE) **'

            lignes_fec.append(_generer_ligne_fec(
                code_journal, libelle_journal,
                numero_ecriture, date_cloture,
                numero_compte, libelle_compte,
                reference_piece,
                f"TVA {taux}% du {date_cloture.strftime('%d/%m/%Y')}",
                0, montant_tva,
                date_cloture,
            ))
            total_credits += montant_tva

    # Assembler le fichier : CRLF, encodage UTF-8
    # / Assemble the file: CRLF, UTF-8 encoding
    contenu = '\r\n'.join(lignes_fec) + '\r\n'
    contenu_bytes = contenu.encode('utf-8')

    # Nom du fichier : {SIREN}FEC{AAAAMMJJ}.txt
    # / Filename: {SIREN}FEC{YYYYMMDD}.txt
    siren = config.siren or 'XXXXXXXXX'
    derniere_cloture = clotures_queryset.order_by('-datetime_cloture').first()
    date_fin = derniere_cloture.datetime_cloture if derniere_cloture else None
    date_label = _formater_date(date_fin) if date_fin else '00000000'
    nom_fichier = f"{siren}FEC{date_label}.txt"

    return (contenu_bytes, nom_fichier, avertissements)
```

- [ ] **Step 2: Verifier l'import**

```bash
docker exec lespass_django poetry run python -c "import laboutik.fec; print('OK')"
```

---

## Task 5 : ViewSet actions (export FEC + charger plan)

**Files:**
- Modify: `laboutik/views.py`
- Create: `Administration/templates/admin/cloture/export_fec_form.html`

- [ ] **Step 1: Ajouter l'action charger_plan_comptable dans CaisseViewSet**

Apres l'action `export_fiscal`, ajouter :

```python
    @action(detail=False, methods=["post"], url_path="charger-plan-comptable", url_name="charger_plan_comptable")
    def charger_plan_comptable(self, request):
        """
        POST /laboutik/caisse/charger-plan-comptable/
        Charge un jeu de comptes comptables par defaut.
        Appele depuis le bouton HTMX dans l'admin CompteComptable.
        / Loads a default set of accounting codes.
        Called from the HTMX button in the CompteComptable admin.

        LOCALISATION : laboutik/views.py
        """
        from django.core.management import call_command
        from django.db import connection
        from django.http import HttpResponse

        jeu = request.POST.get('jeu', '')
        if jeu not in ('bar_resto', 'association'):
            return HttpResponse(
                '<span class="text-red-500">Jeu invalide.</span>',
                status=400,
            )

        schema = connection.schema_name

        try:
            call_command('charger_plan_comptable', schema=schema, jeu=jeu)
        except Exception as e:
            return HttpResponse(
                f'<span class="text-red-500">Erreur : {e}</span>',
                status=500,
            )

        return HttpResponse(
            '<div class="py-2">'
            '<span class="text-green-600 dark:text-green-400 font-medium">'
            f'<span class="material-symbols-outlined align-middle" style="font-size:18px;">check_circle</span> '
            f'Plan comptable "{jeu}" charge avec succes. '
            f'<a href="." class="underline">Rafraichir la page</a>'
            '</span></div>'
        )
```

- [ ] **Step 2: Ajouter l'action export_fec dans CaisseViewSet**

```python
    @action(detail=False, methods=["get", "post"], url_path="export-fec", url_name="export_fec")
    def export_fec(self, request):
        """
        GET /laboutik/caisse/export-fec/
        Formulaire dates debut/fin.
        POST /laboutik/caisse/export-fec/
        Genere et telecharge le fichier FEC.
        / GET: date form. POST: generates and downloads FEC file.

        LOCALISATION : laboutik/views.py
        """
        from datetime import date as date_type

        from django.db import connection
        from django.http import HttpResponse

        from laboutik.fec import generer_fec
        from laboutik.models import ClotureCaisse

        if request.method == "GET":
            est_requete_htmx = request.headers.get('HX-Request') == 'true'
            if est_requete_htmx:
                return render(request, "admin/cloture/export_fec_form.html", {
                    "form_action_url": request.path,
                })
            return render(request, "laboutik/partial/hx_export_fiscal.html")

        # POST : generer le FEC
        # / POST: generate FEC
        debut = None
        fin = None
        debut_str = request.POST.get('debut', '').strip()
        fin_str = request.POST.get('fin', '').strip()
        try:
            if debut_str:
                debut = date_type.fromisoformat(debut_str)
            if fin_str:
                fin = date_type.fromisoformat(fin_str)
        except ValueError:
            return HttpResponse("Format de date invalide.", status=400)

        # Construire le queryset de clotures
        # / Build the closures queryset
        filtres = {'niveau': ClotureCaisse.JOURNALIERE}
        if debut:
            filtres['datetime_cloture__date__gte'] = debut
        if fin:
            filtres['datetime_cloture__date__lte'] = fin

        clotures = ClotureCaisse.objects.filter(**filtres)

        if not clotures.exists():
            return HttpResponse("Aucune cloture journaliere pour cette periode.", status=404)

        schema = connection.schema_name
        contenu_bytes, nom_fichier, avertissements = generer_fec(clotures, schema)

        response = HttpResponse(contenu_bytes, content_type='text/plain; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{nom_fichier}"'
        return response
```

- [ ] **Step 3: Creer le template formulaire FEC HTMX**

`Administration/templates/admin/cloture/export_fec_form.html` — meme structure que `export_fiscal_form.html` :

```html
{% load i18n %}
<div class="py-3" data-testid="export-fec-form"
     style="animation: fadeSlideIn 300ms ease both;">
    <style>
        @keyframes fadeSlideIn {
            from { opacity: 0; transform: translateY(-6px); }
        }
    </style>
    <form method="post" action="{{ form_action_url }}"
          aria-label="{% translate 'FEC export' %}" class="flex flex-col gap-4">
        {% csrf_token %}
        <div class="flex flex-col sm:flex-row gap-3">
            <div class="flex-1">
                <label for="id_debut_fec"
                       class="block text-xs font-medium text-font-subtle-light dark:text-font-subtle-dark mb-1">
                    {% translate "Start date" %}
                    <span class="text-base-400 dark:text-base-500 font-normal ml-1">({% translate "optional" %})</span>
                </label>
                <input type="date" id="id_debut_fec" name="debut"
                       class="w-full px-3 py-2 text-sm rounded-default border border-base-200 dark:border-base-700 bg-white dark:bg-base-900 text-font-default-light dark:text-font-default-dark focus:outline-none focus:ring-2 focus:ring-primary-500 transition-colors"
                       data-testid="export-fec-debut">
            </div>
            <div class="flex-1">
                <label for="id_fin_fec"
                       class="block text-xs font-medium text-font-subtle-light dark:text-font-subtle-dark mb-1">
                    {% translate "End date" %}
                    <span class="text-base-400 dark:text-base-500 font-normal ml-1">({% translate "optional" %})</span>
                </label>
                <input type="date" id="id_fin_fec" name="fin"
                       class="w-full px-3 py-2 text-sm rounded-default border border-base-200 dark:border-base-700 bg-white dark:bg-base-900 text-font-default-light dark:text-font-default-dark focus:outline-none focus:ring-2 focus:ring-primary-500 transition-colors"
                       data-testid="export-fec-fin">
            </div>
        </div>
        <p class="text-xs text-base-400 dark:text-base-500">
            {% translate "FEC format: 18 tab-separated columns, accepted by PennyLane, Odoo, EBP Hubbix, Paheko, Sage." %}
        </p>
        <div class="flex items-center gap-3">
            <button type="submit"
                    class="font-medium flex items-center gap-2 px-5 py-2.5 rounded-default cursor-pointer bg-primary-600 text-white hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 transition-colors"
                    data-testid="export-fec-submit">
                <span class="material-symbols-outlined" style="font-size: 18px;" aria-hidden="true">download</span>
                {% translate "Download FEC" %}
            </button>
            <button type="button" onclick="window.location.reload()"
                    class="text-sm text-font-subtle-light dark:text-font-subtle-dark hover:text-font-default-light dark:hover:text-font-default-dark transition-colors cursor-pointer"
                    data-testid="export-fec-cancel">
                {% translate "Cancel" %}
            </button>
        </div>
    </form>
</div>
```

- [ ] **Step 4: Ajouter le bouton FEC dans le bandeau des clotures**

Dans `Administration/templates/admin/cloture/changelist_before.html`, ajouter un 2e bouton a cote de "Export fiscal" :

```html
                <button type="button"
                        hx-get="/laboutik/caisse/export-fec/"
                        hx-target="#export-fiscal-zone"
                        hx-swap="innerHTML"
                        class="font-medium flex items-center gap-2 px-5 py-2.5 rounded-default justify-center whitespace-nowrap cursor-pointer bg-base-600 text-white hover:bg-base-700 focus:outline-none focus:ring-2 focus:ring-base-500 focus:ring-offset-2 dark:focus:ring-offset-base-900 transition-colors flex-shrink-0"
                        data-testid="btn-export-fec">
                    <span class="material-symbols-outlined" style="font-size: 18px;" aria-hidden="true">description</span>
                    {% translate "Export FEC" %}
                </button>
```

- [ ] **Step 5: Verifier**

```bash
docker exec lespass_django poetry run python manage.py check
```

---

## Task 6 : Tests

**Files:**
- Create: `tests/pytest/test_export_comptable.py`

- [ ] **Step 1: Creer le fichier de test**

Le fichier doit :
- Utiliser FastTenantTestCase (meme pattern que test_archivage_fiscal.py)
- Creer les donnees minimales dans setUp (categorie, produit, prix, PV, LigneArticle, ClotureCaisse)
- Charger un jeu de comptes via call_command
- Tester le generateur FEC

11 tests couvrant : modeles, fixtures, generateur FEC (colonnes, equilibre, format), categorie non mappee, moyen ignore.

Commencer par lire `tests/pytest/test_archivage_fiscal.py` pour le pattern exact, puis creer `tests/pytest/test_export_comptable.py` avec les memes fixtures + les tests specifiques session 20.

- [ ] **Step 2: Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_export_comptable.py -v
```

- [ ] **Step 3: Non-regression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_archivage_fiscal.py tests/pytest/test_corrections_fond_sortie.py tests/pytest/test_envoi_rapports_version.py tests/pytest/test_export_comptable.py -v
```

---

## Task 7 : Documentation utilisateur

**Files:**
- Create: `TECH DOC/A DOCUMENTER/export-comptable-guide-utilisateur.md`

Sections :
1. **C'est quoi un compte comptable ?** — explication debutant (classes, debit=credit, exemple vente biere)
2. **Pourquoi configurer un mapping ?** — pour que le comptable importe directement
3. **Etape 1 : charger un plan par defaut** — bouton admin ou commande
4. **Etape 2 : verifier les comptes** — liste admin, modifier si besoin
5. **Etape 3 : mapper les categories** — dans l'admin de chaque categorie, choisir le compte de vente
6. **Etape 4 : mapper les moyens de paiement** — dans l'admin mapping, lier chaque moyen a un compte (ou ignorer)
7. **Etape 5 : exporter le FEC** — bouton dans les clotures, choisir la periode
8. **FAQ** — cashless (ignore par defaut), remises, ecarts, categories sans mapping, format FEC

---

## Task 8 : Verification finale

- [ ] **Step 1: Ruff**

```bash
docker exec lespass_django poetry run ruff check --fix laboutik/models.py laboutik/fec.py laboutik/views.py laboutik/management/commands/charger_plan_comptable.py Administration/admin/laboutik.py
docker exec lespass_django poetry run ruff format laboutik/models.py laboutik/fec.py laboutik/views.py laboutik/management/commands/charger_plan_comptable.py Administration/admin/laboutik.py
```

- [ ] **Step 2: Django check**

```bash
docker exec lespass_django poetry run python manage.py check
```

- [ ] **Step 3: Tests complets**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_export_comptable.py tests/pytest/test_archivage_fiscal.py tests/pytest/test_corrections_fond_sortie.py tests/pytest/test_cloture_caisse.py tests/pytest/test_cloture_enrichie.py tests/pytest/test_cloture_export.py tests/pytest/test_envoi_rapports_version.py -v
```
