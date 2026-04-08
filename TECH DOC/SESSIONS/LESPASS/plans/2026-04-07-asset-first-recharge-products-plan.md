# Asset-first recharge products — Plan d'implementation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** L'Asset fedow_core drive la creation des produits de recharge — plus de bouton "Recharge" sans Asset, plus de lookup par categorie.

**Architecture:** Signal post_save sur fedow_core.Asset cree automatiquement un Product multi-tarif (1/5/10/Libre) et l'attache aux PV CASHLESS. Le refactoring de `_executer_recharges()` et `_payer_par_nfc()` remplace le lookup par categorie par un lien direct `product.asset`.

**Tech Stack:** Django 4.x, django-tenants, fedow_core (SHARED_APPS), pytest

**Spec:** `TECH DOC/SESSIONS/LESPASS/specs/2026-04-07-asset-first-recharge-products-design.md`

---

## File Structure

| Fichier | Action | Responsabilite |
|---------|--------|----------------|
| `BaseBillet/models.py` | Modifier | Ajout FK `Product.asset → fedow_core.Asset` |
| `BaseBillet/migrations/XXXX_product_asset_fk.py` | Creer | Migration FK |
| `fedow_core/signals.py` | Creer | Signal post_save Asset → Product + Prices + PV CASHLESS |
| `fedow_core/apps.py` | Modifier | Enregistre le signal dans `ready()` |
| `laboutik/views.py` | Modifier | Refactor `_executer_recharges`, `_payer_par_nfc`, filtre `_construire_donnees_articles` |
| `laboutik/management/commands/create_test_pos_data.py` | Modifier | Cree Assets au lieu de Products recharge |
| `tests/pytest/test_asset_recharge_signal.py` | Creer | Tests du signal et du filtre affichage |
| `tests/pytest/test_paiement_cashless.py` | Modifier | Adapter fixture `asset_tlf` au nouveau flow |

---

### Task 1 : Migration — FK Product.asset

**Files:**
- Modify: `BaseBillet/models.py:1369` (apres `prix_achat`)
- Create: `BaseBillet/migrations/XXXX_product_asset_fk.py`

- [ ] **Step 1: Ajouter le champ FK sur Product**

Dans `BaseBillet/models.py`, apres le champ `prix_achat` (ligne 1369), avant `def fedow_category(self):` (ligne 1371), ajouter :

```python
    # Asset fedow_core lie a ce produit de recharge.
    # Rempli automatiquement par le signal post_save de fedow_core.Asset.
    # Null pour les produits non-cashless (VT, AD, BI, etc.).
    # / fedow_core Asset linked to this top-up product.
    # Auto-filled by fedow_core.Asset post_save signal.
    # Null for non-cashless products (VT, AD, BI, etc.).
    asset = models.ForeignKey(
        "fedow_core.Asset",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="products",
        verbose_name=_("Asset"),
        help_text=_(
            "Asset fedow lie a ce produit de recharge. "
            "/ Fedow asset linked to this top-up product."
        ),
    )
```

- [ ] **Step 2: Generer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations BaseBillet --name product_asset_fk
```

Expected: migration creee dans `BaseBillet/migrations/`

- [ ] **Step 3: Appliquer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --tenant
```

Expected: migration appliquee sans erreur

---

### Task 2 : Signal post_save sur fedow_core.Asset

**Files:**
- Create: `fedow_core/signals.py`
- Modify: `fedow_core/apps.py`

- [ ] **Step 1: Ecrire le test du signal — creation Asset TLF**

Creer `tests/pytest/test_asset_recharge_signal.py` :

