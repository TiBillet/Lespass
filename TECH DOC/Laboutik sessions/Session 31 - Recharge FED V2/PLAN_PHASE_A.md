# Plan d'implémentation — Session 31 Phase A

> **Pour les workers agentiques :** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (recommended) ou superpowers:executing-plans pour exécuter ce plan tâche par tâche. Les étapes utilisent la syntaxe checkbox `- [ ]` pour le suivi.

**Goal :** Poser les fondations de la recharge FED V2 : modèle, tenant dédié, service idempotent. Zero UI, zero webhook — ces éléments arrivent en Phase B et C.

**Architecture :** Nouveau tenant `federation_fed` (catégorie `Client.FED='E'`) qui porte l'asset FED unique, un `Product` de recharge, et les futurs `Paiement_stripe`. Une management command `bootstrap_fed_asset` idempotente crée tout. Un `RefillService.process_cashless_refill()` dans `fedow_core/services.py` sera le point d'entrée PSP-agnostique appelé par les webhooks (Phase B).

**Tech Stack :** Django 4.2, Python 3.11, PostgreSQL 13 (django-tenants schema-per-tenant), pytest + pytest-django, Unfold admin.

**Contraintes projet :**
- **Aucune opération git** (CLAUDE.md — le mainteneur commit lui-même, chaque tâche propose un message de commit)
- Code **FALC** : noms verbeux, commentaires FR/EN inline, pas de magie
- Tests pytest dans `tests/pytest/` (DB-only, pas de navigateur)
- Toutes les commandes passent par `docker exec lespass_django poetry run ...`

**Référence spec :** `TECH DOC/Laboutik sessions/Session 31 - Recharge FED V2/SPEC_RECHARGE_FED_V2.md`

---

## Cartographie des fichiers

**Créés :**
- `fedow_core/management/commands/bootstrap_fed_asset.py` (commande idempotente)
- `fedow_core/PSP_INTERFACE.md` (contrat documenté pour futurs PSP)
- `PaiementStripe/serializers.py` (nouveau — contiendra `RefillAmountSerializer`)
- `tests/pytest/test_bootstrap_fed_asset.py`
- `tests/pytest/test_refill_service.py`
- `tests/pytest/test_refill_serializer.py`

**Modifiés :**
- `Customers/models.py` : +`FED = 'E'` dans `CATEGORIE_CHOICES`
- `Customers/migrations/XXXX_add_fed_category.py` (auto-généré par `makemigrations`)
- `BaseBillet/models.py` : +`CASHLESS_REFILL = "R"` dans `Paiement_stripe.SOURCE_CHOICES` + `RECHARGE_CASHLESS_FED = "R"` dans `Product.categorie_article` choices
- `BaseBillet/migrations/XXXX_add_refill_choices.py` (auto-généré)
- `fedow_core/services.py` : +classe `RefillService`
- `Administration/management/commands/install.py` : hook `call_command('bootstrap_fed_asset')` après création tenant_meta
- `laboutik/management/commands/create_test_pos_data.py` : hook `call_command('bootstrap_fed_asset')` pour les fixtures de test

**Dépendances entre tâches :**
```
Task 1 (Customers.FED) ──┐
                         ▼
Task 2 (BaseBillet)      Task 3 (bootstrap cmd) ──┬──► Task 4 (install.py)
                         ▲                        │
                         │                        └──► Task 5 (create_test_pos_data)
Task 6 (Serializer)  (indépendant)
Task 7 (RefillService) (indépendant des autres sauf Asset/Token)
Task 8 (PSP_INTERFACE.md) (indépendant, peut être fait à tout moment)
```

---

## Task 1 — Migration `Customers.Client.FED` catégorie

**Files :**
- Modify: `Customers/models.py:17-30`
- Create: `Customers/migrations/0011_add_fed_category.py` (ou numéro suivant disponible)

- [ ] **Step 1.1 : Lire le fichier cible**

```bash
docker exec lespass_django cat /DjangoFiles/Customers/models.py
```
Confirmer que `CATEGORIE_CHOICES` est bien aux lignes 17-30 et qu'il n'y a pas déjà un code `'E'` utilisé.

- [ ] **Step 1.2 : Ajouter la catégorie FED dans `Customers/models.py`**

Modifier la constante de choix (ligne 17) et la liste de tuples (ligne 18-27) :

```python
# Avant:
ARTISTE, SALLE_SPECTACLE, FESTIVAL, TOURNEUR, PRODUCTEUR, META, WAITING_CONFIG, ROOT = 'A', 'S', 'F', 'T', 'P', 'M', 'W', 'R'
CATEGORIE_CHOICES = [
    (ARTISTE, _('Artist')),
    (SALLE_SPECTACLE, _("Scene")),
    (FESTIVAL, _('Festival')),
    (TOURNEUR, _('Tour operator')),
    (PRODUCTEUR, _('Producer')),
    (META, _('Event aggregator')),
    (WAITING_CONFIG, _('Waiting configuration')),
    (ROOT, _('Root public tenant')),
]

# Après:
ARTISTE, SALLE_SPECTACLE, FESTIVAL, TOURNEUR, PRODUCTEUR, META, WAITING_CONFIG, ROOT, FED = 'A', 'S', 'F', 'T', 'P', 'M', 'W', 'R', 'E'
CATEGORIE_CHOICES = [
    (ARTISTE, _('Artist')),
    (SALLE_SPECTACLE, _("Scene")),
    (FESTIVAL, _('Festival')),
    (TOURNEUR, _('Tour operator')),
    (PRODUCTEUR, _('Producer')),
    (META, _('Event aggregator')),
    (WAITING_CONFIG, _('Waiting configuration')),
    (ROOT, _('Root public tenant')),
    # Tenant federation : porte le pot central FED, pas d'accès HTTP direct
    # / Federation tenant: holds central FED pot, no HTTP access
    (FED, _('Federation currency')),
]
```

- [ ] **Step 1.3 : Générer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations Customers
```
Expected : `Customers/migrations/0011_alter_client_categorie.py` créé (ou numéro suivant).

- [ ] **Step 1.4 : Appliquer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --shared
```
Expected : `Applying Customers.0011_alter_client_categorie... OK`

- [ ] **Step 1.5 : Vérifier la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "from Customers.models import Client; print(Client.FED, [c for c in Client.CATEGORIE_CHOICES if c[0]=='E'])"
```
Expected : `E [('E', 'Federation currency')]`

- [ ] **Step 1.6 : Checkpoint mainteneur**

Aucun test unitaire — c'est une migration de choix pure, validée par le shell. Message de commit suggéré :
```
feat(customers): add Client.FED='E' category for federation tenants

