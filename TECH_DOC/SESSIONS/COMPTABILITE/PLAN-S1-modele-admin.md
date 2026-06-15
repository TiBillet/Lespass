# Plan d'implémentation — S1 (Chantier 01 / App `comptabilite`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Hub documentaire :** [`INDEX.md`](INDEX.md) — **Spec source :** [`SPEC.md`](SPEC.md) (sections 2, 5.1, 5.3)
>
> **Garde-fous projet (rappel maintainer) :**
> - **JAMAIS d'opération `git` (commit/add/push/checkout --/stash/reset/clean)**. Les étapes « Commit » de ce plan OUTPUTENT un message de commit suggéré pour que le mainteneur l'exécute lui-même.
> - **Ne pas lancer `runserver_plus`** — le serveur tourne déjà dans byobu sur le port 8002.
> - **Pas de `ruff format` sur fichiers existants** — uniquement sur fichiers neufs créés par ce plan.

**Goal :** Squelette de l'app Django `comptabilite/` avec le modèle `ClotureCaisse`, sa migration, l'admin Unfold read-only minimal, et l'entrée sidebar — page `/admin/comptabilite/cloturecaisse/` accessible et vide.

**Architecture :** Nouvelle app dans `TENANT_APPS` (1 table par schéma tenant). Modèle immuable (no add/change/delete depuis l'admin). Permission via `TenantAdminPermissionWithRequest` partagé avec les autres ModelAdmins. Sidebar conditionnelle via `Administration/admin/dashboard.py:get_sidebar_navigation()`.

**Tech Stack :** Django 5.x, django-tenants, django-unfold, pytest, pytest-django, multi-tenant (schema isolation).

---

## File structure produite par S1

```
comptabilite/
├── __init__.py                                     # nouveau (vide)
├── apps.py                                         # nouveau (AppConfig)
├── models.py                                       # nouveau (ClotureCaisse)
├── admin.py                                        # nouveau (ClotureCaisseAdmin)
└── migrations/
    ├── __init__.py                                 # nouveau (vide)
    └── 0001_initial.py                             # généré par makemigrations

BaseBillet/
├── models.py                                       # MODIFIÉ (+2 champs sur Configuration)
└── migrations/
    └── 00XX_configuration_rapport_emails.py        # généré par makemigrations

Administration/
└── admin/
    └── dashboard.py                                # MODIFIÉ (entrée sidebar)

TiBillet/
└── settings.py                                     # MODIFIÉ (+'comptabilite' dans TENANT_APPS)

tests/
└── pytest/
    └── test_comptabilite_admin.py                  # nouveau (tests smoke)
```

---

## Task 1 — Squelette de l'app `comptabilite`

**Files :**
- Create: `comptabilite/__init__.py`
- Create: `comptabilite/apps.py`

- [ ] **Step 1.1 — Créer `comptabilite/__init__.py` (fichier vide)**

```bash
mkdir -p /home/jonas/TiBillet/dev/Lespass/comptabilite
touch /home/jonas/TiBillet/dev/Lespass/comptabilite/__init__.py
```

- [ ] **Step 1.2 — Créer `comptabilite/apps.py`**

```python
"""
Configuration de l'app comptabilite.
/ Configuration of the comptabilite app.

LOCALISATION : comptabilite/apps.py

App tenant qui hebergera : ClotureCaisse (cloture comptable),
CompteComptable et MappingMoyenDePaiement (plan comptable parametrable, en S5).
/ Tenant app hosting: ClotureCaisse (accounting closure), and later
CompteComptable + MappingMoyenDePaiement (configurable accounting plan, S5).
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ComptabiliteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "comptabilite"
    verbose_name = _("Accounting")
```

- [ ] **Step 1.3 — Créer `comptabilite/migrations/__init__.py` (fichier vide)**

```bash
mkdir -p /home/jonas/TiBillet/dev/Lespass/comptabilite/migrations
touch /home/jonas/TiBillet/dev/Lespass/comptabilite/migrations/__init__.py
```

- [ ] **Step 1.4 — Verifier la structure**

```bash
ls /home/jonas/TiBillet/dev/Lespass/comptabilite/
```

Attendu :
```
__init__.py  apps.py  migrations
```

---

## Task 2 — Ajouter `comptabilite` dans `TENANT_APPS`

**Files :**
- Modify: `TiBillet/settings.py:172-187`

- [ ] **Step 2.1 — Modifier `TENANT_APPS`**

Dans `/home/jonas/TiBillet/dev/Lespass/TiBillet/settings.py`, remplacer la section :

```python
TENANT_APPS = (
    # The following Django contrib apps must be in TENANT_APPS
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',

    'rest_framework_api_key',
    # your tenant-specific apps
    'BaseBillet',
    'ApiBillet',
    'api_v2',
    'PaiementStripe',
    'wsocket',
    'tibrss',
    'fedow_connect',
    'crowds',
)
```

par :

```python
TENANT_APPS = (
    # The following Django contrib apps must be in TENANT_APPS
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',

    'rest_framework_api_key',
    # your tenant-specific apps
    'BaseBillet',
    'ApiBillet',
    'api_v2',
    'PaiementStripe',
    'wsocket',
    'tibrss',
    'fedow_connect',
    'crowds',
    'comptabilite',
)
```

- [ ] **Step 2.2 — Verifier que Django importe correctement l'app**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues (0 silenced).`

(L'app est encore vide, mais Django doit pouvoir la charger.)

---

## Task 3 — Tests d'unite pour le modele `ClotureCaisse`

**Files :**
- Create: `tests/pytest/test_comptabilite_admin.py`

- [ ] **Step 3.1 — Ecrire le test du modele AVANT l'implementation (TDD)**

Creer `/home/jonas/TiBillet/dev/Lespass/tests/pytest/test_comptabilite_admin.py` :

```python
"""
Tests smoke S1 — modele ClotureCaisse + admin Unfold.
/ Smoke tests S1 — ClotureCaisse model + Unfold admin.

LOCALISATION : tests/pytest/test_comptabilite_admin.py

S1 livre uniquement le squelette : modele, migration, admin liste vide,
entree sidebar. Ces tests verifient qu'on peut creer une cloture en base
et que la page admin se charge.
/ S1 only delivers the skeleton: model, migration, empty admin list,
sidebar entry. These tests verify we can create a closure and that
the admin page loads.
"""
import pytest
from django.urls import reverse
from django_tenants.utils import tenant_context, schema_context


pytestmark = pytest.mark.django_db


def test_app_comptabilite_dans_installed_apps():
    """
    L'app comptabilite est bien chargee par Django (presente dans INSTALLED_APPS).
    / The comptabilite app is properly loaded by Django.
    """
    from django.apps import apps
    assert apps.is_installed("comptabilite"), (
        "L'app 'comptabilite' n'est pas dans INSTALLED_APPS"
    )


def test_modele_cloturecaisse_creation_minimale(db):
    """
    On peut creer une ClotureCaisse minimale dans un schema tenant.
    / We can create a minimal ClotureCaisse in a tenant schema.
    """
    from Customers.models import Client
    tenant = Client.objects.exclude(schema_name="public").first()
    assert tenant is not None, "Aucun tenant non-public disponible pour le test"

    from django.utils import timezone
    from datetime import timedelta

    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse

        debut = timezone.now() - timedelta(days=1)
        fin = timezone.now()

        cloture = ClotureCaisse.objects.create(
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            numero_sequentiel=1,
            datetime_debut=debut,
            datetime_fin=fin,
        )

        assert cloture.pk is not None
        assert cloture.numero_sequentiel == 1
        assert cloture.niveau == "J"
        assert cloture.total_general == 0
        assert cloture.rapport_json == {}


def test_modele_cloturecaisse_unique_numero_sequentiel(db):
    """
    Le numero sequentiel est unique globalement par tenant.
    / Sequential number is globally unique per tenant.
    """
    from Customers.models import Client
    tenant = Client.objects.exclude(schema_name="public").first()

    from django.utils import timezone
    from datetime import timedelta
    from django.db import IntegrityError

    with tenant_context(tenant):
        from comptabilite.models import ClotureCaisse

        debut = timezone.now() - timedelta(days=2)
        fin1 = timezone.now() - timedelta(days=1)

        ClotureCaisse.objects.create(
            niveau="J", numero_sequentiel=42,
            datetime_debut=debut, datetime_fin=fin1,
        )

        # Tentative de creer une 2eme cloture avec le meme numero
        # / Attempt to create a 2nd closure with the same number
        with pytest.raises(IntegrityError):
            ClotureCaisse.objects.create(
                niveau="H", numero_sequentiel=42,  # meme numero
                datetime_debut=debut,
                datetime_fin=timezone.now(),
            )
```

- [ ] **Step 3.2 — Lancer les tests pour verifier qu'ils echouent (RED)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_comptabilite_admin.py -v
```

Attendu : `test_app_comptabilite_dans_installed_apps` PASSE (l'app est dans TENANT_APPS depuis Task 2), les 2 autres tests `test_modele_cloturecaisse_*` ÉCHOUENT avec `ModuleNotFoundError: No module named 'comptabilite.models'` ou similaire.

---

## Task 4 — Implementer le modele `ClotureCaisse`

**Files :**
- Create: `comptabilite/models.py`

- [ ] **Step 4.1 — Creer `comptabilite/models.py`**

Ecrire le contenu suivant dans `/home/jonas/TiBillet/dev/Lespass/comptabilite/models.py` :

```python
"""
Modeles de l'app comptabilite.
/ Models of the comptabilite app.

LOCALISATION : comptabilite/models.py

Modele principal : ClotureCaisse.
Une cloture est un instantane agrege des ventes (reservations + adhesions)
sur une periode fermee [datetime_debut, datetime_fin]. Elle stocke un dict
complet (rapport_json) qui permet de regenerer tout le PDF/Excel/CSV/FEC
sans recalculer depuis les LigneArticle.

Le numero_sequentiel est CONTINU GLOBAL par tenant : toutes les clotures
(J + H + M + A) partagent le meme compteur incremental. Conformite LNE V2.

/ Main model: ClotureCaisse. A closure is an aggregated snapshot of sales
(reservations + memberships) for a closed period. Sequential number is
continuous global per tenant (all periodicities share one counter).
"""
import uuid as uuid_lib

from django.db import models
from django.utils.translation import gettext_lazy as _


class ClotureCaisse(models.Model):
    NIVEAU_JOURNALIER = "J"
    NIVEAU_HEBDOMADAIRE = "H"
    NIVEAU_MENSUEL = "M"
    NIVEAU_ANNUEL = "A"
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
        unique=True,
        verbose_name=_("Sequential number"),
        help_text=_(
            "Continuous global counter per tenant (LNE compliance). "
            "Shared across all periodicities (daily, weekly, monthly, yearly)."
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
            "SHA-256 of sorted (pk, amount, qty, status) tuples of every "
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
        ]

    def __str__(self):
        return f"{self.get_niveau_display()} #{self.numero_sequentiel} — {self.datetime_fin:%Y-%m-%d}"
```

- [ ] **Step 4.2 — Verifier qu'aucune migration n'est manquante au-dela de celle a creer**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues (0 silenced).`

---

## Task 5 — Generer et appliquer la migration `comptabilite/0001_initial`

**Files :**
- Create (généré) : `comptabilite/migrations/0001_initial.py`

- [ ] **Step 5.1 — Generer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations comptabilite
```

Attendu :
```
Migrations for 'comptabilite':
  comptabilite/migrations/0001_initial.py
    + Create model ClotureCaisse
```

- [ ] **Step 5.2 — Inspecter le fichier de migration genere**

```bash
cat /home/jonas/TiBillet/dev/Lespass/comptabilite/migrations/0001_initial.py
```

Verifier qu'il y a bien :
- `migrations.CreateModel(name="ClotureCaisse", ...)` avec tous les champs
- `dependencies = [("AuthBillet", "...")]` (a cause de la FK responsable)
- L'index sur `niveau, -datetime_fin`
- L'index sur `-numero_sequentiel`
- Le `UniqueConstraint` `unique_cloture_periode`

- [ ] **Step 5.3 — Appliquer la migration sur tous les schemas tenant**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
```

Attendu : pour chaque schema tenant, la ligne `Applying comptabilite.0001_initial... OK`. Pas d'erreur.

- [ ] **Step 5.4 — Relancer les tests modele**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_comptabilite_admin.py::test_modele_cloturecaisse_creation_minimale tests/pytest/test_comptabilite_admin.py::test_modele_cloturecaisse_unique_numero_sequentiel -v
```

Attendu : les 2 tests PASSENT (GREEN).

---

## Task 6 — Ajouter `rapport_emails` et `rapport_periodicite` sur `Configuration`

**Files :**
- Modify: `BaseBillet/models.py:546-555` (ajout apres `module_crowdfunding`)
- Create (généré) : `BaseBillet/migrations/00XX_configuration_rapport_emails.py`

- [ ] **Step 6.1 — Ouvrir `BaseBillet/models.py` et reperer la classe `Configuration`**

Lecture de reference :
```bash
docker exec lespass_django poetry run python -c "from BaseBillet.models import Configuration; print(Configuration._meta.fields[-5:])"
```

- [ ] **Step 6.2 — Inserer les 2 champs APRES `module_federation`**

Dans `/home/jonas/TiBillet/dev/Lespass/BaseBillet/models.py`, **apres la ligne 555** (definition de `module_federation`) et **avant la ligne 557** (`# FROM V2 : UNUSED`), inserer le bloc suivant :

```python

    ######### COMPTABILITE — RAPPORTS PERIODIQUES #########
    # / Periodic reports — accounting app

    PERIODICITE_NONE = "NONE"
    PERIODICITE_JOURNALIER = "J"
    PERIODICITE_HEBDOMADAIRE = "H"
    PERIODICITE_MENSUEL = "M"
    PERIODICITE_ANNUEL = "A"
    PERIODICITE_CHOICES = [
        (PERIODICITE_NONE, _("No email")),
        (PERIODICITE_JOURNALIER, _("Daily")),
        (PERIODICITE_HEBDOMADAIRE, _("Weekly")),
        (PERIODICITE_MENSUEL, _("Monthly")),
        (PERIODICITE_ANNUEL, _("Yearly")),
    ]

    rapport_emails = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Recipient emails for closure reports"),
        help_text=_(
            "Comma-separated emails. Leave empty to disable automatic sending."
        ),
    )

    rapport_periodicite = models.CharField(
        max_length=4,
        choices=PERIODICITE_CHOICES,
        default=PERIODICITE_NONE,
        verbose_name=_("Closure report sending frequency"),
    )

```

Notes :
- Ne **PAS** lancer `ruff format BaseBillet/models.py` (fichier existant — destructif).
- Verifier visuellement que l'indentation (4 espaces) est correcte par rapport aux autres champs de la classe.

- [ ] **Step 6.3 — Generer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations BaseBillet
```

Attendu :
```
Migrations for 'BaseBillet':
  BaseBillet/migrations/00XX_configuration_rapport_emails_rapport_periodicite.py
    + Add field rapport_emails to configuration
    + Add field rapport_periodicite to configuration
```

(Le numero `00XX` sera attribue automatiquement par Django selon les migrations existantes.)

- [ ] **Step 6.4 — Appliquer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
```

Attendu : `Applying BaseBillet.00XX_configuration_rapport_emails_*... OK` pour chaque tenant.

- [ ] **Step 6.5 — Verifier en shell tenant**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
t = Client.objects.exclude(schema_name='public').first()
with tenant_context(t):
    from BaseBillet.models import Configuration
    c = Configuration.get_solo()
    print('rapport_emails:', repr(c.rapport_emails))
    print('rapport_periodicite:', repr(c.rapport_periodicite))
"
```

Attendu :
```
rapport_emails: ''
rapport_periodicite: 'NONE'
```

---

## Task 7 — Tests pour l'admin (RED avant implementation)

**Files :**
- Modify: `tests/pytest/test_comptabilite_admin.py` (append)

- [ ] **Step 7.1 — Ajouter les tests admin a la fin du fichier de test**

Append au fichier `/home/jonas/TiBillet/dev/Lespass/tests/pytest/test_comptabilite_admin.py` :

```python


# ============================================================================
# Tests admin Unfold
# ============================================================================

@pytest.fixture
def admin_client(db):
    """
    Client Django authentifie en tant qu'admin sur un tenant.
    / Django client logged in as admin on a tenant.
    """
    from django.test import Client as DjangoClient
    from Customers.models import Client as TenantClient
    from AuthBillet.models import TibilletUser

    tenant = TenantClient.objects.exclude(schema_name="public").first()
    domain = tenant.domains.first()

    with tenant_context(tenant):
        admin_user, _created = TibilletUser.objects.get_or_create(
            email="admin@admin.com",
            defaults={"is_staff": True, "is_superuser": True, "is_active": True},
        )
        if not admin_user.is_staff:
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.is_active = True
            admin_user.save()

    client = DjangoClient(HTTP_HOST=domain.domain)
    client.force_login(admin_user)
    return client, domain


def test_admin_changelist_se_charge(admin_client):
    """
    GET /admin/comptabilite/cloturecaisse/ retourne 200.
    / The admin changelist returns 200.
    """
    client, _ = admin_client
    response = client.get("/admin/comptabilite/cloturecaisse/")
    assert response.status_code == 200, (
        f"Status {response.status_code} — body: {response.content[:500]}"
    )


def test_admin_pas_de_bouton_add(admin_client):
    """
    Le bouton 'Add' n'est PAS present (modele immuable).
    / The 'Add' button is NOT present (immutable model).
    """
    client, _ = admin_client
    response = client.get("/admin/comptabilite/cloturecaisse/")
    contenu = response.content.decode("utf-8")
    # Unfold rend le bouton "add" avec href contenant '/add/'.
    # / Unfold renders the "add" button with href containing '/add/'.
    assert "/comptabilite/cloturecaisse/add/" not in contenu, (
        "Le bouton Add ne devrait pas etre present pour ClotureCaisse"
    )
```

- [ ] **Step 7.2 — Lancer les tests admin (attendu : FAIL)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_comptabilite_admin.py::test_admin_changelist_se_charge -v
```

Attendu : ÉCHEC avec 404 ou erreur d'URL `Reverse not found: cloturecaisse_changelist` car l'admin n'est pas encore enregistre.

---

## Task 8 — Implementer l'admin `ClotureCaisseAdmin`

**Files :**
- Create: `comptabilite/admin.py`

- [ ] **Step 8.1 — Creer `comptabilite/admin.py`**

```python
"""
Admin Unfold pour l'app comptabilite.
/ Unfold admin for the comptabilite app.

LOCALISATION : comptabilite/admin.py

S1 : admin liste minimaliste, read-only. ClotureCaisseAdmin sera enrichi en S3
avec change_form_before_template (rapport visuel) et en S4 avec les exports.

/ S1: minimal read-only list admin. ClotureCaisseAdmin will be enriched in S3
with change_form_before_template (visual report) and in S4 with exports.
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from unfold.admin import ModelAdmin

from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest

from comptabilite.models import ClotureCaisse


# Helpers d'affichage definis AU NIVEAU MODULE (pas methodes de classe).
# Unfold wrappe les methodes d'un ModelAdmin avec son systeme @action, ce qui
# peut causer des bugs sur des helpers internes. (cf. tests/PIEGES.md)
# / Display helpers defined AT MODULE LEVEL (not class methods). Unfold wraps
# ModelAdmin methods via @action which can break internal helpers.

def _format_euros(centimes: int) -> str:
    """
    Formate un montant en centimes en chaine euros lisible.
    / Format a cents amount as a readable euros string.
    """
    if centimes is None:
        return "—"
    return f"{centimes / 100:.2f} €"


@admin.register(ClotureCaisse, site=staff_admin_site)
class ClotureCaisseAdmin(ModelAdmin):
    """
    Admin read-only pour les clotures comptables.
    / Read-only admin for accounting closures.
    """

    list_display = (
        "datetime_fin",
        "niveau",
        "numero_sequentiel",
        "responsable",
        "ca_ttc",
        "nombre_transactions",
    )
    list_filter = ("niveau",)
    search_fields = ("responsable__email",)
    ordering = ("-datetime_fin",)

    # Aucun fieldset : l'edition est interdite, la vue detail sera surchargee en S3.
    # / No fieldset: editing forbidden, detail view will be overridden in S3.
    fieldsets = ()

    # --- Permissions : modele immuable ---
    # / Permissions: immutable model

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        # Creation uniquement via Celery ou management command.
        # / Creation only via Celery or management command.
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # --- Colonnes d'affichage ---
    # / Display columns

    @admin.display(description=_("Total TTC"), ordering="total_general")
    def ca_ttc(self, obj):
        return _format_euros(obj.total_general)
```

- [ ] **Step 8.2 — Verifier que Django charge l'admin sans erreur**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues (0 silenced).`

- [ ] **Step 8.3 — Verifier que la route admin existe**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django.urls import reverse
print(reverse('staff_admin:comptabilite_cloturecaisse_changelist'))
"
```

Attendu : `/admin/comptabilite/cloturecaisse/`

- [ ] **Step 8.4 — Relancer les tests admin (attendu : GREEN)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_comptabilite_admin.py -v
```

Attendu : tous les tests PASSENT (4/4 GREEN).

---

## Task 9 — Entree dans la sidebar Unfold

**Files :**
- Modify: `Administration/admin/dashboard.py:550-558` (insertion **avant** `Entries`)

- [ ] **Step 9.1 — Reperer le bloc `Entries`**

```bash
grep -n "Entries\|BaseBillet_lignearticle_changelist" /home/jonas/TiBillet/dev/Lespass/Administration/admin/dashboard.py
```

Attendu : lignes ~552-558.

- [ ] **Step 9.2 — Inserer l'entree `Cash closure` AVANT `Entries`**

Dans `/home/jonas/TiBillet/dev/Lespass/Administration/admin/dashboard.py`, remplacer le bloc :

```python
            "items": [
                {
                    "title": _("Entries"),
                    "icon": "receipt_long",
                    "link": reverse_lazy(
                        "staff_admin:BaseBillet_lignearticle_changelist"
                    ),
                    "permission": admin_permission,
                },
```

par :

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
```

- [ ] **Step 9.3 — Verifier `manage.py check`**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues (0 silenced).`

---

## Task 10 — i18n : extraire et compiler les chaines

**Files :**
- Modify (généré) : `locale/fr/LC_MESSAGES/django.po`
- Modify (généré) : `locale/en/LC_MESSAGES/django.po`

- [ ] **Step 10.1 — Extraire les nouvelles chaines**

```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
```

- [ ] **Step 10.2 — Editer manuellement `locale/fr/LC_MESSAGES/django.po`**

Localiser et completer les `msgstr` pour ces nouvelles chaines :

| msgid (anglais) | msgstr (francais) |
|---|---|
| `Accounting` | `Comptabilité` |
| `Daily` | `Journalier` |
| `Weekly` | `Hebdomadaire` |
| `Monthly` | `Mensuel` |
| `Yearly` | `Annuel` |
| `Periodicity` | `Périodicité` |
| `Daily closure aggregates one day. Weekly/monthly/yearly aggregate the matching daily closures.` | `La clôture journalière agrège une journée. Les clôtures hebdomadaire/mensuelle/annuelle agrègent les clôtures journalières correspondantes.` |
| `Sequential number` | `Numéro séquentiel` |
| `Continuous global counter per tenant (LNE compliance). Shared across all periodicities (daily, weekly, monthly, yearly).` | `Compteur global continu par tenant (conformité LNE). Partagé entre toutes les périodicités (journalier, hebdomadaire, mensuel, annuel).` |
| `Period start` | `Début de période` |
| `Period end` | `Fin de période` |
| `Operator` | `Opérateur·ice` |
| `User who triggered a manual closure. Null if Celery auto.` | `Utilisateur·ice qui a déclenché une clôture manuelle. Vide si automatique (Celery).` |
| `Total TTC (cents)` | `Total TTC (centimes)` |
| `Total HT (cents)` | `Total HT (centimes)` |
| `Total VAT (cents)` | `Total TVA (centimes)` |
| `Number of transactions` | `Nombre de transactions` |
| `Perpetual total (cents)` | `Total perpétuel (centimes)` |
| `Sum of total_general of all daily closures since tenant creation. Safety check against retroactive modification.` | `Somme des totaux TTC de toutes les clôtures journalières depuis la création du tenant. Filet de sécurité contre les modifications rétroactives.` |
| `Lines hash` | `Empreinte des lignes` |
| `SHA-256 of sorted (pk, amount, qty, status) tuples of every LigneArticle covered. Changes if any line is altered post-closure.` | `SHA-256 des tuples (pk, montant, qty, statut) triés de chaque LigneArticle couverte. Change si une ligne est modifiée après la clôture.` |
| `Report payload` | `Données du rapport` |
| `Full report sections (totals by payment method, sales by category, VAT breakdown, memberships, tickets, refunds, synthesis, legal info).` | `Sections complètes du rapport (totaux par moyen de paiement, ventes par catégorie, ventilation TVA, adhésions, billets, remboursements, synthèse, infos légales).` |
| `Cash closure` | `Clôture caisse` |
| `Cash closures` | `Clôtures caisse` |
| `Recipient emails for closure reports` | `Destinataires email pour les rapports de clôture` |
| `Comma-separated emails. Leave empty to disable automatic sending.` | `Emails séparés par une virgule. Laisser vide pour désactiver l'envoi automatique.` |
| `Closure report sending frequency` | `Fréquence d'envoi du rapport de clôture` |
| `No email` | `Aucun email` |
| `Total TTC` | `Total TTC` |

Important : verifier qu'aucun `#, fuzzy` ne reste sur ces traductions (sinon les supprimer manuellement).

- [ ] **Step 10.3 — Pour `locale/en/LC_MESSAGES/django.po`**

Les msgid sont deja en anglais, donc les `msgstr` anglais doivent etre identiques aux msgid (ou laisses vides — gettext fait fallback sur msgid).

Verifier que les nouvelles chaines apparaissent dans le fichier en .po, mais aucune modification du msgstr n'est requise.

- [ ] **Step 10.4 — Compiler**

```bash
docker exec lespass_django poetry run django-admin compilemessages
```

Attendu : `processing file django.po in /path/locale/fr/LC_MESSAGES` (pas d'erreur).

---

## Task 11 — Vérifications finales

- [ ] **Step 11.1 — Lancer la suite complete des tests comptabilite**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_comptabilite_admin.py -v
```

Attendu : 4 tests PASSENT.

- [ ] **Step 11.2 — `manage.py check` global**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Attendu : `System check identified no issues (0 silenced).`

- [ ] **Step 11.3 — `makemigrations --check --dry-run` global**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --check --dry-run
```

Attendu : `No changes detected` (aucune migration manquante).

- [ ] **Step 11.4 — Lancer la suite pytest courte de non-regression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q --last-failed-no-failures=all -x 2>&1 | tail -30
```

Attendu : aucun nouveau test KO (sinon investiguer immediatement).

- [ ] **Step 11.5 — Visite manuelle de l'admin (PAR LE MAINTAINEUR)**

Demander au maintaineur de :
1. Visiter `https://lespass.tibillet.localhost/admin/` (admin tenant)
2. Verifier qu'une entree **Cash closure** apparait dans la sidebar section *Sales & accounting*, **avant** *Entries*
3. Cliquer dessus et verifier que la page `/admin/comptabilite/cloturecaisse/` se charge avec une liste vide
4. Verifier qu'**aucun bouton "Add Cash closure"** n'est present
5. Si tout est OK → proceder a Step 11.6

- [ ] **Step 11.6 — Message de commit suggere (POUR LE MAINTAINEUR)**

**NE PAS executer de `git` !** Le maintaineur passera la commande lui-meme.

Message de commit suggere :

```
feat(comptabilite): port partiel V2 — S1 squelette ClotureCaisse

Création de l'app `comptabilite/` (TENANT_APPS) avec :
- Modèle ClotureCaisse : UUID PK, niveau J/H/M/A, numéro séquentiel
  continu global tenant (conformité LNE), périodes datetime_debut/fin,
  totaux (TTC/HT/TVA), total perpétuel, hash_lignes SHA-256,
  rapport_json JSONField, FK responsable.
- Migration 0001_initial.
- Admin Unfold read-only : list_display, no add/change/delete,
  permissions TenantAdminPermissionWithRequest.
- 2 AddField sur BaseBillet.Configuration : rapport_emails (TextField),
  rapport_periodicite (CharField NONE/J/H/M/A).
- Entrée sidebar « Cash closure » insérée AVANT « Entries » dans la
  section *Sales & accounting* (Administration/admin/dashboard.py).
- 4 tests pytest smoke (app loaded, model create, unique sequentiel,
  admin changelist 200, no add button).
- Traductions FR ajoutées au .po + compilemessages.

Référence : TECH_DOC/SESSIONS/COMPTABILITE/SPEC.md §2, §5, §9 (S1).
Hub : TECH_DOC/SESSIONS/COMPTABILITE/INDEX.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

- [ ] **Step 11.7 — Mise a jour du statut dans INDEX.md (apres validation maintaineur)**

Dans `/home/jonas/TiBillet/dev/Lespass/TECH_DOC/SESSIONS/COMPTABILITE/INDEX.md`, dans le tableau « Chantiers » :

```markdown
| 01 | Port partiel V2 (clôture caisse + plan comptable + exports CSV/FEC/Excel/PDF) | 🟡 S1 fait, S2-S6 à venir | [`SPEC.md`](SPEC.md) |
```

Et dans la section §9 « Statut détaillé » :

```markdown
- [x] S1 — Modèle + admin minimal
- [ ] S2 — Service rapport + management command + tests
```

---

## Critères de succès S1

S1 est consideree comme **DONE** quand TOUTES ces conditions sont remplies :

1. ✅ App `comptabilite/` charge dans Django (apps.is_installed)
2. ✅ Migration `0001_initial` appliquee sur tous les tenants
3. ✅ Migration AddField Configuration appliquee
4. ✅ `/admin/comptabilite/cloturecaisse/` retourne 200
5. ✅ Aucun bouton Add (admin read-only)
6. ✅ Entree sidebar « Cash closure » visible, **avant** « Entries »
7. ✅ 4 tests pytest passent (`test_comptabilite_admin.py`)
8. ✅ `manage.py check` retourne 0 issue
9. ✅ `makemigrations --check` retourne 0 changement
10. ✅ Traductions FR ajoutees, compilemessages sans erreur
11. ✅ Aucun test pytest existant casse (non-regression)
12. ✅ Validation visuelle du maintaineur dans le navigateur

---

## Pièges anticipés pour S1

1. **Verbose name + i18n** : ne pas oublier les `gettext_lazy as _` partout. Sinon les chaines anglaises ne sont pas extraites par makemessages.

2. **FK vers `AuthBillet.TibilletUser`** : utiliser le string `"AuthBillet.TibilletUser"` dans la FK, pas l'import direct. Sinon dependance circulaire potentielle.

3. **`unique=True` sur `numero_sequentiel`** : Django cree un index automatique. Pas besoin d'ajouter `db_index=True` redondamment.

4. **`makemigrations` sans precision** : appliquer `migrate_schemas --executor=multiprocessing` (pas `migrate`), sinon les schemas tenant ne recevront pas la migration.

5. **L'app est dans TENANT_APPS, pas SHARED_APPS** : la table `comptabilite_cloturecaisse` existe dans chaque schema tenant, **pas** dans `public`. Les tests doivent etre dans un `tenant_context()`.

6. **`ruff format` interdit** sur `BaseBillet/models.py` (fichier existant). Si formatage necessaire, le faire **uniquement** sur les fichiers neufs (`comptabilite/*.py`, `tests/pytest/test_comptabilite_admin.py`).

7. **Test admin avec `Client(HTTP_HOST=...)`** : il faut le bon Domain pour que django-tenants resolve le bon schema. Voir fixture `admin_client` dans Task 7.

8. **Pas de git par Claude Code** : meme un `git status` pour verifier l'etat — le maintaineur s'en occupe.

---

## Estimation duree

- Task 1 : 3 min
- Task 2 : 2 min
- Task 3 : 8 min (3 tests)
- Task 4 : 5 min (modele)
- Task 5 : 5 min (migration)
- Task 6 : 7 min (AddField Configuration)
- Task 7 : 5 min (tests admin)
- Task 8 : 8 min (admin.py)
- Task 9 : 3 min (sidebar)
- Task 10 : 10 min (i18n + traductions FR)
- Task 11 : 8 min (verifications + commit message)

**Total estime : ~65 minutes** (hors temps de validation maintaineur).

Marges :
- Si makemigrations rejette le modele : +15 min de debug
- Si test admin renvoie 302 (redirect non-authent) : +10 min sur la fixture
- Si i18n fuzzy a corriger : +10 min

**Plage realiste : 1h - 1h45.**