```python
"""
tests/pytest/test_asset_recharge_signal.py — Tests du signal post_save Asset.
Verifie que la creation d'un Asset TLF/TNF/TIM cree automatiquement
un Product de recharge avec 4 Prices et l'attache aux PV CASHLESS.

/ Tests for Asset post_save signal.
Verifies that creating a TLF/TNF/TIM Asset auto-creates a top-up
Product with 4 Prices and attaches it to CASHLESS POS.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_asset_recharge_signal.py -v
"""

import sys
sys.path.insert(0, '/DjangoFiles')

import django
django.setup()

import pytest
from decimal import Decimal

from django.db import connection
from django_tenants.utils import schema_context

from AuthBillet.models import Wallet
from BaseBillet.models import CategorieProduct, Product, Price
from Customers.models import Client
from fedow_core.models import Asset
from fedow_core.services import AssetService
from laboutik.models import PointDeVente


TENANT_SCHEMA = 'lespass'


@pytest.fixture(scope="module")
def tenant():
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture(scope="module")
def wallet_lieu(tenant):
    """Wallet du lieu pour les Assets.
    / Venue wallet for Assets."""
    wallet, _ = Wallet.objects.get_or_create(
        origin=tenant,
        defaults={"name": f"[test_signal] {tenant.name}"},
    )
    return wallet


@pytest.fixture(scope="module")
def pv_cashless():
    """Point de vente CASHLESS pour verifier l'auto-attachement.
    / CASHLESS POS to verify auto-attachment."""
    with schema_context(TENANT_SCHEMA):
        pv, _ = PointDeVente.objects.get_or_create(
            name="[test_signal] PV Cashless",
            defaults={
                "comportement": PointDeVente.CASHLESS,
                "service_direct": True,
            },
        )
        return pv


# --- Tests creation ---

@pytest.mark.django_db(transaction=True)
def test_creation_asset_tlf_cree_product_recharge(tenant, wallet_lieu, pv_cashless):
    """Creer un Asset TLF → un Product RE avec 4 Prices doit apparaitre.
    / Creating a TLF Asset → a RE Product with 4 Prices must appear."""
    with schema_context(TENANT_SCHEMA):
        # Nettoyer les Products de recharge existants lies a un Asset de test
        # / Clean up existing top-up products linked to a test asset
        Product.objects.filter(
            name__startswith="Recharge [test_signal]",
        ).delete()

        asset_tlf = AssetService.creer_asset(
            tenant=tenant,
            name="[test_signal] Monnaie locale",
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=wallet_lieu,
        )

        # Le signal doit avoir cree un Product
        # / Signal should have created a Product
        produit = Product.objects.filter(asset=asset_tlf).first()
        assert produit is not None, "Le signal n'a pas cree de Product pour l'Asset TLF"
        assert produit.methode_caisse == Product.RECHARGE_EUROS
        assert "Recharge" in produit.name
        assert produit.archive is False

        # 4 Prices : 1, 5, 10, Libre
        # / 4 Prices: 1, 5, 10, Free
        prices = list(Price.objects.filter(product=produit).order_by("order"))
        assert len(prices) == 4, f"Attendu 4 Prices, trouve {len(prices)}"
        assert prices[0].prix == Decimal("1.00")
        assert prices[1].prix == Decimal("5.00")
        assert prices[2].prix == Decimal("10.00")
        assert prices[3].free_price is True

        # Le Product doit etre dans le PV CASHLESS
        # / Product must be in the CASHLESS POS
        assert pv_cashless.products.filter(pk=produit.pk).exists(), \
            "Le Product n'a pas ete ajoute au PV CASHLESS"

        # Nettoyage / Cleanup
        produit.delete()
        asset_tlf.delete()


@pytest.mark.django_db(transaction=True)
def test_creation_asset_tnf_cree_product_cadeau(tenant, wallet_lieu):
    """Creer un Asset TNF → un Product RC doit apparaitre.
    / Creating a TNF Asset → a RC Product must appear."""
    with schema_context(TENANT_SCHEMA):
        asset_tnf = AssetService.creer_asset(
            tenant=tenant,
            name="[test_signal] Cadeau",
            category=Asset.TNF,
            currency_code="CAD",
            wallet_origin=wallet_lieu,
        )

        produit = Product.objects.filter(asset=asset_tnf).first()
        assert produit is not None
        assert produit.methode_caisse == Product.RECHARGE_CADEAU
        assert "cadeau" in produit.name.lower()

        # Nettoyage / Cleanup
        produit.delete()
        asset_tnf.delete()


@pytest.mark.django_db(transaction=True)
def test_creation_asset_tim_cree_product_temps(tenant, wallet_lieu):
    """Creer un Asset TIM → un Product TM doit apparaitre.
    / Creating a TIM Asset → a TM Product must appear."""
    with schema_context(TENANT_SCHEMA):
        asset_tim = AssetService.creer_asset(
            tenant=tenant,
            name="[test_signal] Temps",
            category=Asset.TIM,
            currency_code="TMP",
            wallet_origin=wallet_lieu,
        )

        produit = Product.objects.filter(asset=asset_tim).first()
        assert produit is not None
        assert produit.methode_caisse == Product.RECHARGE_TEMPS

        # Nettoyage / Cleanup
        produit.delete()
        asset_tim.delete()


@pytest.mark.django_db(transaction=True)
def test_creation_asset_fed_ne_cree_pas_product(tenant, wallet_lieu):
    """Creer un Asset FED → aucun Product ne doit etre cree.
    / Creating a FED Asset → no Product should be created."""
    with schema_context(TENANT_SCHEMA):
        # Supprimer l'eventuel FED existant (contrainte unique)
        # / Delete existing FED if any (unique constraint)
        Asset.objects.filter(category=Asset.FED).delete()

        asset_fed = AssetService.creer_asset(
            tenant=tenant,
            name="[test_signal] Stripe Fed",
            category=Asset.FED,
            currency_code="EUR",
            wallet_origin=wallet_lieu,
        )

        produit = Product.objects.filter(asset=asset_fed).first()
        assert produit is None, "Le signal a cree un Product pour un Asset FED — il ne devrait pas"

        asset_fed.delete()


# --- Tests archivage ---

@pytest.mark.django_db(transaction=True)
def test_archivage_asset_archive_product(tenant, wallet_lieu):
    """Archiver un Asset → le Product doit etre archive.
    / Archiving an Asset → the Product must be archived."""
    with schema_context(TENANT_SCHEMA):
        asset = AssetService.creer_asset(
            tenant=tenant,
            name="[test_signal] Archive Test",
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=wallet_lieu,
        )

        produit = Product.objects.get(asset=asset)
        assert produit.archive is False

        # Archiver l'Asset / Archive the Asset
        asset.archive = True
        asset.save(update_fields=["archive"])

        produit.refresh_from_db()
        assert produit.archive is True, "Le Product n'a pas ete archive"

        # Reactiver / Reactivate
        asset.archive = False
        asset.save(update_fields=["archive"])

        produit.refresh_from_db()
        assert produit.archive is False, "Le Product n'a pas ete reactive"

        # Nettoyage / Cleanup
        produit.delete()
        asset.delete()


@pytest.mark.django_db(transaction=True)
def test_renommage_asset_met_a_jour_product(tenant, wallet_lieu):
    """Renommer un Asset → le Product doit etre renomme.
    / Renaming an Asset → the Product must be renamed."""
    with schema_context(TENANT_SCHEMA):
        asset = AssetService.creer_asset(
            tenant=tenant,
            name="[test_signal] Avant",
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=wallet_lieu,
        )

        produit = Product.objects.get(asset=asset)
        assert "Avant" in produit.name

        asset.name = "[test_signal] Apres"
        asset.save(update_fields=["name"])

        produit.refresh_from_db()
        assert "Apres" in produit.name, f"Nom non mis a jour : {produit.name}"

        # Nettoyage / Cleanup
        produit.delete()
        asset.delete()
```