Prepare the federation_fed tenant that will hold the central FED asset.
Part of Session 31 Phase A (recharge FED V2).
```

---

## Task 2 — Migration `Paiement_stripe.CASHLESS_REFILL` + `Product.RECHARGE_CASHLESS_FED`

**Files :**
- Modify: `BaseBillet/models.py:1186-1188` (`Product.categorie_article` choices)
- Modify: `BaseBillet/models.py:3589-3604` (`Paiement_stripe.SOURCE_CHOICES`)
- Create: `BaseBillet/migrations/XXXX_add_refill_choices.py`

- [ ] **Step 2.1 : Ajouter `RECHARGE_CASHLESS_FED` dans Product.categorie_article**

Lire d'abord :
```bash
docker exec lespass_django sed -n '1180,1215p' /DjangoFiles/BaseBillet/models.py
```
Confirmer que `RECHARGE_CASHLESS = "R"` existe déjà mais est commenté dans la liste de tuples (ligne 1199).

Modifier `BaseBillet/models.py:1186-1188` :

```python
# Avant:
NONE, BILLET, PACK, RECHARGE_CASHLESS = "N", "B", "P", "R"
RECHARGE_FEDERATED, VETEMENT, MERCH, ADHESION, BADGE = "S", "T", "M", "A", "G"
DON, FREERES, NEED_VALIDATION = "D", "F", "V"

# Après:
NONE, BILLET, PACK, RECHARGE_CASHLESS = "N", "B", "P", "R"
RECHARGE_FEDERATED, VETEMENT, MERCH, ADHESION, BADGE = "S", "T", "M", "A", "G"
DON, FREERES, NEED_VALIDATION = "D", "F", "V"
# Recharge cashless FED : produit système créé par bootstrap_fed_asset.
# Un seul Product avec cette catégorie existe, lié à l'asset FED unique.
# / Cashless FED refill: system product created by bootstrap_fed_asset.
# Only one Product with this category exists, linked to the unique FED asset.
RECHARGE_CASHLESS_FED = "E"
```

Puis ajouter la ligne dans le tuple `CHOICES` (ligne 1196-1205). Lire d'abord :
```bash
docker exec lespass_django sed -n '1196,1215p' /DjangoFiles/BaseBillet/models.py
```

Ajouter après `(BADGE, _("Membership card"))` :
```python
    (RECHARGE_CASHLESS_FED, _("FED cashless refill")),
```

- [ ] **Step 2.2 : Ajouter `CASHLESS_REFILL` dans `Paiement_stripe.SOURCE_CHOICES`**

Modifier `BaseBillet/models.py:3589-3604` :

```python
# Avant:
QRCODE, API_BILLETTERIE, FRONT_BILLETTERIE, FRONT_CROWDS, INVOICE, TRANSFERT = (
    "Q",
    "B",
    "F",
    "C",
    "I",
    "T",
)
SOURCE_CHOICES = (
    (QRCODE, _("From QR code scan")),  # ancien api. A virer ?
    (API_BILLETTERIE, _("From API")),
    (FRONT_BILLETTERIE, _("From ticketing app")),
    (FRONT_CROWDS, _("From Crowds app")),
    (INVOICE, _("From invoice")),
    (TRANSFERT, _("Stripe Transfert")),
)

# Après:
QRCODE, API_BILLETTERIE, FRONT_BILLETTERIE, FRONT_CROWDS, INVOICE, TRANSFERT, CASHLESS_REFILL = (
    "Q",
    "B",
    "F",
    "C",
    "I",
    "T",
    "R",
)
SOURCE_CHOICES = (
    (QRCODE, _("From QR code scan")),  # ancien api. A virer ?
    (API_BILLETTERIE, _("From API")),
    (FRONT_BILLETTERIE, _("From ticketing app")),
    (FRONT_CROWDS, _("From Crowds app")),
    (INVOICE, _("From invoice")),
    (TRANSFERT, _("Stripe Transfert")),
    # Recharge FED V2 : paiement d'un user pour recharger son wallet federe.
    # Stocke dans le schema federation_fed, pas dans le tenant du lieu.
    # / FED V2 refill: user payment to refill their federated wallet.
    # Stored in federation_fed schema, not in the venue tenant.
    (CASHLESS_REFILL, _("Cashless refill")),
)
```

- [ ] **Step 2.3 : Générer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations BaseBillet
```
Expected : `BaseBillet/migrations/XXXX_alter_product_categorie_article_alter_paiement_stripe_source.py` créé.

- [ ] **Step 2.4 : Appliquer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
```
Expected : `Applying BaseBillet.XXXX_alter_product_categorie_article_alter_paiement_stripe_source... OK` sur chaque tenant.

- [ ] **Step 2.5 : Vérifier les choix**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from BaseBillet.models import Product, Paiement_stripe
print('Product:', Product.RECHARGE_CASHLESS_FED, 'in choices:', ('E','FED cashless refill') in [(c[0], str(c[1])) for c in Product._meta.get_field('categorie_article').choices])
print('Paiement_stripe:', Paiement_stripe.CASHLESS_REFILL, 'in choices:', 'R' in [c[0] for c in Paiement_stripe.SOURCE_CHOICES])
"
```
Expected (ou équivalent) : `Product: E in choices: True` et `Paiement_stripe: R in choices: True`.

- [ ] **Step 2.6 : Checkpoint mainteneur**

Message de commit suggéré :
```
feat(BaseBillet): add CASHLESS_REFILL source and RECHARGE_CASHLESS_FED category

Needed for recharge FED V2 flow. Paiement_stripe.CASHLESS_REFILL identifies
cashless refill intents; Product.RECHARGE_CASHLESS_FED identifies the unique
system product created by bootstrap_fed_asset.
Part of Session 31 Phase A (recharge FED V2).
```

---

## Task 3 — Management command `bootstrap_fed_asset`

**Files :**
- Create: `fedow_core/management/commands/bootstrap_fed_asset.py`
- Create: `tests/pytest/test_bootstrap_fed_asset.py`

- [ ] **Step 3.1 : Écrire le test d'intégration (TDD)**

Créer `tests/pytest/test_bootstrap_fed_asset.py` :