- [ ] **Step 2: Lancer le test pour verifier qu'il echoue**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_asset_recharge_signal.py -v -x
```

Expected: FAIL — le signal n'existe pas encore, les Products ne sont pas crees.

- [ ] **Step 3: Creer `fedow_core/signals.py`**

```python
"""
Signal post_save sur fedow_core.Asset.
Cree automatiquement un Product de recharge multi-tarif
quand un Asset TLF/TNF/TIM est cree.

/ post_save signal on fedow_core.Asset.
Auto-creates a multi-rate top-up Product
when a TLF/TNF/TIM Asset is created.

LOCALISATION : fedow_core/signals.py
"""

import logging
from decimal import Decimal

from django.db import connection
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from fedow_core.models import Asset

logger = logging.getLogger(__name__)

# Mapping : Asset.category → (Product.methode_caisse, prefixe du nom)
# / Mapping: Asset.category → (Product.methode_caisse, name prefix)
CATEGORY_TO_RECHARGE = {
    Asset.TLF: ("RE", "Recharge"),
    Asset.TNF: ("RC", "Recharge cadeau"),
    Asset.TIM: ("TM", "Recharge temps"),
}

# Tarifs par defaut pour les produits de recharge auto-crees
# / Default prices for auto-created top-up products
TARIFS_DEFAUT = [
    {"name": "1", "prix": Decimal("1.00"), "free_price": False, "order": 1},
    {"name": "5", "prix": Decimal("5.00"), "free_price": False, "order": 2},
    {"name": "10", "prix": Decimal("10.00"), "free_price": False, "order": 3},
    {"name": "Libre", "prix": Decimal("0"), "free_price": True, "order": 4},
]

# Couleurs par defaut pour les boutons POS selon la categorie
# / Default POS button colors by category
COULEURS_PAR_CATEGORIE = {
    Asset.TLF: {"fond": "#10B981", "texte": "#FFFFFF", "icon": "fa-coins"},
    Asset.TNF: {"fond": "#EC4899", "texte": "#FFFFFF", "icon": "fa-gift"},
    Asset.TIM: {"fond": "#8B5CF6", "texte": "#FFFFFF", "icon": "fa-clock"},
}


@receiver(post_save, sender=Asset)
def creer_ou_mettre_a_jour_product_recharge(sender, instance, created, **kwargs):
    """
    Signal post_save sur Asset.
    - Creation (TLF/TNF/TIM) : cree un Product + 4 Prices + attache aux PV CASHLESS.
    - Modification : propage archivage et renommage.

    / post_save signal on Asset.
    - Creation (TLF/TNF/TIM): creates Product + 4 Prices + attaches to CASHLESS POS.
    - Modification: propagates archiving and renaming.
    """
    # Import ici pour eviter les imports circulaires
    # / Import here to avoid circular imports
    from BaseBillet.models import CategorieProduct, Product, Price
    from laboutik.models import PointDeVente

    categorie_asset = instance.category

    # Seuls TLF, TNF, TIM generent des produits de recharge
    # / Only TLF, TNF, TIM generate top-up products
    if categorie_asset not in CATEGORY_TO_RECHARGE:
        return

    methode_caisse, prefixe_nom = CATEGORY_TO_RECHARGE[categorie_asset]
    nom_produit = f"{prefixe_nom} {instance.name}"

    if created:
        # --- Creation : nouveau Product + Prices + PV ---
        # / Creation: new Product + Prices + POS

        # Trouver ou creer la CategorieProduct "Cashless"
        # / Find or create the "Cashless" CategorieProduct
        categorie_cashless, _ = CategorieProduct.objects.get_or_create(
            name="Cashless",
            defaults={
                "icon": "fa-wallet",
                "couleur_texte": "#FFFFFF",
                "couleur_fond": "#10B981",
            },
        )

        couleurs = COULEURS_PAR_CATEGORIE.get(categorie_asset, {})

        produit = Product.objects.create(
            name=nom_produit,
            methode_caisse=methode_caisse,
            asset=instance,
            categorie_pos=categorie_cashless,
            couleur_fond_pos=couleurs.get("fond", "#10B981"),
            couleur_texte_pos=couleurs.get("texte", "#FFFFFF"),
            icon_pos=couleurs.get("icon", "fa-coins"),
        )

        # Creer les 4 tarifs par defaut (1, 5, 10, Libre)
        # / Create the 4 default prices (1, 5, 10, Free)
        for tarif in TARIFS_DEFAUT:
            Price.objects.create(
                product=produit,
                name=tarif["name"],
                prix=tarif["prix"],
                free_price=tarif["free_price"],
                publish=True,
                order=tarif["order"],
            )

        # Ajouter le Product a tous les PV CASHLESS du tenant
        # / Add the Product to all CASHLESS POS of the tenant
        pvs_cashless = PointDeVente.objects.filter(
            comportement=PointDeVente.CASHLESS,
        )
        for pv in pvs_cashless:
            pv.products.add(produit)

        logger.info(
            f"Product de recharge cree : '{produit.name}' "
            f"(methode={methode_caisse}) pour Asset '{instance.name}' "
            f"({instance.category}), attache a {pvs_cashless.count()} PV CASHLESS"
        )

    else:
        # --- Modification : propager archivage et renommage ---
        # / Modification: propagate archiving and renaming
        produit = Product.objects.filter(asset=instance).first()
        if produit is None:
            return

        champs_a_mettre_a_jour = []

        # Propagation archivage
        # / Archive propagation
        if produit.archive != instance.archive:
            produit.archive = instance.archive
            champs_a_mettre_a_jour.append("archive")

        # Propagation renommage
        # / Name propagation
        nom_attendu = f"{prefixe_nom} {instance.name}"
        if produit.name != nom_attendu:
            produit.name = nom_attendu
            champs_a_mettre_a_jour.append("name")

        if champs_a_mettre_a_jour:
            produit.save(update_fields=champs_a_mettre_a_jour)
            logger.info(
                f"Product '{produit.name}' mis a jour : {champs_a_mettre_a_jour}"
            )
```

- [ ] **Step 4: Enregistrer le signal dans `fedow_core/apps.py`**

Remplacer le contenu de `fedow_core/apps.py` par :

```python
from django.apps import AppConfig


class FedowCoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'fedow_core'
    verbose_name = 'Fedow Core'

    def ready(self):
        import fedow_core.signals  # noqa: F401
```

- [ ] **Step 5: Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_asset_recharge_signal.py -v
```