```python
"""
Tests du bootstrap de l'infrastructure recharge FED V2.
Tests for the FED V2 refill infrastructure bootstrap.

LOCALISATION : tests/pytest/test_bootstrap_fed_asset.py
"""
import pytest
from django.core.management import call_command
from django_tenants.utils import tenant_context

from Customers.models import Client
from AuthBillet.models import Wallet
from fedow_core.models import Asset
from BaseBillet.models import Product, Price


TEST_PREFIX = "[bootstrap_fed]"


@pytest.mark.django_db(transaction=True)
def test_bootstrap_cree_tenant_federation_fed():
    """
    Premier appel : cree le tenant federation_fed avec la bonne categorie.
    / First call: creates the federation_fed tenant with the right category.
    """
    # Nettoyage si un test precedent a laisse le tenant
    # / Cleanup if a previous test left the tenant
    Client.objects.filter(schema_name='federation_fed').delete()

    call_command('bootstrap_fed_asset')

    tenant = Client.objects.get(schema_name='federation_fed')
    assert tenant.categorie == Client.FED
    assert tenant.name == 'Fédération FED'


@pytest.mark.django_db(transaction=True)
def test_bootstrap_cree_asset_fed_unique():
    """
    Apres bootstrap, il existe exactement UN Asset de categorie FED.
    / After bootstrap, exactly ONE Asset of category FED exists.
    """
    Client.objects.filter(schema_name='federation_fed').delete()

    call_command('bootstrap_fed_asset')

    assets_fed = Asset.objects.filter(category=Asset.FED)
    assert assets_fed.count() == 1
    asset = assets_fed.first()
    assert asset.currency_code == 'EUR'
    assert asset.wallet_origin is not None
    assert asset.wallet_origin.name == 'Pot central TiBillet FED'


@pytest.mark.django_db(transaction=True)
def test_bootstrap_cree_product_et_price_dans_federation_fed():
    """
    Le Product et Price de recharge existent dans le schema federation_fed.
    / The refill Product and Price exist in the federation_fed schema.
    """
    Client.objects.filter(schema_name='federation_fed').delete()

    call_command('bootstrap_fed_asset')

    tenant = Client.objects.get(schema_name='federation_fed')
    with tenant_context(tenant):
        product = Product.objects.get(categorie_article=Product.RECHARGE_CASHLESS_FED)
        assert product.name == 'Recharge monnaie fédérée'
        price = product.prices.first()
        assert price is not None
        assert price.name == 'Montant libre'
        assert price.prix == 0


@pytest.mark.django_db(transaction=True)
def test_bootstrap_est_idempotent():
    """
    Deux appels successifs ne creent pas de doublons.
    / Two successive calls do not create duplicates.
    """
    Client.objects.filter(schema_name='federation_fed').delete()

    call_command('bootstrap_fed_asset')
    call_command('bootstrap_fed_asset')

    assert Client.objects.filter(schema_name='federation_fed').count() == 1
    assert Asset.objects.filter(category=Asset.FED).count() == 1

    tenant = Client.objects.get(schema_name='federation_fed')
    with tenant_context(tenant):
        assert Product.objects.filter(
            categorie_article=Product.RECHARGE_CASHLESS_FED
        ).count() == 1
```

- [ ] **Step 3.2 : Lancer le test pour vérifier l'échec**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_bootstrap_fed_asset.py -v
```
Expected : `CommandError: Unknown command: 'bootstrap_fed_asset'` sur chaque test.

- [ ] **Step 3.3 : Implémenter la management command**

Créer `fedow_core/management/commands/bootstrap_fed_asset.py` :

```python
"""
Management command bootstrap_fed_asset.
Cree l'infrastructure minimale pour la recharge FED V2 :
- Tenant federation_fed (categorie Client.FED)
- Root wallet (pot central)
- Asset FED unique
- Product et Price de recharge (dans le schema federation_fed)

/ Creates minimal infrastructure for FED V2 refill:
- federation_fed tenant (Client.FED category)
- Root wallet (central pot)
- Unique FED Asset
- Refill Product and Price (in federation_fed schema)

LOCALISATION : fedow_core/management/commands/bootstrap_fed_asset.py

Idempotent : peut etre lance plusieurs fois sans effet de bord.
/ Idempotent: can be run multiple times without side effects.

Usage :
    docker exec lespass_django poetry run python manage.py bootstrap_fed_asset
"""
import logging

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django_tenants.utils import tenant_context

from Customers.models import Client
from AuthBillet.models import Wallet
from fedow_core.models import Asset
from BaseBillet.models import Product, Price


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Bootstrap de l'infrastructure recharge FED V2 (tenant federation_fed + asset FED)"

    def handle(self, *args, **options):
        # 1. Tenant federation_fed (schema PostgreSQL auto-cree par django-tenants)
        # / 1. federation_fed tenant (schema auto-created by django-tenants)
        tenant, tenant_created = Client.objects.get_or_create(
            schema_name='federation_fed',
            defaults={
                'name': 'Fédération FED',
                'categorie': Client.FED,
                'on_trial': False,
            },
        )
        if tenant_created:
            self.stdout.write(self.style.SUCCESS(
                f"Tenant federation_fed cree (schema PostgreSQL auto-genere)."
            ))
        else:
            self.stdout.write(
                f"Tenant federation_fed deja present, reutilise."
            )

        # 2. Migrer les TENANT_APPS dans ce schema.
        # auto_create_schema=True cree le schema PostgreSQL, mais NE lance PAS
        # les migrations. On le fait manuellement uniquement si le tenant vient
        # d'etre cree (sinon, les migrations sont deja en place).
        # / 2. Migrate TENANT_APPS in this schema.
        # auto_create_schema creates the PostgreSQL schema but does NOT run
        # migrations. We do it manually only if the tenant was just created.
        if tenant_created:
            self.stdout.write("Migration des TENANT_APPS dans federation_fed...")
            call_command(
                'migrate_schemas',
                schema_name='federation_fed',
                interactive=False,
            )
            self.stdout.write(self.style.SUCCESS("Migrations appliquees."))

        # 3. Root wallet (le "pot central" qui emet les tokens FED lors d'une REFILL)
        # Wallet est en SHARED_APPS, pas besoin de tenant_context pour la creation.
        # / 3. Root wallet (the "central pot" that emits FED tokens on REFILL).
        # Wallet is in SHARED_APPS, no tenant_context needed for creation.
        root_wallet, wallet_created = Wallet.objects.get_or_create(
            name='Pot central TiBillet FED',
            defaults={'origin': tenant},
        )
        if wallet_created:
            self.stdout.write(self.style.SUCCESS(f"Root wallet cree : {root_wallet.uuid}"))

        # 4. Asset FED unique. Asset est en SHARED_APPS.
        # / 4. Unique FED Asset. Asset is in SHARED_APPS.
        asset_fed, asset_created = Asset.objects.get_or_create(
            category=Asset.FED,
            defaults={
                'name': 'Euro fédéré TiBillet',
                'currency_code': 'EUR',
                'wallet_origin': root_wallet,
                'tenant_origin': tenant,
            },
        )
        if asset_created:
            self.stdout.write(self.style.SUCCESS(f"Asset FED cree : {asset_fed.uuid}"))

        # 5. Product et Price de recharge (TENANT_APPS, dans federation_fed)
        # / 5. Refill Product and Price (TENANT_APPS, in federation_fed schema)
        with tenant_context(tenant):
            product, product_created = Product.objects.get_or_create(
                categorie_article=Product.RECHARGE_CASHLESS_FED,
                defaults={
                    'name': 'Recharge monnaie fédérée',
                    'asset': asset_fed,
                },
            )
            if product_created:
                self.stdout.write(self.style.SUCCESS(
                    f"Product de recharge FED cree : {product.uuid}"
                ))

            price, price_created = Price.objects.get_or_create(
                product=product,
                defaults={
                    'name': 'Montant libre',
                    'prix': 0,  # custom_amount ecrase cette valeur a chaque achat
                    'asset': asset_fed,
                },
            )
            if price_created:
                self.stdout.write(self.style.SUCCESS(
                    f"Price de recharge FED cree : {price.uuid}"
                ))

        self.stdout.write(self.style.SUCCESS(
            "\nBootstrap FED V2 termine."
        ))