Expected: tous les tests passent (6 tests).

---

### Task 3 : Filtre affichage dans `_construire_donnees_articles()`

**Files:**
- Modify: `laboutik/views.py:475-485` (requete produits + boucle)

- [ ] **Step 1: Ecrire le test du filtre**

Ajouter dans `tests/pytest/test_asset_recharge_signal.py` :

```python
# --- Tests filtre affichage ---

@pytest.mark.django_db(transaction=True)
def test_filtre_affichage_product_recharge_sans_asset(pv_cashless):
    """Un Product RE sans Asset ne doit pas apparaitre dans les articles POS.
    / A RE Product without Asset must not appear in POS articles."""
    with schema_context(TENANT_SCHEMA):
        from laboutik.views import _construire_donnees_articles

        # Creer un Product orphelin (sans asset) de type recharge
        # / Create an orphan Product (no asset) of type top-up
        produit_orphelin = Product.objects.create(
            name="[test_filtre] Recharge orpheline",
            methode_caisse=Product.RECHARGE_EUROS,
            asset=None,
        )
        pv_cashless.products.add(produit_orphelin)
        # Creer un Price pour que le produit ne soit pas filtre par "pas de prix"
        # / Create a Price so the product isn't filtered by "no price"
        Price.objects.create(
            product=produit_orphelin,
            name="10",
            prix=Decimal("10.00"),
            publish=True,
        )

        articles = _construire_donnees_articles(pv_cashless)
        noms = [a["name"] for a in articles]
        assert "[test_filtre] Recharge orpheline" not in noms, \
            "Un Product RE sans Asset apparait dans le POS"

        # Nettoyage / Cleanup
        pv_cashless.products.remove(produit_orphelin)
        produit_orphelin.delete()


@pytest.mark.django_db(transaction=True)
def test_filtre_affichage_product_recharge_asset_archive(tenant, wallet_lieu, pv_cashless):
    """Un Product RE dont l'Asset est archive ne doit pas apparaitre.
    / A RE Product with archived Asset must not appear."""
    with schema_context(TENANT_SCHEMA):
        from laboutik.views import _construire_donnees_articles

        asset = AssetService.creer_asset(
            tenant=tenant,
            name="[test_filtre] Archive",
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=wallet_lieu,
        )
        # Le signal a cree le Product et l'a attache au PV
        # / Signal created the Product and attached it to POS
        produit = Product.objects.get(asset=asset)

        # Avant archivage : le Product doit apparaitre
        # / Before archiving: Product must appear
        articles_avant = _construire_donnees_articles(pv_cashless)
        noms_avant = [a["name"] for a in articles_avant]
        assert produit.name in noms_avant

        # Archiver l'Asset / Archive the Asset
        asset.archive = True
        asset.save(update_fields=["archive"])

        articles_apres = _construire_donnees_articles(pv_cashless)
        noms_apres = [a["name"] for a in articles_apres]
        assert produit.name not in noms_apres, \
            "Le Product avec Asset archive apparait encore dans le POS"

        # Nettoyage / Cleanup
        produit.delete()
        asset.delete()
```

- [ ] **Step 2: Lancer le test pour verifier qu'il echoue**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_asset_recharge_signal.py::test_filtre_affichage_product_recharge_sans_asset -v -x
```

Expected: FAIL — le filtre n'existe pas encore, le Product orphelin apparait.

- [ ] **Step 3: Implementer le filtre dans `_construire_donnees_articles()`**

Dans `laboutik/views.py`, modifier la requete `produits` (ligne 475-482) pour ajouter `select_related("asset")` :

```python
    produits = list(
        point_de_vente_instance.products.filter(
            Q(methode_caisse__isnull=False) | Q(categorie_article=Product.ADHESION)
        )
        .select_related("categorie_pos", "stock_inventaire", "asset")
        .prefetch_related(prix_euros_prefetch)
        .order_by("poids", "name")
    )
```

Puis dans la boucle `for product in produits:` (ligne 485), ajouter le filtre **avant** le check `if not product.prix_euros:` (ligne 488) :

```python
    for product in produits:
        # Produits de recharge sans Asset lie, ou Asset archive/inactif → ne pas afficher
        # / Top-up products without linked Asset, or archived/inactive Asset → skip
        if product.methode_caisse in METHODES_RECHARGE:
            if product.asset is None or product.asset.archive or not product.asset.active:
                continue

        # Premier prix publie en euros (deja filtre par le Prefetch)
        # First published EUR price (already filtered by Prefetch)
        if not product.prix_euros:
            continue
```

- [ ] **Step 4: Lancer les tests du filtre**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_asset_recharge_signal.py -v -x
```

Expected: tous les tests passent (8 tests).

---

### Task 4 : Refactoring `_executer_recharges()`

**Files:**
- Modify: `laboutik/views.py:4050-4186`

- [ ] **Step 1: Lire la fonction actuelle**

Lire `laboutik/views.py` lignes 4050-4186 pour avoir le code complet de `_executer_recharges()`.

- [ ] **Step 2: Remplacer les 3 blocs par une boucle generique**

Remplacer le contenu de `_executer_recharges()` (lignes 4050-4186) par :

```python
def _executer_recharges(
    articles_panier, wallet_client, carte_client, code_methode_paiement, ip_client
):
    """
    Execute les recharges contenues dans le panier.
    Chaque article de recharge connait son Asset via product.asset (FK directe).
    Executes top-ups in the cart.
    Each top-up article knows its Asset via product.asset (direct FK).

    LOCALISATION : laboutik/views.py

    DOIT etre appelee a l'interieur d'un bloc transaction.atomic().
    MUST be called inside a transaction.atomic() block.

    :param articles_panier: liste de dicts (seulement les articles recharge)
    :param wallet_client: Wallet du client a crediter
    :param carte_client: CarteCashless du client
    :param code_methode_paiement: code du moyen de paiement ("espece", "carte_bancaire", "CH")
    :param ip_client: adresse IP de la requete
    :return: None
    """
    tenant_courant = connection.tenant
    ip_client_str = ip_client or "0.0.0.0"

    # Regrouper les articles par Asset pour faire une seule transaction par Asset
    # / Group articles by Asset to make one transaction per Asset
    articles_par_asset = {}
    for article in articles_panier:
        asset = article["product"].asset
        if asset is None:
            logger.warning(
                f"Product de recharge '{article['product'].name}' sans Asset — ignore"
            )
            continue
        if asset.uuid not in articles_par_asset:
            articles_par_asset[asset.uuid] = {
                "asset": asset,
                "articles": [],
            }
        articles_par_asset[asset.uuid]["articles"].append(article)

    for groupe in articles_par_asset.values():
        asset = groupe["asset"]
        articles_du_groupe = groupe["articles"]

        total_centimes = _calculer_total_panier_centimes(articles_du_groupe)

        # Determiner le moyen de paiement pour la LigneArticle
        # Les recharges cadeau (RC) et temps (TM) sont toujours gratuites,
        # quel que soit le moyen de paiement choisi par le caissier.
        # / Determine payment method for LigneArticle.
        # Gift (RC) and time (TM) top-ups are always free,
        # regardless of the payment method chosen by the cashier.
        methode_du_groupe = articles_du_groupe[0]["product"].methode_caisse
        est_recharge_gratuite = methode_du_groupe in METHODES_RECHARGE_GRATUITES
        code_methode_pour_ligne = "gift" if est_recharge_gratuite else code_methode_paiement

        TransactionService.creer_recharge(
            sender_wallet=asset.wallet_origin,
            receiver_wallet=wallet_client,
            asset=asset,
            montant_en_centimes=total_centimes,
            tenant=tenant_courant,
            ip=ip_client_str,
        )
        _creer_lignes_articles(
            articles_du_groupe,
            code_methode_pour_ligne,
            asset_uuid=asset.uuid,
            carte=carte_client,
            wallet=wallet_client,
        )
```

- [ ] **Step 3: Lancer les tests de paiement cashless**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_paiement_cashless.py -v -x
```

Expected: tous les tests passent.

- [ ] **Step 4: Lancer les tests de retour carte / recharges**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_retour_carte_recharges.py -v -x
```

Expected: tous les tests passent.

---

### Task 5 : Refactoring `_payer_par_nfc()`

**Files:**
- Modify: `laboutik/views.py:4794-5090` (fonction `_payer_par_nfc`)

- [ ] **Step 1: Lire la fonction actuelle**

Lire `laboutik/views.py` lignes 4855-4870 — le bloc qui cherche `asset_tlf` par categorie.

- [ ] **Step 2: Remplacer le lookup Asset par categorie**

Dans `_payer_par_nfc()`, supprimer le bloc lignes 4855-4869 :

```python
        # 3. Trouver l'asset TLF actif du tenant
        # 3. Find the tenant's active TLF asset
        asset_tlf = Asset.objects.filter(
            tenant_origin=connection.tenant,
            category=Asset.TLF,
            active=True,
        ).first()

        if asset_tlf is None:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Monnaie locale non configurée"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur)

        wallet_lieu = asset_tlf.wallet_origin
```