```

- [ ] **Step 3.4 : Lancer le test pour vérifier qu'il passe**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_bootstrap_fed_asset.py -v
```
Expected : 4 tests PASS.

- [ ] **Step 3.5 : Vérifier manuellement l'idempotence**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py bootstrap_fed_asset
docker exec lespass_django poetry run python /DjangoFiles/manage.py bootstrap_fed_asset
```
Expected : 2ème appel affiche "deja present, reutilise" et ne crée rien de nouveau.

- [ ] **Step 3.6 : Checkpoint mainteneur**

Message de commit suggéré :
```
feat(fedow_core): add bootstrap_fed_asset management command

Creates the federation_fed tenant (Client.FED category), the central pot wallet,
the unique FED Asset, and the system Product/Price for cashless refills.
Idempotent: safe to run multiple times.
Part of Session 31 Phase A (recharge FED V2).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## Task 4 — Hook `bootstrap_fed_asset` dans `install.py`

**Files :**
- Modify: `Administration/management/commands/install.py:134-145` (après la création tenant_meta)

- [ ] **Step 4.1 : Lire le contexte actuel**

```bash
docker exec lespass_django sed -n '118,160p' /DjangoFiles/Administration/management/commands/install.py
```
Confirmer l'emplacement : après `domain_public.save()` du tenant meta (ligne 142 du fichier actuel), avant `### Installation du premier tenant`.

- [ ] **Step 4.2 : Ajouter l'appel à bootstrap_fed_asset**

Modifier `Administration/management/commands/install.py` juste après le `domain_public.save()` du bloc `tenant_meta` (après `m.{DOMAIN}` domain) et avant `### Installation du premier tenant :` :

Avant :
```python
        ## m pour les scans de cartes,
        domain_public, created = Domain.objects.get_or_create(
            domain=f'm.{os.getenv("DOMAIN")}',
            tenant=tenant_meta,
            is_primary=False
        )
        domain_public.save()

        ### Installation du premier tenant :
```

Après :
```python
        ## m pour les scans de cartes,
        domain_public, created = Domain.objects.get_or_create(
            domain=f'm.{os.getenv("DOMAIN")}',
            tenant=tenant_meta,
            is_primary=False
        )
        domain_public.save()

        ## Tenant FEDERATION : porte le pot central FED pour la recharge V2
        # / FEDERATION tenant: holds the central FED pot for V2 refills
        call_command('bootstrap_fed_asset')

        ### Installation du premier tenant :
```

- [ ] **Step 4.3 : Vérifier visuellement que `call_command` est importé**

```bash
docker exec lespass_django grep -n "from django.core.management" /DjangoFiles/Administration/management/commands/install.py
```
Expected : `from django.core.management import call_command` déjà présent (ligne 7). Si absent, l'ajouter.

- [ ] **Step 4.4 : Vérifier que la modif ne casse pas install.py**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```
Expected : `System check identified no issues (0 silenced).`

- [ ] **Step 4.5 : Checkpoint mainteneur**

Ce step n'a pas de test unitaire car `install.py` est la commande de première installation (elle tourne une seule fois). Tests manuels d'install complet effectués par le mainteneur sur un environnement fresh.

Message de commit suggéré :
```
feat(install): hook bootstrap_fed_asset after meta tenant creation

Ensures every new TiBillet install has the federation_fed tenant and the unique
FED Asset ready for V2 refills. Runs once after public + meta tenants.
Part of Session 31 Phase A (recharge FED V2).
```

---

## Task 5 — Hook `bootstrap_fed_asset` dans `create_test_pos_data`

**Files :**
- Modify: `laboutik/management/commands/create_test_pos_data.py`

- [ ] **Step 5.1 : Lire le début de la commande**

```bash
docker exec lespass_django sed -n '1,60p' /DjangoFiles/laboutik/management/commands/create_test_pos_data.py
```
Identifier le début de `handle()` et repérer où placer l'appel (idéalement en tête, avant les créations qui dépendent potentiellement de l'asset FED).

- [ ] **Step 5.2 : Ajouter l'appel à bootstrap_fed_asset**

Ajouter au tout début de `handle()` (après d'éventuelles validations d'arguments) :

```python
def handle(self, *args, **options):
    # Bootstrap de l'infrastructure FED V2 (tenant federation_fed + asset FED).
    # Idempotent : si deja present, ne fait rien.
    # / V2 FED infrastructure bootstrap. Idempotent.
    from django.core.management import call_command
    call_command('bootstrap_fed_asset')

    # ... reste du handle existant
```

(Adapter selon la structure existante de la commande — si `call_command` est déjà importé en haut du fichier, ne pas réimporter localement.)

- [ ] **Step 5.3 : Vérifier que `create_test_pos_data` tourne sans erreur**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py create_test_pos_data
```
Expected : sortie incluant les lignes "Tenant federation_fed cree..." (premier run) ou "deja present, reutilise" (runs suivants). Aucune erreur.

- [ ] **Step 5.4 : Vérifier que les tests pytest existants passent toujours**

Lancer un test qui utilise `create_test_pos_data` :
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_pos_views_data.py -v --timeout=120
```
Expected : aucune régression (tous les tests qui passaient avant passent encore).

- [ ] **Step 5.5 : Checkpoint mainteneur**

Message de commit suggéré :
```
feat(laboutik): call bootstrap_fed_asset in create_test_pos_data fixtures

Ensures test fixtures always have the federation_fed tenant and FED Asset
available. Required for upcoming RefillService tests.
Part of Session 31 Phase A (recharge FED V2).
```

---

## Task 6 — `RefillAmountSerializer`

**Files :**
- Create: `PaiementStripe/serializers.py` (nouveau fichier)
- Create: `tests/pytest/test_refill_serializer.py`

- [ ] **Step 6.1 : Écrire les tests (TDD)**

Créer `tests/pytest/test_refill_serializer.py` :

```python
"""
Tests du RefillAmountSerializer : validation des bornes de montant (1€ min, 500€ max).
Tests for RefillAmountSerializer: amount boundary validation.

LOCALISATION : tests/pytest/test_refill_serializer.py
"""
import pytest


@pytest.mark.django_db
def test_refill_serializer_accepte_borne_min():
    """100 centimes (1,00 EUR) est accepte."""
    from PaiementStripe.serializers import RefillAmountSerializer
    serializer = RefillAmountSerializer(data={'amount_cents': 100})
    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_refill_serializer_accepte_borne_max():
    """50000 centimes (500,00 EUR) est accepte."""
    from PaiementStripe.serializers import RefillAmountSerializer
    serializer = RefillAmountSerializer(data={'amount_cents': 50000})
    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_refill_serializer_rejette_sous_borne_min():
    """99 centimes est rejete."""
    from PaiementStripe.serializers import RefillAmountSerializer
    serializer = RefillAmountSerializer(data={'amount_cents': 99})
    assert not serializer.is_valid()
    assert 'amount_cents' in serializer.errors