Le remplacer par une extraction de l'Asset depuis les articles du panier. Les ventes et adhesions debitent en TLF — il faut donc trouver l'Asset TLF depuis les articles de vente ou adhesion. Pour les recharges gratuites, l'Asset est sur chaque article.

```python
        # 3. Trouver l'asset du tenant depuis les articles du panier
        # Les ventes et adhesions sont en TLF — on le prend depuis le premier
        # article qui a un Asset lie, ou depuis un Product de recharge.
        # / 3. Find the tenant's asset from cart articles.
        # Sales and memberships use TLF — get it from the first article
        # with a linked Asset, or from a top-up Product.
        asset_tlf = None
        for article in articles_panier:
            produit = article["product"]
            if produit.asset is not None:
                asset_tlf = produit.asset
                break

        # Si aucun article n'a d'Asset (ex: panier VT pur sans recharges),
        # chercher l'Asset TLF du tenant pour les debits.
        # / If no article has an Asset (e.g. pure VT cart without top-ups),
        # look up the tenant's TLF Asset for debits.
        if asset_tlf is None:
            asset_tlf = Asset.objects.filter(
                tenant_origin=connection.tenant,
                category=Asset.TLF,
                active=True,
            ).first()

        if asset_tlf is None:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Monnaie locale non configurée"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur)

        wallet_lieu = asset_tlf.wallet_origin
```

- [ ] **Step 3: Lancer les tests de paiement cashless**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_paiement_cashless.py -v -x
```

Expected: tous les tests passent.

---

### Task 6 : Mise a jour `create_test_pos_data`

**Files:**
- Modify: `laboutik/management/commands/create_test_pos_data.py`

- [ ] **Step 1: Lire les sections a modifier**

Lire les lignes 294-338 (products recharge), 765-790 (M2M cashless), 971-972 (FedowAsset).

- [ ] **Step 2: Supprimer les dicts de Products de recharge**

Dans la liste `products_data` (lignes 294-338), supprimer les 5 dicts :
- "Recharge 10€" (lignes 294-301)
- "Recharge 20€" (lignes 304-310)
- "Cadeau 5€" (lignes 313-319)
- "Cadeau 10€" (lignes 322-328)
- "Temps 1h" (lignes 331-337)

- [ ] **Step 3: Ajouter la creation des Assets apres les categories, avant les produits**

Apres la creation des `CategorieProduct` (ligne ~113) et avant les `products_data` (ligne ~120), ajouter :

```python
            # --- Assets fedow_core (monnaie locale, cadeau, temps) ---
            # Le signal post_save cree automatiquement les Products de recharge
            # et les attache aux PV CASHLESS.
            # / fedow_core Assets (local currency, gift, time).
            # The post_save signal auto-creates top-up Products
            # and attaches them to CASHLESS POS.
            from fedow_core.models import Asset as FedowAsset
            from fedow_core.services import AssetService
            from fedow_connect.models import FedowConfig

            # Wallet du lieu : utiliser celui de FedowConfig si disponible,
            # sinon en creer un local (dev sans serveur Fedow).
            # / Venue wallet: use FedowConfig's if available,
            # otherwise create a local one (dev without Fedow server).
            fedow_config = FedowConfig.get_solo()
            if fedow_config.wallet:
                wallet_du_lieu = fedow_config.wallet
            else:
                wallet_du_lieu, _ = Wallet.objects.get_or_create(
                    origin=tenant_client,
                    defaults={"name": f"Wallet {tenant_client.name}"},
                )

            # Creer les 3 Assets si inexistants
            # / Create the 3 Assets if they don't exist
            for asset_def in [
                {"name": "Monnaie locale", "category": FedowAsset.TLF, "currency_code": "EUR"},
                {"name": "Cadeau", "category": FedowAsset.TNF, "currency_code": "CAD"},
                {"name": "Temps", "category": FedowAsset.TIM, "currency_code": "TMP"},
            ]:
                asset_existant = FedowAsset.objects.filter(
                    tenant_origin=tenant_client,
                    category=asset_def["category"],
                    active=True,
                ).first()
                if asset_existant is None:
                    AssetService.creer_asset(
                        tenant=tenant_client,
                        name=asset_def["name"],
                        category=asset_def["category"],
                        currency_code=asset_def["currency_code"],
                        wallet_origin=wallet_du_lieu,
                    )
                    self.stdout.write(f"  Asset cree : {asset_def['name']} ({asset_def['category']})")
                else:
                    self.stdout.write(f"  Asset existant : {asset_existant.name} ({asset_existant.category})")