@pytest.mark.django_db
def test_refill_serializer_rejette_au_dessus_borne_max():
    """50001 centimes est rejete."""
    from PaiementStripe.serializers import RefillAmountSerializer
    serializer = RefillAmountSerializer(data={'amount_cents': 50001})
    assert not serializer.is_valid()
    assert 'amount_cents' in serializer.errors


@pytest.mark.django_db
def test_refill_serializer_rejette_champ_manquant():
    """Absence de amount_cents est rejete."""
    from PaiementStripe.serializers import RefillAmountSerializer
    serializer = RefillAmountSerializer(data={})
    assert not serializer.is_valid()
    assert 'amount_cents' in serializer.errors
```

- [ ] **Step 6.2 : Lancer les tests pour vérifier l'échec**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_refill_serializer.py -v
```
Expected : 5 tests FAIL avec `ModuleNotFoundError: No module named 'PaiementStripe.serializers'`.

- [ ] **Step 6.3 : Créer le fichier `PaiementStripe/serializers.py`**

```python
"""
Serializers DRF pour l'app PaiementStripe.
DRF serializers for the PaiementStripe app.

LOCALISATION : PaiementStripe/serializers.py

Regle du projet (stack djc) :
- Utiliser serializers.Serializer, jamais Django Forms.
- Bornes hardcodees (YAGNI), deplacables sur Asset plus tard.
/ Project rule (djc stack):
- Use serializers.Serializer, never Django Forms.
- Hardcoded bounds (YAGNI), movable onto Asset later if needed.
"""
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class RefillAmountSerializer(serializers.Serializer):
    """
    Valide un montant de recharge FED saisi en centimes.
    / Validates a FED refill amount in cents.

    La conversion euros -> centimes est faite par la vue AVANT d'appeler ce serializer
    (l'user saisit en euros dans le formulaire HTMX, la vue convertit via Decimal).
    / Euros -> cents conversion is done by the view BEFORE calling this serializer.
    """

    # Montant minimum : 100 centimes = 1,00 EUR
    # Montant maximum : 50000 centimes = 500,00 EUR
    # / Min: 100 cents = 1.00 EUR. Max: 50000 cents = 500.00 EUR.
    MIN_CENTS = 100
    MAX_CENTS = 50000

    amount_cents = serializers.IntegerField(
        min_value=MIN_CENTS,
        max_value=MAX_CENTS,
        error_messages={
            'required': _("Le montant est obligatoire."),
            'min_value': _("Montant minimum : 1,00 €"),
            'max_value': _("Montant maximum : 500,00 €"),
            'invalid': _("Montant invalide."),
        },
    )
```

- [ ] **Step 6.4 : Lancer les tests pour vérifier qu'ils passent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_refill_serializer.py -v
```
Expected : 5 tests PASS.

- [ ] **Step 6.5 : Checkpoint mainteneur**

Message de commit suggéré :
```
feat(PaiementStripe): add RefillAmountSerializer for FED refill validation

Validates refill amount in cents (100 to 50000, i.e. 1 EUR to 500 EUR).
The view handles euros -> cents conversion before calling this serializer.
Part of Session 31 Phase A (recharge FED V2).
```

---

## Task 7 — `RefillService.process_cashless_refill`

**Files :**
- Modify: `fedow_core/services.py` (ajouter une nouvelle classe en fin de fichier)
- Create: `tests/pytest/test_refill_service.py`

- [ ] **Step 7.1 : Écrire les tests critiques (TDD)**

Créer `tests/pytest/test_refill_service.py` :

```python
"""
Tests du RefillService.process_cashless_refill.
Tests for RefillService.process_cashless_refill.

LOCALISATION : tests/pytest/test_refill_service.py

Tests critiques (Phase A) :
- nominal : Transaction REFILL creee, Token credite
- idempotent : 2 appels -> 1 seule Transaction
- fallback wallet : si user.wallet is None, wallet cree automatiquement

Tests nice-to-have (Phase D-polish) :
- no asset FED present
- cross-tenant (user d'un tenant A recharge via tenant B)

/ Critical tests (Phase A):
- nominal: REFILL Transaction created, Token credited
- idempotent: 2 calls -> 1 Transaction
- wallet fallback: if user.wallet is None, wallet auto-created
"""
import uuid

import pytest
from django.core.management import call_command
from django_tenants.utils import tenant_context

from Customers.models import Client
from AuthBillet.models import Wallet, TibilletUser
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import RefillService


TEST_EMAIL = "test_refill_service@example.com"


@pytest.fixture
def tenant_federation_fed(db):
    """
    Bootstrape federation_fed et retourne le tenant.
    Idempotent : reutilise si deja present (bootstrap_fed_asset est idempotent).
    """
    call_command('bootstrap_fed_asset')
    return Client.objects.get(schema_name='federation_fed')


@pytest.fixture
def user_avec_wallet(tenant_federation_fed):
    """User dont le wallet pointe vers federation_fed (cas V2 nominal)."""
    # Nettoyage des users de test precedents
    TibilletUser.objects.filter(email=TEST_EMAIL).delete()

    user = TibilletUser.objects.create(
        email=TEST_EMAIL,
        username=TEST_EMAIL,
    )
    user.wallet = Wallet.objects.create(
        origin=tenant_federation_fed,
        name=f"Wallet {TEST_EMAIL}",
    )
    user.save(update_fields=['wallet'])
    return user


@pytest.mark.django_db(transaction=True)
def test_refill_service_nominal(tenant_federation_fed, user_avec_wallet):
    """
    Appel nominal : la Transaction REFILL est creee et le Token credite.
    / Nominal call: REFILL Transaction created and Token credited.
    """
    paiement_uuid = uuid.uuid4()
    amount_cents = 1500  # 15,00 EUR

    transaction = RefillService.process_cashless_refill(
        paiement_uuid=paiement_uuid,
        user=user_avec_wallet,
        amount_cents=amount_cents,
        tenant=tenant_federation_fed,
        ip='127.0.0.1',
    )

    # La Transaction existe avec les bonnes valeurs
    # / Transaction exists with the right values
    assert transaction is not None
    assert transaction.action == Transaction.REFILL
    assert transaction.amount == amount_cents
    assert transaction.receiver == user_avec_wallet.wallet
    assert str(transaction.checkout_stripe) == str(paiement_uuid)

    # Le Token est credite du montant
    # / Token is credited
    asset_fed = Asset.objects.get(category=Asset.FED)
    token = Token.objects.get(wallet=user_avec_wallet.wallet, asset=asset_fed)
    assert token.value == amount_cents


@pytest.mark.django_db(transaction=True)
def test_refill_service_idempotent(tenant_federation_fed, user_avec_wallet):
    """
    Deux appels successifs avec le meme paiement_uuid : une seule Transaction.
    / Two successive calls with the same paiement_uuid: one Transaction.
    """
    paiement_uuid = uuid.uuid4()
    amount_cents = 2000

    tx1 = RefillService.process_cashless_refill(
        paiement_uuid=paiement_uuid,
        user=user_avec_wallet,
        amount_cents=amount_cents,
        tenant=tenant_federation_fed,
        ip='127.0.0.1',
    )
    tx2 = RefillService.process_cashless_refill(
        paiement_uuid=paiement_uuid,
        user=user_avec_wallet,
        amount_cents=amount_cents,
        tenant=tenant_federation_fed,
        ip='127.0.0.1',
    )

    # Meme Transaction retournee
    # / Same Transaction returned
    assert tx1.pk == tx2.pk

    # Une seule Transaction en base pour ce paiement_uuid
    # / Only one Transaction in DB for this paiement_uuid
    transactions = Transaction.objects.filter(
        checkout_stripe=paiement_uuid,
        action=Transaction.REFILL,
    )
    assert transactions.count() == 1

    # Le Token n'est pas credite 2x
    # / Token is not credited twice
    asset_fed = Asset.objects.get(category=Asset.FED)
    token = Token.objects.get(wallet=user_avec_wallet.wallet, asset=asset_fed)
    assert token.value == amount_cents  # pas 2 * amount_cents


@pytest.mark.django_db(transaction=True)
def test_refill_service_cree_wallet_si_absent(tenant_federation_fed):
    """
    Fallback defensif : si user.wallet is None, le wallet est cree automatiquement.
    / Defensive fallback: if user.wallet is None, wallet auto-created.
    """
    TibilletUser.objects.filter(email=TEST_EMAIL).delete()
    user_sans_wallet = TibilletUser.objects.create(
        email=TEST_EMAIL,
        username=TEST_EMAIL,
    )
    assert user_sans_wallet.wallet is None

    RefillService.process_cashless_refill(
        paiement_uuid=uuid.uuid4(),
        user=user_sans_wallet,
        amount_cents=500,
        tenant=tenant_federation_fed,
        ip='127.0.0.1',
    )

    # Le wallet a ete cree
    # / Wallet was created
    user_sans_wallet.refresh_from_db()
    assert user_sans_wallet.wallet is not None
    assert user_sans_wallet.wallet.origin == tenant_federation_fed
```

- [ ] **Step 7.2 : Lancer les tests pour vérifier l'échec**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_refill_service.py -v
```
Expected : 3 tests FAIL avec `ImportError: cannot import name 'RefillService'`.

- [ ] **Step 7.3 : Lire la fin de `fedow_core/services.py`**

```bash
docker exec lespass_django tail -20 /DjangoFiles/fedow_core/services.py
```
Identifier la dernière classe et ajouter `RefillService` après.

- [ ] **Step 7.4 : Ajouter la classe `RefillService` à `fedow_core/services.py`**

Ajouter en fin de fichier (après `BankTransferService`) :

```python
# ---------------------------------------------------------------------------
# RefillService : recharge cashless depuis un PSP externe (Stripe, Payplug...)
# RefillService: cashless refill from an external PSP
# ---------------------------------------------------------------------------

class RefillService:
    """
    Service de recharge FED depuis un paiement bancaire externe.
    Appele par les webhooks PSP (Stripe aujourd'hui, autres demain).

    / FED refill service from an external bank payment.
    Called by PSP webhooks (Stripe today, others tomorrow).

    Contrat PSP-agnostique : fedow_core/PSP_INTERFACE.md
    """

    @staticmethod
    def process_cashless_refill(
        paiement_uuid,
        user,
        amount_cents,
        tenant,
        ip="0.0.0.0",
    ):
        """
        Cree une Transaction(action=REFILL) idempotente et credite le Token de l'user.
        / Creates an idempotent REFILL Transaction and credits the user's Token.

        Args:
            paiement_uuid: UUID du paiement externe (Paiement_stripe.uuid, ou autre PSP)
            user: TibilletUser a crediter
            amount_cents: int (montant en centimes, deja valide par le serializer)
            tenant: Client (generalement federation_fed)
            ip: str (IP de la requete, pour audit)

        Returns:
            Transaction: la transaction creee (ou existante si idempotence)

        Idempotence :
        Si une Transaction(checkout_stripe=paiement_uuid, action=REFILL) existe deja,
        on la retourne sans rien creer. Cela protege contre les retries Stripe.

        / If a Transaction(checkout_stripe=paiement_uuid, action=REFILL) already exists,
        we return it without creating anything. Protects against Stripe retries.
        """
        # L'asset FED est unique global (convention, cf. bootstrap_fed_asset)
        # / FED asset is globally unique (convention, see bootstrap_fed_asset)
        asset_fed = Asset.objects.get(category=Asset.FED)

        with transaction.atomic():
            # Idempotence : verifier si la Transaction existe deja
            # / Idempotence: check if Transaction already exists
            transaction_existante = Transaction.objects.filter(
                checkout_stripe=paiement_uuid,
                action=Transaction.REFILL,
            ).first()
            if transaction_existante:
                return transaction_existante

            # Fallback defensif : creer le wallet si absent.
            # Normalement, refill_wallet() a deja cree le wallet avant Stripe
            # (car la metadata Stripe a besoin de wallet.uuid).
            # / Defensive fallback: create wallet if missing.
            # Normally refill_wallet() already created it before Stripe.
            if user.wallet is None:
                from AuthBillet.models import Wallet
                user.wallet = Wallet.objects.create(
                    origin=tenant,
                    name=f"Wallet {user.email}",
                )
                user.save(update_fields=['wallet'])

            # Creation de la Transaction REFILL + credit du Token (atomique).
            # TransactionService.creer_recharge fait un atomic imbrique,
            # Django gere via savepoint.
            # / Create REFILL Transaction + credit Token (atomic).
            # TransactionService.creer_recharge uses nested atomic, handled by Django savepoint.
            nouvelle_transaction = TransactionService.creer_recharge(
                sender_wallet=asset_fed.wallet_origin,
                receiver_wallet=user.wallet,
                asset=asset_fed,
                montant_en_centimes=amount_cents,
                tenant=tenant,
                ip=ip,
                checkout_stripe_uuid=paiement_uuid,
                comment="Recharge FED via PSP (bootstrap contrat : PSP_INTERFACE.md)",
            )

            return nouvelle_transaction
```

- [ ] **Step 7.5 : Lancer les tests pour vérifier qu'ils passent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_refill_service.py -v
```
Expected : 3 tests PASS.

- [ ] **Step 7.6 : Lancer TOUS les tests fedow_core pour vérifier non-régression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_fedow_core.py tests/pytest/test_bank_transfer_service.py tests/pytest/test_refill_service.py -v
```
Expected : tous les tests passent (aucune régression sur les autres services).

- [ ] **Step 7.7 : Linter ruff**