```

Note : il faut aussi ajouter l'import `Wallet` en haut du fichier :

```python
from AuthBillet.models import Wallet
```

- [ ] **Step 4: Adapter le bloc M2M du PV Cashless**

Le signal a deja attache les Products de recharge aux PV CASHLESS. Supprimer ou adapter le bloc `pdv_cashless.products.set(cashless_products)` (ligne 789) pour ne plus forcer un `.set()` qui ecraserait les produits ajoutes par le signal :

```python
            # Cashless : les produits de recharge sont auto-ajoutes par le signal Asset.
            # On ne fait PAS de .set() ici pour ne pas ecraser les produits du signal.
            # / Cashless: top-up products are auto-added by the Asset signal.
            # We do NOT .set() here to avoid overwriting signal products.
            pdv_cashless.categories.set([categorie_cashless])
```

- [ ] **Step 5: Adapter la reference FedowAsset dans les lignes de demo**

Le bloc ligne 971-972 cherche `FedowAsset.objects.filter(category=FedowAsset.TLF, active=True).first()`. Ce lookup fonctionne toujours car les Assets sont maintenant crees juste avant. Pas de modification necessaire.

- [ ] **Step 6: Lancer la commande pour verifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py create_test_pos_data
```

Expected: la commande s'execute sans erreur, les Assets sont crees, les Products de recharge apparaissent automatiquement.

- [ ] **Step 7: Lancer la suite de tests complete**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q --tb=short
```

Expected: tous les tests passent. Les tests qui referencent "Recharge 10€" ou "Cadeau 5€" par nom exact devront peut-etre etre adaptes (voir Task 7).

---

### Task 7 : Adapter les tests existants

**Files:**
- Modify: `tests/pytest/test_paiement_cashless.py` (fixture `asset_tlf`)
- Modify: `tests/pytest/test_retour_carte_recharges.py` (si references par nom)
- Modify: `tests/pytest/test_paiement_especes_cb.py` (si references par nom)

- [ ] **Step 1: Identifier les tests qui cassent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q --tb=line 2>&1 | head -60
```

Identifier les tests en echec et les raisons (nom de produit change, fixture manquante, etc.).

- [ ] **Step 2: Adapter chaque test casse**

Pour chaque test en echec, adapter :
- Les references par nom exact ("Recharge 10€") → utiliser `Product.objects.filter(methode_caisse=Product.RECHARGE_EUROS).first()` a la place
- Les fixtures qui creent des Assets TLF manuellement → verifier qu'elles n'entrent pas en conflit avec les Assets crees par `create_test_pos_data` via le signal
- La fixture `asset_tlf` dans `test_paiement_cashless.py` : le signal va creer un Product de recharge pour cet Asset — s'assurer que ca ne cree pas de doublon ou de conflit

- [ ] **Step 3: Lancer la suite de tests complete**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

Expected: tous les tests passent.

- [ ] **Step 4: Lancer les tests E2E POS (si serveur disponible)**

```bash
docker exec lespass_django poetry run pytest tests/e2e/test_pos_*.py -v -s
```

Expected: les tests E2E passent (les boutons de recharge sont generes par le signal).

---

### Task 8 : Verification finale et ruff

- [ ] **Step 1: Ruff check sur tous les fichiers modifies**

```bash
docker exec lespass_django poetry run ruff check --fix \
    /DjangoFiles/BaseBillet/models.py \
    /DjangoFiles/fedow_core/signals.py \
    /DjangoFiles/fedow_core/apps.py \
    /DjangoFiles/laboutik/views.py \
    /DjangoFiles/laboutik/management/commands/create_test_pos_data.py \
    /DjangoFiles/tests/pytest/test_asset_recharge_signal.py
```

- [ ] **Step 2: Ruff format**

```bash
docker exec lespass_django poetry run ruff format \
    /DjangoFiles/BaseBillet/models.py \
    /DjangoFiles/fedow_core/signals.py \
    /DjangoFiles/fedow_core/apps.py \
    /DjangoFiles/laboutik/views.py \
    /DjangoFiles/laboutik/management/commands/create_test_pos_data.py \
    /DjangoFiles/tests/pytest/test_asset_recharge_signal.py
```

- [ ] **Step 3: Suite de tests complete**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
```

Expected: tous les tests passent, 0 erreur ruff.