```bash
docker exec lespass_django poetry run ruff check --fix /DjangoFiles/fedow_core/services.py
docker exec lespass_django poetry run ruff format /DjangoFiles/fedow_core/services.py
```
Expected : zéro warning ou corrections triviales.

- [ ] **Step 7.8 : Checkpoint mainteneur**

Message de commit suggéré :
```
feat(fedow_core): add RefillService.process_cashless_refill

Idempotent service that creates a REFILL Transaction and credits the user's
FED Token. Called by PSP webhooks (Stripe today, others tomorrow).
Contract documented in fedow_core/PSP_INTERFACE.md.
Part of Session 31 Phase A (recharge FED V2).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## Task 8 — Documentation contrat `PSP_INTERFACE.md`

**Files :**
- Create: `fedow_core/PSP_INTERFACE.md`

- [ ] **Step 8.1 : Créer le fichier de contrat**

```markdown
# PSP Interface — Contrat de recharge FED

> Pour ajouter un nouveau PSP (Payplug, Lydia, Stripe alternatif...), respecter ce contrat.

## Responsabilités

### Ce que le PSP fait

1. **Création d'un checkout / intent de paiement** dans son propre module (`PaiementXxx/refill_federation.py`)
   - Créer le `Paiement_xxx` en base (dans le tenant `federation_fed`)
   - Injecter la metadata requise (voir section "Metadata attendue")
   - Configurer le return URL vers `/my_account/<paiement_uuid>/return_refill_wallet/`
   - **Pas de compte connecté** : la recharge FED utilise le compte central du PSP
   - **Pas de paiement différé** (SEPA, virement, etc.) : UX recharge immédiate seulement
2. **Gestion du webhook PSP** (dans `ApiBillet/views.py` ou un module dédié)
   - Valider la signature du webhook (sécurité PSP)
   - Extraire la metadata
   - Anti-tampering : vérifier que le montant PSP correspond au montant stocké en base
   - Appeler `RefillService.process_cashless_refill(...)` avec les bons arguments
   - Marquer le `Paiement_xxx.status = PAID`

### Ce que `RefillService` fait (fourni par `fedow_core`)

- Vérifier l'idempotence (pas de doublon si le webhook est rejoué)
- Créer `Transaction(action=REFILL, asset=FED, amount=amount_cents, ...)` dans `federation_fed`
- Créditer `Token(wallet=user.wallet, asset=FED).value` atomiquement
- Retourner la `Transaction` (nouvelle ou existante)

Le PSP n'a **jamais** à toucher directement aux `Token`, `Wallet`, ou `Transaction`. Tout passe par `RefillService`.

## Signature de `RefillService.process_cashless_refill`

```python
from fedow_core.services import RefillService
from fedow_core.models import Transaction

tx: Transaction = RefillService.process_cashless_refill(
    paiement_uuid=paiement.uuid,        # UUID — identifiant stable du paiement externe
    user=paiement.user,                 # TibilletUser — bénéficiaire du crédit
    amount_cents=int(...),              # int centimes — montant validé et sécurisé
    tenant=tenant_federation_fed,       # Client — doit être le tenant federation_fed
    ip=get_request_ip(request),         # str — IP de la requête pour audit
)
```

## Metadata attendue sur le paiement PSP

Pour que le webhook puisse retrouver le contexte, injecter au minimum :

| Clé | Valeur | Usage côté webhook |
|---|---|---|
| `tenant` | UUID du tenant `federation_fed` | Charger le bon schéma avant `Paiement_xxx.objects.get()` |
| `paiement_xxx_uuid` | UUID du paiement | Retrouver l'enregistrement local |
| `refill_type` | `'FED'` | Dispatch dans le webhook (filtre : c'est une recharge FED) |
| `wallet_receiver_uuid` | UUID du wallet user | Debug / audit |
| `asset_uuid` | UUID de l'asset FED | Debug / audit |

Chaque PSP adapte les noms si son système impose des contraintes (ex: Stripe accepte des clés libres, d'autres limitent à certains noms).

## Checklist d'implémentation d'un nouveau PSP

- [ ] Créer `Paiement<PSP>` en TENANT_APPS avec au minimum : `uuid`, `user`, `source` (avec valeur `CASHLESS_REFILL`), `status`, lien vers `LigneArticle`
- [ ] Créer `Paiement<PSP>/refill_federation.py` avec une classe `CreationPaiement<PSP>Federation`
- [ ] Ajouter une action dans le webhook `<PSP>` qui filtre `metadata.refill_type == 'FED'` et appelle `RefillService.process_cashless_refill`
- [ ] Tests pytest : nominal, idempotence, anti-tampering
- [ ] Pas de compte connecté, pas de paiement différé
- [ ] Respecter la structure `tenant_context(tenant_federation_fed)` pour toutes les opérations TENANT_APPS

## Référence

- Spec produit : `TECH DOC/Laboutik sessions/Session 31 - Recharge FED V2/SPEC_RECHARGE_FED_V2.md`
- Implémentation Stripe de référence (Phase B) : `PaiementStripe/refill_federation.py` + `ApiBillet/views.py:1042+`
```

- [ ] **Step 8.2 : Vérifier le rendu markdown**

```bash
docker exec lespass_django cat /DjangoFiles/fedow_core/PSP_INTERFACE.md | head -30
```
Expected : la doc commence par `# PSP Interface — Contrat de recharge FED`.

- [ ] **Step 8.3 : Checkpoint mainteneur**

Message de commit suggéré :
```
docs(fedow_core): add PSP_INTERFACE.md contract

Documents the contract that any new PSP (Payplug, Lydia, alternative Stripe...)
must respect to integrate with RefillService. Defines the expected metadata,
the service signature, and an implementation checklist.
Part of Session 31 Phase A (recharge FED V2).
```

---

## Task 9 — Validation finale Phase A

**Files :** aucun

- [ ] **Step 9.1 : Tous les tests Phase A passent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_bootstrap_fed_asset.py tests/pytest/test_refill_service.py tests/pytest/test_refill_serializer.py -v
```
Expected : 12 tests PASS (4 bootstrap + 3 service + 5 serializer).

- [ ] **Step 9.2 : Pas de régression sur les tests fedow_core et BaseBillet**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_fedow_core.py tests/pytest/test_bank_transfer_service.py tests/pytest/test_verify_transactions.py -v
```
Expected : tous les tests PASS.

- [ ] **Step 9.3 : `manage.py check` propre**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```
Expected : `System check identified no issues (0 silenced).`

- [ ] **Step 9.4 : Makemigrations propre (pas de migration oubliée)**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --check
```
Expected : `No changes detected`

- [ ] **Step 9.5 : CHANGELOG.md à mettre à jour (mainteneur)**

Proposer au mainteneur d'ajouter une section dans `CHANGELOG.md` (au format bilingue FR/EN existant) :

```markdown
## N. Recharge FED V2 — Phase A / FED V2 Refill — Phase A

**Quoi / What:** Fondations du moteur de recharge FED V2 local (sans serveur Fedow distant).
- Nouveau tenant `federation_fed` (catégorie `Client.FED='E'`)
- Nouveau `Product` de recharge (catégorie `RECHARGE_CASHLESS_FED`)
- Nouveau `Paiement_stripe.source = CASHLESS_REFILL`
- Management command `bootstrap_fed_asset` (idempotente)
- Nouveau `RefillAmountSerializer` (bornes 1 € / 500 €)
- Nouveau `RefillService.process_cashless_refill()` (idempotent, PSP-agnostique)
- Documentation contrat `fedow_core/PSP_INTERFACE.md`

**Pourquoi / Why:** Préparer la bascule de la recharge FED depuis le serveur Fedow distant vers le moteur local `fedow_core`. Phase A = socle, Phase B = gateway Stripe + webhook, Phase C = UI, Phase D = tests E2E.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Customers/models.py` | +catégorie `FED = 'E'` |
| `BaseBillet/models.py` | +`Product.RECHARGE_CASHLESS_FED` et +`Paiement_stripe.CASHLESS_REFILL` |
| `fedow_core/services.py` | +classe `RefillService` |
| `fedow_core/management/commands/bootstrap_fed_asset.py` | Nouveau |
| `fedow_core/PSP_INTERFACE.md` | Nouveau |
| `PaiementStripe/serializers.py` | Nouveau (`RefillAmountSerializer`) |
| `Administration/management/commands/install.py` | +hook `bootstrap_fed_asset` |
| `laboutik/management/commands/create_test_pos_data.py` | +hook `bootstrap_fed_asset` |

### Migration
- **Migration nécessaire / Migration required:** Oui
- `Customers.XXXX_alter_client_categorie`
- `BaseBillet.XXXX_alter_product_categorie_article_alter_paiement_stripe_source`
- Commande : `docker exec lespass_django poetry run python manage.py migrate_schemas --executor=multiprocessing`
- Management command requise après la migration : `docker exec lespass_django poetry run python manage.py bootstrap_fed_asset`
```

- [ ] **Step 9.6 : Fichier `A TESTER et DOCUMENTER/recharge-fed-v2-phase-a.md` (mainteneur)**

Proposer au mainteneur de créer ce fichier :

```markdown
# Recharge FED V2 — Phase A (fondations)

## Ce qui a été fait
Fondations techniques de la recharge FED V2. Pas d'UI, pas de webhook à ce stade.

### Modifications
| Fichier | Changement |
|---|---|
| `Customers/models.py` | +catégorie `FED = 'E'` |
| `BaseBillet/models.py` | +`Product.RECHARGE_CASHLESS_FED` + `Paiement_stripe.CASHLESS_REFILL` |
| `fedow_core/services.py` | +classe `RefillService` |
| `fedow_core/management/commands/bootstrap_fed_asset.py` | Nouveau |
| `PaiementStripe/serializers.py` | Nouveau |
| `Administration/management/commands/install.py` | hook bootstrap |
| `laboutik/management/commands/create_test_pos_data.py` | hook bootstrap |

## Tests à réaliser

### Test 1 : Bootstrap idempotent
1. `docker exec lespass_django poetry run python manage.py bootstrap_fed_asset`
2. Vérifier la sortie : "Tenant federation_fed cree" (si premier run) ou "deja present, reutilise"
3. Relancer la même commande
4. Vérifier qu'aucun doublon n'est créé

### Test 2 : Vérifier l'Asset FED en base
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from fedow_core.models import Asset
from Customers.models import Client
print('Assets FED:', list(Asset.objects.filter(category=Asset.FED).values('uuid', 'name', 'wallet_origin__name')))
print('Tenants FED:', list(Client.objects.filter(categorie=Client.FED).values('schema_name', 'name')))
"
```
Attendu : exactement 1 Asset FED et 1 Tenant `federation_fed`.

### Test 3 : Vérifier le Product/Price dans le schema federation_fed
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import Product
tenant = Client.objects.get(schema_name='federation_fed')
with tenant_context(tenant):
    product = Product.objects.get(categorie_article=Product.RECHARGE_CASHLESS_FED)
    print('Product:', product.name, 'Price:', product.prices.first().name)
"
```
Attendu : `Product: Recharge monnaie fédérée Price: Montant libre`

### Test 4 : RefillService idempotent depuis le shell
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
import uuid
from Customers.models import Client
from AuthBillet.models import TibilletUser
from fedow_core.services import RefillService
from fedow_core.models import Transaction

tenant = Client.objects.get(schema_name='federation_fed')
user = TibilletUser.objects.filter(email='admin@admin.com').first()
paiement_uuid = uuid.uuid4()
tx1 = RefillService.process_cashless_refill(paiement_uuid, user, 1000, tenant)
tx2 = RefillService.process_cashless_refill(paiement_uuid, user, 1000, tenant)
print('Memes:', tx1.pk == tx2.pk)
print('Count:', Transaction.objects.filter(checkout_stripe=paiement_uuid).count())
"
```
Attendu : `Memes: True` et `Count: 1`.

## Compatibilité
- Pas de rupture : aucun code existant ne référence les nouveaux éléments
- Fedow distant continue de fonctionner normalement (hors scope Phase A)
- Les tenants existants ne sont pas impactés (ni migration de données, ni modification de comportement)
```

- [ ] **Step 9.7 : Checkpoint mainteneur final Phase A**

La Phase A est terminée. Le mainteneur peut :
1. Commit chaque tâche avec les messages proposés
2. Tester manuellement depuis le shell
3. Documenter dans `CHANGELOG.md` et `A TESTER et DOCUMENTER/`
4. Passer à Phase B (plan à écrire ensuite) quand prêt

---

## Self-review (après écriture du plan)

**Spec coverage (Phase A 8 items) :**
- Migration Customers.FED → Task 1 ✓
- Migration BaseBillet (CASHLESS_REFILL + RECHARGE_CASHLESS_FED) → Task 2 ✓
- Management command bootstrap_fed_asset → Task 3 ✓
- Hook dans install.py → Task 4 ✓
- Ajout dans create_test_pos_data → Task 5 ✓
- RefillAmountSerializer → Task 6 ✓
- RefillService.process_cashless_refill → Task 7 ✓
- PSP_INTERFACE.md → Task 8 ✓
- Validation finale + CHANGELOG + A TESTER → Task 9 ✓

**Placeholder scan :** OK, aucun "TBD" ou "implement later".

**Cohérence des types et signatures :**
- `RefillService.process_cashless_refill(paiement_uuid, user, amount_cents, tenant, ip)` utilisée de façon cohérente dans Task 7 tests et implémentation
- `bootstrap_fed_asset` sans argument, idempotente — cohérent entre Task 3 et Tasks 4/5/9
- `RefillAmountSerializer.MIN_CENTS = 100`, `MAX_CENTS = 50000` cohérents Task 6

**Convention conversion euros/centimes** (flou résiduel Phase C) : non applicable en Phase A (le serializer reçoit déjà des centimes, la vue Phase C convertira). Noté pour Phase C.
