# Inventaire et Stock POS — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un système d'inventaire optionnel par produit POS avec journal de mouvements, alertes visuelles, actions rapides caissier, et endpoint capteur débit mètre.

**Architecture:** Nouvelle app Django `inventaire` (TENANT_APP). Modèle `Stock` (OneToOne → Product) avec unités (pièces/cl/g). Modèle `MouvementStock` (journal immutable). Décrémentation atomique via `F()` dans le flux de paiement existant. Admin Unfold + actions HTMX dans le POS.

**Tech Stack:** Django 4.2, django-tenants, django-unfold, DRF ViewSets, HTMX, PostgreSQL `F()` expressions.

**Spec de référence :** `TECH DOC/Laboutik sessions/Session 03 - Inventaire et stock/SPEC_INVENTAIRE.md`

---

## Structure des fichiers

### Fichiers à créer

| Fichier | Responsabilité |
|---------|---------------|
| `inventaire/__init__.py` | App init |
| `inventaire/apps.py` | AppConfig Django |
| `inventaire/models.py` | Stock, MouvementStock, choices, exceptions |
| `inventaire/services.py` | StockService (décrémentation, mouvements, résumé clôture) |
| `inventaire/serializers.py` | MouvementRapideSerializer, DebitMetreSerializer |
| `inventaire/views.py` | StockViewSet, DebitMetreViewSet |
| `inventaire/urls.py` | Routes DRF |
| `inventaire/templates/inventaire/partial/modale_mouvement.html` | Modale HTMX pour actions rapides POS |
| `Administration/templates/admin/inventaire/ajustement_form.html` | Formulaire ajustement admin |
| `tests/pytest/test_inventaire.py` | Tests modèles, services, vues |

### Fichiers à modifier

| Fichier | Changement |
|---------|-----------|
| `BaseBillet/models.py:540-560` | Ajouter `module_inventaire` sur Configuration |
| `BaseBillet/models.py:1347` | Ajouter `contenance` sur Price |
| `TiBillet/settings.py:172-188` | Ajouter `'inventaire'` dans TENANT_APPS |
| `Administration/admin/dashboard.py:404-433` | Ajouter `module_inventaire` dans MODULE_FIELDS |
| `Administration/admin/dashboard.py:20-120` | Ajouter section Inventaire dans sidebar |
| `Administration/admin/products.py:1062-1119` | Ajouter StockInline sur POSProductAdmin |
| `laboutik/views.py:2684-2800` | Brancher décrémentation stock dans `_creer_lignes_articles()` |
| `laboutik/reports.py:35-200` | Ajouter section résumé stock au rapport de clôture |

---

## Session 23 — Modèles + services fondation

### Task 1 : App inventaire + modèle Stock

**Files:**
- Create: `inventaire/__init__.py`
- Create: `inventaire/apps.py`
- Create: `inventaire/models.py`
- Modify: `TiBillet/settings.py:172-188`
- Test: `tests/pytest/test_inventaire.py`

- [ ] **Step 1: Créer l'app inventaire**

```python
# inventaire/__init__.py
# (fichier vide)
```

```python
# inventaire/apps.py
"""
Configuration de l'app inventaire.
Gestion de stock optionnelle pour les produits POS.
/ Inventory app configuration. Optional stock management for POS products.

LOCALISATION : inventaire/apps.py
"""
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class InventaireConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'inventaire'
    verbose_name = _("Inventaire / Inventory")
```

- [ ] **Step 2: Créer le modèle Stock**

```python
# inventaire/models.py
"""
Modèles de gestion de stock pour les produits POS.
/ Stock management models for POS products.

LOCALISATION : inventaire/models.py

DEPENDENCIES :
- BaseBillet.Product (OneToOne)
- BaseBillet.LigneArticle (FK sur MouvementStock)
- laboutik.ClotureCaisse (FK sur MouvementStock)
- AuthBillet.TibilletUser (FK sur MouvementStock)
"""
import uuid as uuid_module

from django.db import models
from django.utils.translation import gettext_lazy as _


# --- Choices ---
# / Stock unit choices

class UniteStock(models.TextChoices):
    """
    Unité de mesure du stock.
    Toujours la plus petite unité pour éviter les décimales.
    / Stock measurement unit. Always the smallest unit to avoid decimals.
    """
    UNITE = 'UN', _("Pièces / Units")
    CENTILITRE = 'CL', _("Centilitres")
    GRAMME = 'GR', _("Grammes / Grams")


class TypeMouvement(models.TextChoices):
    """
    Type de mouvement de stock.
    / Stock movement type.
    """
    VENTE = 'VE', _("Vente / Sale")
    RECEPTION = 'RE', _("Réception / Reception")
    AJUSTEMENT = 'AJ', _("Ajustement inventaire / Inventory adjustment")
    OFFERT = 'OF', _("Offert / Complimentary")
    PERTE = 'PE', _("Perte / casse / Loss / breakage")
    DEBIT_METRE = 'DM', _("Débit mètre / Flow meter")


# --- Exceptions ---

class StockInsuffisant(Exception):
    """
    Levée quand le stock est insuffisant et que la vente est bloquante.
    / Raised when stock is insufficient and sale is blocking.
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
    Stock d'un produit POS.
    Lié en OneToOne à Product. Pas de Stock = pas de gestion de stock.
    / POS product stock. OneToOne to Product. No Stock = no stock management.

    LOCALISATION : inventaire/models.py

    L'unité de base (centilitres, grammes, ou pièces) est toujours
    la plus petite unité pour éviter les décimales.
    La quantité peut être négative si autoriser_vente_hors_stock=True.
    """
    uuid = models.UUIDField(
        primary_key=True,
        default=uuid_module.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    product = models.OneToOneField(
        'BaseBillet.Product',
        on_delete=models.CASCADE,
        related_name='stock_inventaire',
        verbose_name=_("Produit / Product"),
        help_text=_("Le produit POS lié à ce stock. / The POS product linked to this stock."),
    )

    quantite = models.IntegerField(
        default=0,
        verbose_name=_("Quantité en stock / Stock quantity"),
        help_text=_("Stock actuel en unité de base. Peut être négatif. / Current stock in base unit. Can be negative."),
    )

    unite = models.CharField(
        max_length=2,
        choices=UniteStock.choices,
        default=UniteStock.UNITE,
        verbose_name=_("Unité / Unit"),
        help_text=_("UN=pièces, CL=centilitres, GR=grammes. / UN=pieces, CL=centiliters, GR=grams."),
    )

    seuil_alerte = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Seuil d'alerte / Alert threshold"),
        help_text=_("Alerte visuelle POS quand le stock passe sous ce seuil. Vide=pas d'alerte. / Visual POS alert when stock falls below. Empty=no alert."),
    )

    autoriser_vente_hors_stock = models.BooleanField(
        default=True,
        verbose_name=_("Autoriser vente hors stock / Allow out-of-stock sale"),
        help_text=_("Si décoché, le produit est bloqué à stock ≤ 0. / If unchecked, product is blocked at stock ≤ 0."),
    )

    class Meta:
        verbose_name = _("Stock")
        verbose_name_plural = _("Stocks")

    def __str__(self):
        return f"{self.product.name} — {self.quantite} {self.get_unite_display()}"

    def est_en_alerte(self):
        """
        Vérifie si le stock est sous le seuil d'alerte.
        / Checks if stock is below alert threshold.
        """
        if self.seuil_alerte is None:
            return False
        return self.quantite <= self.seuil_alerte and self.quantite > 0

    def est_en_rupture(self):
        """
        Vérifie si le stock est à zéro ou négatif.
        / Checks if stock is at zero or negative.
        """
        return self.quantite <= 0


class MouvementStock(models.Model):
    """
    Journal de mouvement de stock. Immutable (lecture seule dans l'admin).
    Chaque entrée/sortie de stock crée un mouvement.
    / Stock movement log. Immutable (read-only in admin).

    LOCALISATION : inventaire/models.py

    Le champ quantite_avant permet de reconstruire l'historique
    sans agrégation (audit trail complet).
    """
    uuid = models.UUIDField(
        primary_key=True,
        default=uuid_module.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    stock = models.ForeignKey(
        Stock,
        on_delete=models.CASCADE,
        related_name='mouvements',
        verbose_name=_("Stock"),
    )

    type_mouvement = models.CharField(
        max_length=2,
        choices=TypeMouvement.choices,
        verbose_name=_("Type de mouvement / Movement type"),
    )

    quantite = models.IntegerField(
        verbose_name=_("Quantité / Quantity"),
        help_text=_("Delta signé : positif=entrée, négatif=sortie. / Signed delta: positive=in, negative=out."),
    )

    quantite_avant = models.IntegerField(
        verbose_name=_("Stock avant / Stock before"),
        help_text=_("Snapshot du stock avant ce mouvement. / Stock snapshot before this movement."),
    )

    motif = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name=_("Motif / Reason"),
        help_text=_("Texte libre : raison de la casse, ID capteur, etc. / Free text: breakage reason, sensor ID, etc."),
    )

    ligne_article = models.ForeignKey(
        'BaseBillet.LigneArticle',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mouvements_stock',
        verbose_name=_("Ligne article / Sale line"),
        help_text=_("Lien vers la vente POS (type VENTE uniquement). / Link to POS sale (VENTE type only)."),
    )

    cloture = models.ForeignKey(
        'laboutik.ClotureCaisse',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mouvements_stock',
        verbose_name=_("Clôture / Closure"),
    )

    cree_par = models.ForeignKey(
        'AuthBillet.TibilletUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mouvements_stock_crees',
        verbose_name=_("Créé par / Created by"),
        help_text=_("Null = système (vente auto, capteur). / Null = system (auto sale, sensor)."),
    )

    cree_le = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Créé le / Created at"),
    )

    class Meta:
        verbose_name = _("Mouvement de stock / Stock movement")
        verbose_name_plural = _("Mouvements de stock / Stock movements")
        ordering = ['-cree_le']
        indexes = [
            models.Index(fields=['-cree_le'], name='idx_mvt_stock_cree_le'),
            models.Index(fields=['type_mouvement'], name='idx_mvt_stock_type'),
        ]

    def __str__(self):
        signe = "+" if self.quantite > 0 else ""
        return (
            f"{self.get_type_mouvement_display()} "
            f"{signe}{self.quantite} {self.stock.get_unite_display()} "
            f"— {self.stock.product.name}"
        )
```

- [ ] **Step 3: Ajouter inventaire dans TENANT_APPS**

Dans `TiBillet/settings.py`, ajouter `'inventaire'` dans TENANT_APPS après `'laboutik'` (ligne ~188) :

```python
# Ajouter après la ligne 'laboutik',
    'inventaire',
```

- [ ] **Step 4: Créer et appliquer la migration**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations inventaire
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
```

- [ ] **Step 5: Vérifier manage.py check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: `System check identified no issues.`

- [ ] **Step 6: Écrire les tests du modèle Stock**

```python
# tests/pytest/test_inventaire.py
"""
Tests pour l'app inventaire : modèles, services, vues.
/ Tests for inventory app: models, services, views.

LOCALISATION : tests/pytest/test_inventaire.py

DEPENDENCIES :
- Requiert un tenant actif (FastTenantTestCase ou tenant_context)
- Requiert des Product avec methode_caisse (POS products)
"""
import uuid

import pytest
from django.db import connection
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.utils import tenant_context

from BaseBillet.models import Product, Price, Tva
from Customers.models import Client
from inventaire.models import (
    Stock,
    MouvementStock,
    UniteStock,
    TypeMouvement,
    StockInsuffisant,
)


class TestStockModel(FastTenantTestCase):
    """
    Tests unitaires pour le modèle Stock.
    / Unit tests for the Stock model.
    """

    @classmethod
    def get_test_schema_name(cls):
        return 'test_inventaire'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-inventaire.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.categorie = Client.SALLE_SPECTACLE
        tenant.save()

    def setUp(self):
        # Passer dans le schema du tenant de test
        # / Switch to test tenant schema
        connection.set_tenant(self.tenant)

        # Créer un produit POS de test
        # / Create a test POS product
        self.tva_20, _ = Tva.objects.get_or_create(name="20%", rate=20)
        self.produit_biere = Product.objects.create(
            name="Bière Pression Test",
            categorie_article=Product.NONE,
            methode_caisse='VT',
            tva=self.tva_20,
        )
        self.prix_pinte = Price.objects.create(
            product=self.produit_biere,
            name="Pinte",
            prix=5.00,
            contenance=50,  # 50 cl
        )
        self.prix_demi = Price.objects.create(
            product=self.produit_biere,
            name="Demi",
            prix=3.00,
            contenance=25,  # 25 cl
        )

    def test_creation_stock_basique(self):
        """
        Un Stock lié à un produit est créé avec les valeurs par défaut.
        / A Stock linked to a product is created with default values.
        """
        stock = Stock.objects.create(
            product=self.produit_biere,
            quantite=5000,  # 50 litres en centilitres
            unite=UniteStock.CENTILITRE,
            seuil_alerte=1000,  # 10 litres
        )
        assert stock.quantite == 5000
        assert stock.unite == UniteStock.CENTILITRE
        assert stock.seuil_alerte == 1000
        assert stock.autoriser_vente_hors_stock is True
        assert str(stock) == "Bière Pression Test — 5000 Centilitres"

    def test_stock_est_en_alerte(self):
        """
        est_en_alerte() retourne True quand quantite <= seuil et > 0.
        / est_en_alerte() returns True when quantity <= threshold and > 0.
        """
        stock = Stock.objects.create(
            product=self.produit_biere,
            quantite=800,
            unite=UniteStock.CENTILITRE,
            seuil_alerte=1000,
        )
        assert stock.est_en_alerte() is True

    def test_stock_pas_en_alerte_si_pas_de_seuil(self):
        """
        est_en_alerte() retourne False si seuil_alerte est None.
        / est_en_alerte() returns False if seuil_alerte is None.
        """
        stock = Stock.objects.create(
            product=self.produit_biere,
            quantite=100,
            unite=UniteStock.CENTILITRE,
            seuil_alerte=None,
        )
        assert stock.est_en_alerte() is False

    def test_stock_est_en_rupture(self):
        """
        est_en_rupture() retourne True quand quantite <= 0.
        / est_en_rupture() returns True when quantity <= 0.
        """
        stock = Stock.objects.create(
            product=self.produit_biere,
            quantite=0,
            unite=UniteStock.CENTILITRE,
        )
        assert stock.est_en_rupture() is True

    def test_stock_negatif_autorise(self):
        """
        La quantité peut être négative (pas de CheckConstraint).
        / Quantity can be negative (no CheckConstraint).
        """
        stock = Stock.objects.create(
            product=self.produit_biere,
            quantite=-200,
            unite=UniteStock.CENTILITRE,
        )
        assert stock.quantite == -200
        assert stock.est_en_rupture() is True

    def test_stock_unite_grammes(self):
        """
        Le stock peut être en grammes pour les produits pesés.
        / Stock can be in grams for weighed products.
        """
        produit_gateau = Product.objects.create(
            name="Gâteau Test",
            methode_caisse='VT',
            tva=self.tva_20,
        )
        stock = Stock.objects.create(
            product=produit_gateau,
            quantite=2000,  # 2 kg
            unite=UniteStock.GRAMME,
        )
        assert stock.unite == UniteStock.GRAMME
        assert stock.quantite == 2000


class TestMouvementStockModel(FastTenantTestCase):
    """
    Tests unitaires pour le modèle MouvementStock.
    / Unit tests for the MouvementStock model.
    """

    @classmethod
    def get_test_schema_name(cls):
        return 'test_inventaire'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-inventaire.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.categorie = Client.SALLE_SPECTACLE
        tenant.save()

    def setUp(self):
        connection.set_tenant(self.tenant)

        self.tva_20, _ = Tva.objects.get_or_create(name="20%", rate=20)
        self.produit = Product.objects.create(
            name="Bouteille Eau Test",
            methode_caisse='VT',
            tva=self.tva_20,
        )
        self.stock = Stock.objects.create(
            product=self.produit,
            quantite=50,
            unite=UniteStock.UNITE,
        )

    def test_creation_mouvement_vente(self):
        """
        Un mouvement de vente décrémente le stock.
        / A sale movement decrements the stock.
        """
        mouvement = MouvementStock.objects.create(
            stock=self.stock,
            type_mouvement=TypeMouvement.VENTE,
            quantite=-2,
            quantite_avant=50,
        )
        assert mouvement.quantite == -2
        assert mouvement.quantite_avant == 50
        assert mouvement.type_mouvement == TypeMouvement.VENTE
        assert mouvement.cree_par is None  # Système

    def test_creation_mouvement_reception(self):
        """
        Un mouvement de réception incrémente le stock.
        / A reception movement increments the stock.
        """
        mouvement = MouvementStock.objects.create(
            stock=self.stock,
            type_mouvement=TypeMouvement.RECEPTION,
            quantite=24,
            quantite_avant=50,
            motif="Livraison fournisseur",
        )
        assert mouvement.quantite == 24
        assert mouvement.motif == "Livraison fournisseur"

    def test_mouvement_ordering_par_date(self):
        """
        Les mouvements sont ordonnés par date décroissante.
        / Movements are ordered by date descending.
        """
        mouvement_1 = MouvementStock.objects.create(
            stock=self.stock,
            type_mouvement=TypeMouvement.RECEPTION,
            quantite=10,
            quantite_avant=50,
        )
        mouvement_2 = MouvementStock.objects.create(
            stock=self.stock,
            type_mouvement=TypeMouvement.VENTE,
            quantite=-1,
            quantite_avant=60,
        )
        mouvements = list(MouvementStock.objects.all())
        assert mouvements[0].pk == mouvement_2.pk
        assert mouvements[1].pk == mouvement_1.pk

    def test_str_mouvement(self):
        """
        __str__ affiche le type, le delta signé, et le produit.
        / __str__ shows type, signed delta, and product.
        """
        mouvement = MouvementStock.objects.create(
            stock=self.stock,
            type_mouvement=TypeMouvement.PERTE,
            quantite=-3,
            quantite_avant=50,
            motif="Casse",
        )
        chaine = str(mouvement)
        assert "Perte" in chaine or "Loss" in chaine
        assert "-3" in chaine
        assert "Bouteille Eau Test" in chaine
```

- [ ] **Step 7: Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_inventaire.py -v
```

Expected: tous les tests passent.

- [ ] **Step 8: Ruff check + format**

```bash
docker exec lespass_django poetry run ruff check --fix inventaire/
docker exec lespass_django poetry run ruff format inventaire/
docker exec lespass_django poetry run ruff check --fix tests/pytest/test_inventaire.py
docker exec lespass_django poetry run ruff format tests/pytest/test_inventaire.py
```

---

### Task 2 : Champ contenance sur Price + module_inventaire sur Configuration

**Files:**
- Modify: `BaseBillet/models.py:540-560` (Configuration)
- Modify: `BaseBillet/models.py:1347` (Price)
- Test: `tests/pytest/test_inventaire.py` (ajouter tests)

- [ ] **Step 1: Ajouter module_inventaire sur Configuration**

Dans `BaseBillet/models.py`, après la ligne `module_caisse` (~ligne 556), ajouter :

```python
    module_inventaire = models.BooleanField(
        default=False,
        verbose_name=_("Module inventaire / Inventory module"),
        help_text=_("Active la gestion de stock pour les produits POS. / Enables stock management for POS products."),
    )
```

- [ ] **Step 2: Ajouter contenance sur Price**

Dans `BaseBillet/models.py`, après le champ `stock` de Price (~ligne 1347), ajouter :

```python
    contenance = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Contenance / Serving size"),
        help_text=_(
            "Quantité consommée par unité vendue, dans l'unité du stock. "
            "Ex : pinte=50 (cl), demi=25 (cl), portion=150 (g). "
            "Vide = 1 unité par défaut. "
            "/ Quantity consumed per unit sold, in the stock's unit. "
            "Empty = 1 unit by default."
        ),
    )
```

- [ ] **Step 3: Créer et appliquer les migrations**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations BaseBillet
docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
```

- [ ] **Step 4: Vérifier manage.py check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 issues.

- [ ] **Step 5: Ajouter tests pour contenance**

Ajouter dans `tests/pytest/test_inventaire.py`, dans la classe `TestStockModel` :

```python
    def test_contenance_sur_price(self):
        """
        Le champ contenance est disponible sur Price.
        / The contenance field is available on Price.
        """
        assert self.prix_pinte.contenance == 50
        assert self.prix_demi.contenance == 25

    def test_contenance_null_par_defaut(self):
        """
        contenance=None signifie 1 unité par défaut.
        / contenance=None means 1 unit by default.
        """
        prix_sans_contenance = Price.objects.create(
            product=self.produit_biere,
            name="Verre",
            prix=2.00,
            contenance=None,
        )
        assert prix_sans_contenance.contenance is None
```

- [ ] **Step 6: Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_inventaire.py -v
```

Expected: tous passent.

---

### Task 3 : Service de décrémentation atomique

**Files:**
- Create: `inventaire/services.py`
- Test: `tests/pytest/test_inventaire.py` (ajouter tests)

- [ ] **Step 1: Écrire les tests du service de décrémentation**

Ajouter dans `tests/pytest/test_inventaire.py` :

```python
from django.db.models import F

from inventaire.services import StockService


class TestStockService(FastTenantTestCase):
    """
    Tests pour StockService : décrémentation atomique.
    / Tests for StockService: atomic decrement.
    """

    @classmethod
    def get_test_schema_name(cls):
        return 'test_inventaire'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-inventaire.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.categorie = Client.SALLE_SPECTACLE
        tenant.save()

    def setUp(self):
        connection.set_tenant(self.tenant)

        self.tva_20, _ = Tva.objects.get_or_create(name="20%", rate=20)
        self.produit = Product.objects.create(
            name="Bière Pression Service",
            methode_caisse='VT',
            tva=self.tva_20,
        )
        self.prix_pinte = Price.objects.create(
            product=self.produit,
            name="Pinte",
            prix=5.00,
            contenance=50,
        )
        self.stock = Stock.objects.create(
            product=self.produit,
            quantite=3000,  # 30 litres
            unite=UniteStock.CENTILITRE,
            seuil_alerte=500,
        )

    def test_decrementer_stock_vente(self):
        """
        La vente de 2 pintes décrémente de 100 cl.
        / Selling 2 pints decrements by 100 cl.
        """
        StockService.decrementer_pour_vente(
            stock=self.stock,
            contenance=50,
            qty=2,
            ligne_article=None,
        )
        self.stock.refresh_from_db()
        assert self.stock.quantite == 2900

        # Vérifie le mouvement créé
        # / Verify the created movement
        mouvement = MouvementStock.objects.first()
        assert mouvement.type_mouvement == TypeMouvement.VENTE
        assert mouvement.quantite == -100
        assert mouvement.quantite_avant == 3000

    def test_decrementer_stock_contenance_null(self):
        """
        contenance=None utilise 1 comme valeur par défaut.
        / contenance=None uses 1 as default value.
        """
        produit_bouteille = Product.objects.create(
            name="Bouteille Service",
            methode_caisse='VT',
            tva=self.tva_20,
        )
        stock_bouteille = Stock.objects.create(
            product=produit_bouteille,
            quantite=24,
            unite=UniteStock.UNITE,
        )
        StockService.decrementer_pour_vente(
            stock=stock_bouteille,
            contenance=None,
            qty=3,
            ligne_article=None,
        )
        stock_bouteille.refresh_from_db()
        assert stock_bouteille.quantite == 21

    def test_decrementer_stock_non_bloquant_passe_en_negatif(self):
        """
        Avec autoriser_vente_hors_stock=True, le stock peut passer en négatif.
        / With autoriser_vente_hors_stock=True, stock can go negative.
        """
        self.stock.quantite = 30
        self.stock.save()

        StockService.decrementer_pour_vente(
            stock=self.stock,
            contenance=50,
            qty=1,  # 50 cl > 30 cl dispo
            ligne_article=None,
        )
        self.stock.refresh_from_db()
        assert self.stock.quantite == -20

    def test_decrementer_stock_bloquant_leve_exception(self):
        """
        Avec autoriser_vente_hors_stock=False, lève StockInsuffisant.
        / With autoriser_vente_hors_stock=False, raises StockInsuffisant.
        """
        self.stock.quantite = 30
        self.stock.autoriser_vente_hors_stock = False
        self.stock.save()

        with pytest.raises(StockInsuffisant):
            StockService.decrementer_pour_vente(
                stock=self.stock,
                contenance=50,
                qty=1,
                ligne_article=None,
            )
        # Le stock n'a pas changé
        # / Stock hasn't changed
        self.stock.refresh_from_db()
        assert self.stock.quantite == 30

    def test_creer_mouvement_reception(self):
        """
        Ajouter du stock via réception.
        / Add stock via reception.
        """
        StockService.creer_mouvement(
            stock=self.stock,
            type_mouvement=TypeMouvement.RECEPTION,
            quantite=3000,  # 30 litres
            motif="Fût de 30L",
            utilisateur=None,
        )
        self.stock.refresh_from_db()
        assert self.stock.quantite == 6000

        mouvement = MouvementStock.objects.first()
        assert mouvement.type_mouvement == TypeMouvement.RECEPTION
        assert mouvement.quantite == 3000
        assert mouvement.quantite_avant == 3000
        assert mouvement.motif == "Fût de 30L"

    def test_creer_mouvement_perte(self):
        """
        Retirer du stock via perte/casse.
        / Remove stock via loss/breakage.
        """
        StockService.creer_mouvement(
            stock=self.stock,
            type_mouvement=TypeMouvement.PERTE,
            quantite=200,  # 2 litres renversés
            motif="Fût tombé",
            utilisateur=None,
        )
        self.stock.refresh_from_db()
        assert self.stock.quantite == 2800

        mouvement = MouvementStock.objects.first()
        assert mouvement.quantite == -200  # Signe négatif automatique

    def test_ajustement_inventaire(self):
        """
        Ajustement : l'utilisateur donne le stock réel, le delta est calculé.
        / Adjustment: user gives real stock, delta is computed.
        """
        StockService.ajuster_inventaire(
            stock=self.stock,
            stock_reel=2500,
            motif="Inventaire physique",
            utilisateur=None,
        )
        self.stock.refresh_from_db()
        assert self.stock.quantite == 2500

        mouvement = MouvementStock.objects.first()
        assert mouvement.type_mouvement == TypeMouvement.AJUSTEMENT
        assert mouvement.quantite == -500  # 2500 - 3000
        assert mouvement.quantite_avant == 3000
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_inventaire.py::TestStockService -v
```

Expected: FAIL avec `ImportError: cannot import name 'StockService'`

- [ ] **Step 3: Implémenter StockService**

```python
# inventaire/services.py
"""
Service de gestion de stock : décrémentation atomique, mouvements, résumé clôture.
/ Stock management service: atomic decrement, movements, closure summary.

LOCALISATION : inventaire/services.py

FLUX de décrémentation à la vente :
1. Récupère le stock du produit (select_related dans le flux POS)
2. Calcule le delta = qty × contenance
3. Update atomique via F() (pas de verrou bloquant)
4. Crée le MouvementStock avec quantite_avant

DEPENDENCIES :
- inventaire.models (Stock, MouvementStock, TypeMouvement, StockInsuffisant)
"""
import logging

from django.db.models import F, Sum

from inventaire.models import (
    MouvementStock,
    Stock,
    StockInsuffisant,
    TypeMouvement,
)

logger = logging.getLogger(__name__)


class StockService:
    """
    Service statique pour les opérations de stock.
    Toutes les méthodes sont des @staticmethod — pas d'état interne.
    / Static service for stock operations. All methods are @staticmethod.
    """

    @staticmethod
    def decrementer_pour_vente(stock, contenance, qty, ligne_article=None):
        """
        Décrémente le stock après une vente POS.
        Utilise F() pour un update atomique sans verrou.
        / Decrements stock after a POS sale. Uses F() for lockless atomic update.

        :param stock: instance Stock (doit être frais, pas stale)
        :param contenance: int ou None. Quantité par unité vendue. None=1.
        :param qty: int. Nombre d'unités vendues.
        :param ligne_article: LigneArticle ou None. Lien vers la vente.
        :raises StockInsuffisant: si stock bloquant et insuffisant.
        """
        # Calcul du delta en unité de base
        # / Compute delta in base unit
        contenance_effective = contenance or 1
        delta = qty * contenance_effective

        # Snapshot du stock avant pour le mouvement
        # / Stock snapshot before for the movement
        stock_avant = stock.quantite

        if stock.autoriser_vente_hors_stock:
            # Non bloquant : décrémente même en négatif
            # / Non-blocking: decrements even if negative
            Stock.objects.filter(pk=stock.pk).update(
                quantite=F('quantite') - delta
            )
        else:
            # Bloquant : échoue si stock insuffisant
            # / Blocking: fails if insufficient stock
            lignes_mises_a_jour = Stock.objects.filter(
                pk=stock.pk,
                quantite__gte=delta,
            ).update(quantite=F('quantite') - delta)

            if not lignes_mises_a_jour:
                raise StockInsuffisant(stock.product, delta, stock.quantite)

        # Créer le mouvement de vente
        # / Create the sale movement
        MouvementStock.objects.create(
            stock=stock,
            type_mouvement=TypeMouvement.VENTE,
            quantite=-delta,
            quantite_avant=stock_avant,
            ligne_article=ligne_article,
            cree_par=None,  # Système
        )

        logger.info(
            f"Stock décrémenté : {stock.product.name} "
            f"-{delta} {stock.get_unite_display()} "
            f"(avant={stock_avant})"
        )

    @staticmethod
    def creer_mouvement(stock, type_mouvement, quantite, motif='', utilisateur=None):
        """
        Crée un mouvement de stock manuel (réception, perte, offert, débit mètre).
        Le signe du delta est déduit du type.
        / Creates a manual stock movement. Delta sign is inferred from type.

        :param stock: instance Stock
        :param type_mouvement: TypeMouvement choice
        :param quantite: int positif. La quantité concernée (toujours positive en entrée).
        :param motif: str optionnel. Raison du mouvement.
        :param utilisateur: TibilletUser ou None.
        """
        # Déterminer le signe selon le type
        # / Determine sign based on type
        types_negatifs = [
            TypeMouvement.PERTE,
            TypeMouvement.OFFERT,
            TypeMouvement.DEBIT_METRE,
        ]
        if type_mouvement in types_negatifs:
            delta = -abs(quantite)
        else:
            delta = abs(quantite)

        stock_avant = stock.quantite

        # Update atomique
        # / Atomic update
        Stock.objects.filter(pk=stock.pk).update(
            quantite=F('quantite') + delta
        )

        MouvementStock.objects.create(
            stock=stock,
            type_mouvement=type_mouvement,
            quantite=delta,
            quantite_avant=stock_avant,
            motif=motif,
            cree_par=utilisateur,
        )

        logger.info(
            f"Mouvement stock {type_mouvement} : {stock.product.name} "
            f"{'+' if delta > 0 else ''}{delta} {stock.get_unite_display()} "
            f"motif='{motif}'"
        )

    @staticmethod
    def ajuster_inventaire(stock, stock_reel, motif='', utilisateur=None):
        """
        Ajustement inventaire : l'utilisateur donne le stock réel compté.
        Le système calcule le delta (réel - actuel).
        / Inventory adjustment: user gives real counted stock. System computes delta.

        :param stock: instance Stock
        :param stock_reel: int. Stock réel compté.
        :param motif: str optionnel.
        :param utilisateur: TibilletUser ou None.
        """
        stock_avant = stock.quantite
        delta = stock_reel - stock_avant

        # Mettre le stock directement à la valeur réelle
        # / Set stock directly to the real value
        Stock.objects.filter(pk=stock.pk).update(quantite=stock_reel)

        MouvementStock.objects.create(
            stock=stock,
            type_mouvement=TypeMouvement.AJUSTEMENT,
            quantite=delta,
            quantite_avant=stock_avant,
            motif=motif,
            cree_par=utilisateur,
        )

        logger.info(
            f"Ajustement inventaire : {stock.product.name} "
            f"{stock_avant} → {stock_reel} (delta={delta:+d})"
        )
```

- [ ] **Step 4: Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_inventaire.py -v
```

Expected: tous passent.

- [ ] **Step 5: Ruff check + format**

```bash
docker exec lespass_django poetry run ruff check --fix inventaire/
docker exec lespass_django poetry run ruff format inventaire/
```

---

### Task 4 : Branchement stock dans le flux de paiement POS

**Files:**
- Modify: `laboutik/views.py:2684-2800` (`_creer_lignes_articles`)
- Test: `tests/pytest/test_inventaire.py` (ajouter test intégration)

- [ ] **Step 1: Écrire le test d'intégration**

Ajouter dans `tests/pytest/test_inventaire.py` :

```python
from BaseBillet.models import ProductSold, PriceSold, LigneArticle, SaleOrigin, PaymentMethod


class TestIntegrationVentePOS(FastTenantTestCase):
    """
    Test d'intégration : la vente POS décrémente le stock.
    / Integration test: POS sale decrements stock.
    """

    @classmethod
    def get_test_schema_name(cls):
        return 'test_inventaire'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-inventaire.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.categorie = Client.SALLE_SPECTACLE
        tenant.save()

    def setUp(self):
        connection.set_tenant(self.tenant)

        self.tva_20, _ = Tva.objects.get_or_create(name="20%", rate=20)
        self.produit = Product.objects.create(
            name="Bière Intégration",
            methode_caisse='VT',
            tva=self.tva_20,
        )
        self.prix_pinte = Price.objects.create(
            product=self.produit,
            name="Pinte",
            prix=5.00,
            contenance=50,
        )
        self.stock = Stock.objects.create(
            product=self.produit,
            quantite=3000,
            unite=UniteStock.CENTILITRE,
        )

    def test_vente_avec_stock_decremente(self):
        """
        Quand _decrementer_stock_si_present est appelé après création
        d'une LigneArticle, le stock est décrémenté.
        / When _decrementer_stock_si_present is called after creating
        a LigneArticle, stock is decremented.
        """
        from inventaire.services import StockService

        # Simuler la partie pertinente du flux de paiement
        # / Simulate the relevant part of the payment flow
        product_sold = ProductSold.objects.create(
            product=self.produit,
            categorie_article=self.produit.categorie_article,
        )
        price_sold = PriceSold.objects.create(
            productsold=product_sold,
            price=self.prix_pinte,
            prix=self.prix_pinte.prix,
        )
        ligne = LigneArticle.objects.create(
            pricesold=price_sold,
            qty=2,
            amount=1000,
            vat=20,
            sale_origin=SaleOrigin.LABOUTIK,
            payment_method=PaymentMethod.ESPECE,
            status=LigneArticle.VALID,
        )

        # Appeler la décrémentation comme le fera le flux POS
        # / Call decrement like the POS flow will
        try:
            stock_du_produit = Stock.objects.get(product=self.produit)
            StockService.decrementer_pour_vente(
                stock=stock_du_produit,
                contenance=self.prix_pinte.contenance,
                qty=2,
                ligne_article=ligne,
            )
        except Stock.DoesNotExist:
            pass  # Pas de stock = pas de décrémentation

        self.stock.refresh_from_db()
        assert self.stock.quantite == 2900  # 3000 - (2 × 50)

        # Le mouvement a un lien vers la LigneArticle
        # / Movement links to the LigneArticle
        mouvement = MouvementStock.objects.first()
        assert mouvement.ligne_article == ligne

    def test_vente_sans_stock_ne_leve_pas_erreur(self):
        """
        Un produit sans Stock lié ne provoque pas d'erreur.
        / A product without linked Stock doesn't cause an error.
        """
        produit_sans_stock = Product.objects.create(
            name="Eau Sans Stock",
            methode_caisse='VT',
            tva=self.tva_20,
        )
        # Pas de Stock créé pour ce produit
        # Le try/except Stock.DoesNotExist dans le flux POS gère ce cas
        existe = Stock.objects.filter(product=produit_sans_stock).exists()
        assert existe is False
```

- [ ] **Step 2: Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_inventaire.py::TestIntegrationVentePOS -v
```

Expected: passent.

- [ ] **Step 3: Brancher la décrémentation dans `_creer_lignes_articles`**

Dans `laboutik/views.py`, dans la fonction `_creer_lignes_articles` (~ligne 2760, après la création de chaque LigneArticle et avant le chaînage HMAC), ajouter :

```python
        # --- Décrémentation stock inventaire ---
        # Si le produit a un Stock lié, on décrémente automatiquement.
        # / If the product has a linked Stock, auto-decrement.
        try:
            stock_du_produit = article_du_panier['product'].stock_inventaire
            from inventaire.services import StockService
            StockService.decrementer_pour_vente(
                stock=stock_du_produit,
                contenance=article_du_panier['price'].contenance,
                qty=article_du_panier['qty'],
                ligne_article=ligne_article,
            )
        except Stock.DoesNotExist:
            pass  # Pas de stock géré pour ce produit — comportement normal
```

Note : l'import est fait localement pour éviter une dépendance circulaire au chargement du module. Le `Stock.DoesNotExist` est levé par le `OneToOneField` quand il n'y a pas de stock lié. Ajouter `from inventaire.models import Stock` en haut du fichier avec les autres imports.

- [ ] **Step 4: Vérifier que les tests existants passent toujours**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_inventaire.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -q --tb=line 2>&1 | tail -20
```

Expected: 0 régression.

- [ ] **Step 5: Ruff check**

```bash
docker exec lespass_django poetry run ruff check --fix laboutik/views.py
```

---

## Session 24 — Admin Unfold + POS visuel

### Task 5 : MODULE_FIELDS + sidebar + dashboard

**Files:**
- Modify: `Administration/admin/dashboard.py:404-433` (MODULE_FIELDS)
- Modify: `Administration/admin/dashboard.py:20-120` (sidebar)

- [ ] **Step 1: Ajouter module_inventaire dans MODULE_FIELDS**

Dans `Administration/admin/dashboard.py`, après l'entrée `"module_caisse"` (~ligne 432), ajouter :

```python
    "module_inventaire": {
        "name": _("Inventory"),
        "description": _("Stock management for POS products: tracking, alerts, movements."),
        "testid": "dashboard-card-inventaire",
        "icon": "inventory_2",
    },
```

- [ ] **Step 2: Ajouter section Inventaire dans la sidebar**

Dans `get_sidebar_navigation()`, ajouter une section conditionnelle pour l'inventaire après la section "Caisse LaBoutik" :

```python
    # Section Inventaire — visible si module_inventaire actif
    # / Inventory section — visible if module_inventaire is active
    if config.module_inventaire:
        navigation_items.append({
            "title": _("Inventaire"),
            "separator": True,
            "collapsible": True,
            "items": [
                {
                    "title": _("Mouvements de stock"),
                    "icon": "inventory_2",
                    "link": reverse_lazy("staff_admin:inventaire_mouvementstock_changelist"),
                    "permission": "ApiBillet.permissions.TenantAdminPermissionWithRequest",
                },
            ],
        })
```

- [ ] **Step 3: Vérifier manage.py check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Step 4: Ruff check**

```bash
docker exec lespass_django poetry run ruff check --fix Administration/admin/dashboard.py
```

---

### Task 6 : MouvementStockAdmin (lecture seule)

**Files:**
- Create: `Administration/admin/inventaire.py`
- Modify: `Administration/admin_tenant.py` (ajouter import)

- [ ] **Step 1: Créer l'admin inventaire**

```python
# Administration/admin/inventaire.py
"""
Admin Unfold pour les modèles inventaire : Stock et MouvementStock.
/ Unfold admin for inventory models: Stock and MouvementStock.

LOCALISATION : Administration/admin/inventaire.py

Les helpers de formatage (conversion unités, affichage euros) sont définis
au niveau module, JAMAIS dans la classe ModelAdmin (piège Unfold wrapping).
"""
import logging

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from Administration.admin.site import staff_admin_site
from ApiBillet.permissions import TenantAdminPermissionWithRequest
from inventaire.models import MouvementStock, Stock, TypeMouvement

logger = logging.getLogger(__name__)


# --- Helpers module-level (pas dans la classe — piège Unfold wrapping) ---
# / Module-level helpers (not in the class — Unfold wrapping trap)

def _formater_quantite_lisible(quantite, unite):
    """
    Convertit une quantité en unité de base vers un affichage lisible.
    / Converts a base-unit quantity to human-readable display.
    """
    if unite == 'CL':
        if abs(quantite) >= 100:
            return f"{quantite / 100:.1f} L"
        return f"{quantite} cl"
    elif unite == 'GR':
        if abs(quantite) >= 1000:
            return f"{quantite / 1000:.1f} kg"
        return f"{quantite} g"
    return f"{quantite}"


# --- Labels pour les badges de type mouvement ---
# / Labels for movement type badges

LABELS_TYPE_MOUVEMENT = {
    TypeMouvement.VENTE: "danger",
    TypeMouvement.RECEPTION: "success",
    TypeMouvement.AJUSTEMENT: "warning",
    TypeMouvement.OFFERT: "info",
    TypeMouvement.PERTE: "danger",
    TypeMouvement.DEBIT_METRE: "primary",
}


# --- StockInline pour POSProductAdmin ---

class StockInline(TabularInline):
    """
    Inline OneToOne pour configurer le stock d'un produit POS.
    / OneToOne inline to configure POS product stock.
    """
    model = Stock
    extra = 0
    max_num = 1
    fields = ("quantite", "unite", "seuil_alerte", "autoriser_vente_hors_stock")

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_delete_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


# --- MouvementStockAdmin (lecture seule) ---

@admin.register(MouvementStock, site=staff_admin_site)
class MouvementStockAdmin(ModelAdmin):
    """
    Journal des mouvements de stock — lecture seule.
    Les mouvements sont créés par le système ou les actions POS.
    / Stock movement log — read-only. Created by system or POS actions.

    LOCALISATION : Administration/admin/inventaire.py
    """
    compressed_fields = True
    warn_unsaved_form = True

    list_display = [
        "cree_le",
        "display_produit",
        "display_type_mouvement",
        "display_quantite",
        "display_stock_apres",
        "motif",
        "display_auteur",
    ]
    list_filter = ["type_mouvement", "cree_le"]
    search_fields = ["stock__product__name", "motif"]
    ordering = ["-cree_le"]

    @display(description=_("Produit / Product"))
    def display_produit(self, obj):
        return obj.stock.product.name

    @display(
        description=_("Type"),
        label=LABELS_TYPE_MOUVEMENT,
    )
    def display_type_mouvement(self, obj):
        return obj.type_mouvement

    @display(description=_("Quantité / Quantity"))
    def display_quantite(self, obj):
        signe = "+" if obj.quantite > 0 else ""
        return f"{signe}{_formater_quantite_lisible(obj.quantite, obj.stock.unite)}"

    @display(description=_("Stock après / Stock after"))
    def display_stock_apres(self, obj):
        stock_apres = obj.quantite_avant + obj.quantite
        return _formater_quantite_lisible(stock_apres, obj.stock.unite)

    @display(description=_("Par / By"))
    def display_auteur(self, obj):
        if obj.cree_par:
            return str(obj.cree_par)
        return _("Système / System")

    # Lecture seule — pas de création, modification, ni suppression
    # / Read-only — no create, edit, or delete

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
```

- [ ] **Step 2: Ajouter l'import dans admin_tenant.py**

Dans `Administration/admin_tenant.py`, ajouter dans la section des imports (après les autres imports admin) :

```python
from Administration.admin import inventaire  # noqa: F401
```

- [ ] **Step 3: Ajouter StockInline sur POSProductAdmin**

Dans `Administration/admin/products.py`, ajouter l'import en haut du fichier :

```python
from Administration.admin.inventaire import StockInline
```

Puis dans la classe `POSProductAdmin` (~ligne 1067), modifier `inlines` :

```python
    inlines = [StockInline, PriceInline]
```

- [ ] **Step 4: Vérifier manage.py check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Step 5: Ruff check**

```bash
docker exec lespass_django poetry run ruff check --fix Administration/admin/inventaire.py
docker exec lespass_django poetry run ruff format Administration/admin/inventaire.py
```

---

### Task 7 : Affichage visuel stock dans le POS

**Files:**
- Modify: `laboutik/views.py` (enrichir les données articles avec l'état stock)
- Ce task est intentionnellement moins prescriptif car il dépend de la structure exacte des templates POS et du flux de données articles. L'implémenteur doit lire le code existant de `_construire_donnees_articles()` pour comprendre comment injecter les infos stock.

- [ ] **Step 1: Enrichir les données articles POS avec l'info stock**

Dans `laboutik/views.py`, dans la fonction `_construire_donnees_articles()`, enrichir chaque article avec les données de stock. L'idée :

```python
# Pour chaque article construit, ajouter l'état stock
# / For each built article, add stock state
try:
    stock_du_produit = product.stock_inventaire
    article['stock_quantite'] = stock_du_produit.quantite
    article['stock_unite'] = stock_du_produit.unite
    article['stock_seuil_alerte'] = stock_du_produit.seuil_alerte
    article['stock_en_alerte'] = stock_du_produit.est_en_alerte()
    article['stock_en_rupture'] = stock_du_produit.est_en_rupture()
    article['stock_bloquant'] = (
        stock_du_produit.est_en_rupture()
        and not stock_du_produit.autoriser_vente_hors_stock
    )
except Stock.DoesNotExist:
    article['stock_quantite'] = None  # Pas de gestion de stock
```

Important : ajouter `select_related('stock_inventaire')` dans la requête Product pour éviter les N+1 queries.

- [ ] **Step 2: Adapter le template des tuiles articles**

Dans le template des tuiles POS (probablement `laboutik/templates/laboutik/cotton/articles.html` ou similaire), ajouter le rendu conditionnel :

```html
{% if article.stock_quantite is not None %}
    {% if article.stock_bloquant %}
        {# Produit grisé, non cliquable #}
        <span class="stock-badge stock-rupture" aria-live="polite"
              data-testid="stock-badge-rupture">
            {% translate "Rupture" %}
        </span>
    {% elif article.stock_en_rupture %}
        {# Pastille rouge, reste cliquable #}
        <span class="stock-badge stock-negatif" aria-live="polite"
              data-testid="stock-badge-negatif">
            {% translate "Stock bas" %}
        </span>
    {% elif article.stock_en_alerte %}
        {# Pastille orange #}
        <span class="stock-badge stock-alerte" aria-live="polite"
              data-testid="stock-badge-alerte">
            {{ article.stock_quantite_lisible }}
        </span>
    {% endif %}
{% endif %}
```

- [ ] **Step 3: Lancer les tests existants**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q --tb=line 2>&1 | tail -20
```

Expected: 0 régression.

---

## Session 25 — Actions rapides POS + API débit mètre + clôture

### Task 8 : Serializers DRF

**Files:**
- Create: `inventaire/serializers.py`

- [ ] **Step 1: Créer les serializers**

```python
# inventaire/serializers.py
"""
Serializers DRF pour la validation des actions de stock.
Jamais de Django Forms — toujours DRF Serializer.
/ DRF serializers for stock action validation. Never Django Forms.

LOCALISATION : inventaire/serializers.py
"""
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _


class MouvementRapideSerializer(serializers.Serializer):
    """
    Validation pour les actions rapides POS (réception, perte, offert).
    La quantité est saisie en unité pratique (litres, kg, pièces)
    et convertie en unité de base côté serveur.
    / Validation for quick POS actions. Quantity is entered in practical
    units and converted to base unit server-side.
    """
    quantite = serializers.IntegerField(
        min_value=1,
        error_messages={
            'min_value': _("La quantité doit être supérieure à 0. / Quantity must be greater than 0."),
            'required': _("La quantité est obligatoire. / Quantity is required."),
        },
    )
    motif = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
    )


class AjustementSerializer(serializers.Serializer):
    """
    Validation pour l'ajustement inventaire (admin).
    L'utilisateur saisit le stock réel compté.
    / Validation for inventory adjustment (admin). User enters real counted stock.
    """
    stock_reel = serializers.IntegerField(
        error_messages={
            'required': _("Le stock réel est obligatoire. / Real stock is required."),
        },
    )
    motif = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
    )


class DebitMetreSerializer(serializers.Serializer):
    """
    Validation pour l'endpoint capteur débit mètre (Raspberry Pi).
    / Validation for the flow meter sensor endpoint (Raspberry Pi).
    """
    product_uuid = serializers.UUIDField(
        error_messages={
            'required': _("L'UUID du produit est obligatoire. / Product UUID is required."),
        },
    )
    quantite_cl = serializers.IntegerField(
        min_value=1,
        error_messages={
            'min_value': _("La quantité doit être supérieure à 0. / Quantity must be greater than 0."),
        },
    )
    capteur_id = serializers.CharField(
        max_length=100,
        error_messages={
            'required': _("L'identifiant du capteur est obligatoire. / Sensor ID is required."),
        },
    )
```

- [ ] **Step 2: Ruff check**

```bash
docker exec lespass_django poetry run ruff check --fix inventaire/serializers.py
docker exec lespass_django poetry run ruff format inventaire/serializers.py
```

---

### Task 9 : StockViewSet + DebitMetreViewSet

**Files:**
- Create: `inventaire/views.py`
- Create: `inventaire/urls.py`
- Modify: `TiBillet/urls.py` (inclure les URLs inventaire)
- Test: `tests/pytest/test_inventaire.py` (ajouter tests vues)

- [ ] **Step 1: Écrire les tests des vues**

Ajouter dans `tests/pytest/test_inventaire.py` :

```python
from rest_framework.test import APIClient


class TestStockViewSet(FastTenantTestCase):
    """
    Tests HTTP pour les actions rapides de stock depuis le POS.
    / HTTP tests for quick stock actions from POS.
    """

    @classmethod
    def get_test_schema_name(cls):
        return 'test_inventaire'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-inventaire.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.categorie = Client.SALLE_SPECTACLE
        tenant.save()

    def setUp(self):
        connection.set_tenant(self.tenant)

        self.tva_20, _ = Tva.objects.get_or_create(name="20%", rate=20)
        self.produit = Product.objects.create(
            name="Bière Vue Test",
            methode_caisse='VT',
            tva=self.tva_20,
        )
        self.stock = Stock.objects.create(
            product=self.produit,
            quantite=3000,
            unite=UniteStock.CENTILITRE,
        )

        self.client = APIClient()
        self.client.defaults['HTTP_HOST'] = 'test-inventaire.tibillet.localhost'

        # Créer un admin pour l'authentification
        # / Create an admin for authentication
        from AuthBillet.models import TibilletUser
        self.admin_user, _ = TibilletUser.objects.get_or_create(
            email='admin-inventaire@test.com',
            defaults={
                'is_staff': True,
                'is_superuser': True,
                'is_active': True,
            }
        )
        self.admin_user.set_password('testpass')
        self.admin_user.save()
        self.client.force_authenticate(user=self.admin_user)

    def test_reception_stock(self):
        """
        POST reception ajoute du stock.
        / POST reception adds stock.
        """
        response = self.client.post(
            f'/api/inventaire/stock/{self.stock.pk}/reception/',
            {'quantite': 3000, 'motif': 'Fût de 30L'},
            format='json',
        )
        assert response.status_code == 200
        self.stock.refresh_from_db()
        assert self.stock.quantite == 6000

    def test_perte_stock(self):
        """
        POST perte retire du stock.
        / POST loss removes stock.
        """
        response = self.client.post(
            f'/api/inventaire/stock/{self.stock.pk}/perte/',
            {'quantite': 200, 'motif': 'Fût tombé'},
            format='json',
        )
        assert response.status_code == 200
        self.stock.refresh_from_db()
        assert self.stock.quantite == 2800

    def test_offert_stock(self):
        """
        POST offert retire du stock.
        / POST complimentary removes stock.
        """
        response = self.client.post(
            f'/api/inventaire/stock/{self.stock.pk}/offert/',
            {'quantite': 50},
            format='json',
        )
        assert response.status_code == 200
        self.stock.refresh_from_db()
        assert self.stock.quantite == 2950

    def test_reception_quantite_invalide(self):
        """
        quantite=0 retourne 400.
        / quantity=0 returns 400.
        """
        response = self.client.post(
            f'/api/inventaire/stock/{self.stock.pk}/reception/',
            {'quantite': 0},
            format='json',
        )
        assert response.status_code == 400


class TestDebitMetreViewSet(FastTenantTestCase):
    """
    Tests HTTP pour l'endpoint débit mètre.
    / HTTP tests for flow meter endpoint.
    """

    @classmethod
    def get_test_schema_name(cls):
        return 'test_inventaire'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-inventaire.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.categorie = Client.SALLE_SPECTACLE
        tenant.save()

    def setUp(self):
        connection.set_tenant(self.tenant)

        self.tva_20, _ = Tva.objects.get_or_create(name="20%", rate=20)
        self.produit = Product.objects.create(
            name="Bière Capteur Test",
            methode_caisse='VT',
            tva=self.tva_20,
        )
        self.stock = Stock.objects.create(
            product=self.produit,
            quantite=5000,
            unite=UniteStock.CENTILITRE,
        )

        self.client = APIClient()
        self.client.defaults['HTTP_HOST'] = 'test-inventaire.tibillet.localhost'

        from AuthBillet.models import TibilletUser
        self.admin_user, _ = TibilletUser.objects.get_or_create(
            email='admin-capteur@test.com',
            defaults={'is_staff': True, 'is_superuser': True, 'is_active': True},
        )
        self.admin_user.set_password('testpass')
        self.admin_user.save()
        self.client.force_authenticate(user=self.admin_user)

    def test_debit_metre_decremente(self):
        """
        POST débit mètre décrémente le stock en CL.
        / POST flow meter decrements stock in CL.
        """
        response = self.client.post(
            '/api/inventaire/debit-metre/',
            {
                'product_uuid': str(self.produit.uuid),
                'quantite_cl': 850,
                'capteur_id': 'pi-tireuse-01',
            },
            format='json',
        )
        assert response.status_code == 201
        self.stock.refresh_from_db()
        assert self.stock.quantite == 4150

        mouvement = MouvementStock.objects.first()
        assert mouvement.type_mouvement == TypeMouvement.DEBIT_METRE
        assert mouvement.motif == 'pi-tireuse-01'

    def test_debit_metre_produit_sans_stock_cl(self):
        """
        Erreur si le produit n'a pas de stock en CL.
        / Error if product doesn't have stock in CL.
        """
        produit_unite = Product.objects.create(
            name="Produit Unités",
            methode_caisse='VT',
            tva=self.tva_20,
        )
        Stock.objects.create(
            product=produit_unite,
            quantite=10,
            unite=UniteStock.UNITE,  # Pas CL
        )
        response = self.client.post(
            '/api/inventaire/debit-metre/',
            {
                'product_uuid': str(produit_unite.uuid),
                'quantite_cl': 100,
                'capteur_id': 'pi-test',
            },
            format='json',
        )
        assert response.status_code == 400
```

- [ ] **Step 2: Créer les ViewSets**

```python
# inventaire/views.py
"""
ViewSets pour les actions de stock : actions rapides POS + débit mètre.
/ ViewSets for stock actions: quick POS actions + flow meter.

LOCALISATION : inventaire/views.py

FLUX :
- StockViewSet : actions caissier (réception, perte, offert)
- DebitMetreViewSet : endpoint API pour capteur Raspberry Pi
"""
import logging

from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from BaseBillet.models import Product
from inventaire.models import Stock, TypeMouvement, UniteStock
from inventaire.serializers import DebitMetreSerializer, MouvementRapideSerializer
from inventaire.services import StockService
from laboutik.permissions import HasLaBoutikAccess

logger = logging.getLogger(__name__)


class StockViewSet(viewsets.ViewSet):
    """
    Actions rapides de stock depuis le POS.
    / Quick stock actions from POS.

    LOCALISATION : inventaire/views.py

    3 actions : réception (+), perte (-), offert (-).
    Chaque action crée un MouvementStock et met à jour le stock atomiquement.
    """
    permission_classes = [HasLaBoutikAccess]

    @action(detail=True, methods=["POST"], url_path="reception", url_name="reception")
    def reception(self, request, pk=None):
        """
        Ajouter du stock (réception livraison).
        / Add stock (delivery reception).
        """
        stock = get_object_or_404(Stock, pk=pk)
        serializer = MouvementRapideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        StockService.creer_mouvement(
            stock=stock,
            type_mouvement=TypeMouvement.RECEPTION,
            quantite=serializer.validated_data['quantite'],
            motif=serializer.validated_data.get('motif', ''),
            utilisateur=request.user if request.user.is_authenticated else None,
        )

        stock.refresh_from_db()
        return Response({
            'stock_actuel': stock.quantite,
            'unite': stock.unite,
        })

    @action(detail=True, methods=["POST"], url_path="perte", url_name="perte")
    def perte(self, request, pk=None):
        """
        Retirer du stock (perte / casse).
        / Remove stock (loss / breakage).
        """
        stock = get_object_or_404(Stock, pk=pk)
        serializer = MouvementRapideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        StockService.creer_mouvement(
            stock=stock,
            type_mouvement=TypeMouvement.PERTE,
            quantite=serializer.validated_data['quantite'],
            motif=serializer.validated_data.get('motif', ''),
            utilisateur=request.user if request.user.is_authenticated else None,
        )

        stock.refresh_from_db()
        return Response({
            'stock_actuel': stock.quantite,
            'unite': stock.unite,
        })

    @action(detail=True, methods=["POST"], url_path="offert", url_name="offert")
    def offert(self, request, pk=None):
        """
        Retirer du stock (offert / gratuit).
        / Remove stock (complimentary / free).
        """
        stock = get_object_or_404(Stock, pk=pk)
        serializer = MouvementRapideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        StockService.creer_mouvement(
            stock=stock,
            type_mouvement=TypeMouvement.OFFERT,
            quantite=serializer.validated_data['quantite'],
            motif=serializer.validated_data.get('motif', ''),
            utilisateur=request.user if request.user.is_authenticated else None,
        )

        stock.refresh_from_db()
        return Response({
            'stock_actuel': stock.quantite,
            'unite': stock.unite,
        })


class DebitMetreViewSet(viewsets.ViewSet):
    """
    Endpoint API pour le capteur de débit (Raspberry Pi).
    / API endpoint for flow meter sensor (Raspberry Pi).

    LOCALISATION : inventaire/views.py

    Reçoit les lectures du capteur et crée un mouvement DEBIT_METRE.
    Le capteur_id est stocké dans le champ motif du mouvement.
    """
    permission_classes = [HasLaBoutikAccess]

    def create(self, request):
        """
        POST /api/inventaire/debit-metre/
        Crée un mouvement de débit mètre.
        / Creates a flow meter movement.
        """
        serializer = DebitMetreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        donnees = serializer.validated_data
        produit = get_object_or_404(Product, uuid=donnees['product_uuid'])

        # Vérifier que le produit a un stock en centilitres
        # / Verify product has stock in centiliters
        try:
            stock = produit.stock_inventaire
        except Stock.DoesNotExist:
            return Response(
                {'error': _("Ce produit n'a pas de stock configuré. / This product has no configured stock.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if stock.unite != UniteStock.CENTILITRE:
            return Response(
                {'error': _("Le débit mètre nécessite un stock en centilitres. / Flow meter requires stock in centiliters.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        StockService.creer_mouvement(
            stock=stock,
            type_mouvement=TypeMouvement.DEBIT_METRE,
            quantite=donnees['quantite_cl'],
            motif=donnees['capteur_id'],
            utilisateur=None,  # Capteur = système
        )

        stock.refresh_from_db()
        return Response(
            {
                'stock_actuel': stock.quantite,
                'unite': stock.unite,
                'product_uuid': str(produit.uuid),
            },
            status=status.HTTP_201_CREATED,
        )
```

- [ ] **Step 3: Créer les URLs**

```python
# inventaire/urls.py
"""
Routes DRF pour l'app inventaire.
/ DRF routes for the inventory app.

LOCALISATION : inventaire/urls.py
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from inventaire.views import DebitMetreViewSet, StockViewSet

router = DefaultRouter()
router.register(r'stock', StockViewSet, basename='stock')
router.register(r'debit-metre', DebitMetreViewSet, basename='debit-metre')

urlpatterns = [
    path('', include(router.urls)),
]
```

- [ ] **Step 4: Inclure les URLs dans le projet**

Dans `TiBillet/urls.py`, ajouter :

```python
    path('api/inventaire/', include('inventaire.urls')),
```

Chercher la section des `urlpatterns` et ajouter cette ligne à côté des autres includes d'API.

- [ ] **Step 5: Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_inventaire.py -v
```

Expected: tous passent.

- [ ] **Step 6: Lancer les tests existants pour vérifier 0 régression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q --tb=line 2>&1 | tail -20
```

---

### Task 10 : Résumé stock dans la clôture de caisse

**Files:**
- Modify: `inventaire/services.py` (ajouter ResumeStockService)
- Modify: `laboutik/views.py` (brancher dans le flux de clôture)
- Test: `tests/pytest/test_inventaire.py`

- [ ] **Step 1: Écrire les tests du résumé clôture**

Ajouter dans `tests/pytest/test_inventaire.py` :

```python
class TestResumeStockCloture(FastTenantTestCase):
    """
    Tests pour le résumé stock intégré à la clôture.
    / Tests for stock summary integrated into closure.
    """

    @classmethod
    def get_test_schema_name(cls):
        return 'test_inventaire'

    @classmethod
    def get_test_tenant_domain(cls):
        return 'test-inventaire.tibillet.localhost'

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.categorie = Client.SALLE_SPECTACLE
        tenant.save()

    def setUp(self):
        connection.set_tenant(self.tenant)

        self.tva_20, _ = Tva.objects.get_or_create(name="20%", rate=20)
        self.produit = Product.objects.create(
            name="Bière Clôture",
            methode_caisse='VT',
            tva=self.tva_20,
        )
        self.stock = Stock.objects.create(
            product=self.produit,
            quantite=3000,
            unite=UniteStock.CENTILITRE,
            seuil_alerte=500,
        )

        # Créer des mouvements de test (sans clôture rattachée)
        # / Create test movements (without linked closure)
        MouvementStock.objects.create(
            stock=self.stock,
            type_mouvement=TypeMouvement.VENTE,
            quantite=-100,
            quantite_avant=3000,
        )
        MouvementStock.objects.create(
            stock=self.stock,
            type_mouvement=TypeMouvement.PERTE,
            quantite=-50,
            quantite_avant=2900,
            motif="Casse",
        )
        MouvementStock.objects.create(
            stock=self.stock,
            type_mouvement=TypeMouvement.OFFERT,
            quantite=-25,
            quantite_avant=2850,
        )

    def test_generer_resume_cloture(self):
        """
        Le résumé contient la consommation par produit et les pertes.
        / Summary contains consumption per product and losses.
        """
        from inventaire.services import ResumeStockService

        resume = ResumeStockService.generer_resume(
            mouvements_sans_cloture=MouvementStock.objects.filter(cloture__isnull=True)
        )

        assert 'par_produit' in resume
        assert len(resume['par_produit']) == 1

        produit_resume = resume['par_produit'][0]
        assert produit_resume['nom'] == "Bière Clôture"
        assert produit_resume['ventes'] == -100
        assert produit_resume['pertes'] == -50
        assert produit_resume['offerts'] == -25

    def test_rattacher_mouvements_a_cloture(self):
        """
        Les mouvements sans clôture sont rattachés à la nouvelle clôture.
        / Movements without closure are attached to the new closure.
        """
        from laboutik.models import ClotureCaisse
        from inventaire.services import ResumeStockService

        cloture = ClotureCaisse.objects.create()

        nombre_rattaches = ResumeStockService.rattacher_a_cloture(cloture)
        assert nombre_rattaches == 3

        mouvements_rattaches = MouvementStock.objects.filter(cloture=cloture)
        assert mouvements_rattaches.count() == 3
```

- [ ] **Step 2: Implémenter ResumeStockService**

Ajouter dans `inventaire/services.py` :

```python
class ResumeStockService:
    """
    Service pour le résumé stock intégré aux clôtures de caisse.
    / Service for stock summary integrated into cash closures.

    LOCALISATION : inventaire/services.py
    """

    @staticmethod
    def generer_resume(mouvements_sans_cloture):
        """
        Génère un résumé JSON-serializable des mouvements de stock.
        / Generates a JSON-serializable summary of stock movements.

        :param mouvements_sans_cloture: QuerySet de MouvementStock
        :return: dict avec 'par_produit' et 'alertes'
        """
        # Agréger par produit et par type
        # / Aggregate by product and type
        produits_data = {}

        for mouvement in mouvements_sans_cloture.select_related('stock__product'):
            nom_produit = mouvement.stock.product.name
            product_uuid = str(mouvement.stock.product.uuid)

            if product_uuid not in produits_data:
                produits_data[product_uuid] = {
                    'nom': nom_produit,
                    'unite': mouvement.stock.unite,
                    'ventes': 0,
                    'receptions': 0,
                    'pertes': 0,
                    'offerts': 0,
                    'debit_metre': 0,
                    'ajustements': 0,
                }

            donnees = produits_data[product_uuid]
            type_mv = mouvement.type_mouvement

            if type_mv == TypeMouvement.VENTE:
                donnees['ventes'] += mouvement.quantite
            elif type_mv == TypeMouvement.RECEPTION:
                donnees['receptions'] += mouvement.quantite
            elif type_mv == TypeMouvement.PERTE:
                donnees['pertes'] += mouvement.quantite
            elif type_mv == TypeMouvement.OFFERT:
                donnees['offerts'] += mouvement.quantite
            elif type_mv == TypeMouvement.DEBIT_METRE:
                donnees['debit_metre'] += mouvement.quantite
            elif type_mv == TypeMouvement.AJUSTEMENT:
                donnees['ajustements'] += mouvement.quantite

        # Alertes stock bas
        # / Low stock alerts
        alertes = []
        for stock in Stock.objects.select_related('product').all():
            if stock.est_en_alerte() or stock.est_en_rupture():
                alertes.append({
                    'nom': stock.product.name,
                    'quantite': stock.quantite,
                    'unite': stock.unite,
                    'seuil': stock.seuil_alerte,
                    'en_rupture': stock.est_en_rupture(),
                })

        return {
            'par_produit': list(produits_data.values()),
            'alertes': alertes,
        }

    @staticmethod
    def rattacher_a_cloture(cloture):
        """
        Rattache tous les mouvements sans clôture à la clôture donnée.
        / Attaches all movements without closure to the given closure.

        :param cloture: ClotureCaisse instance
        :return: int nombre de mouvements rattachés
        """
        nombre_rattaches = MouvementStock.objects.filter(
            cloture__isnull=True,
        ).update(cloture=cloture)

        logger.info(f"Clôture {cloture.pk} : {nombre_rattaches} mouvements stock rattachés")
        return nombre_rattaches
```

- [ ] **Step 3: Brancher dans le flux de clôture**

Dans `laboutik/views.py`, dans la méthode de clôture (chercher `cloturer` ou `cloture` dans CaisseViewSet), après la création de la ClotureCaisse et le calcul du rapport, ajouter :

```python
        # --- Résumé stock inventaire ---
        # Rattacher les mouvements et ajouter le résumé au rapport
        # / Attach movements and add summary to the report
        try:
            from inventaire.models import MouvementStock
            from inventaire.services import ResumeStockService

            mouvements_sans_cloture = MouvementStock.objects.filter(cloture__isnull=True)

            if mouvements_sans_cloture.exists():
                resume_stock = ResumeStockService.generer_resume(mouvements_sans_cloture)
                ResumeStockService.rattacher_a_cloture(cloture)

                # Ajouter au rapport JSON existant
                # / Add to existing JSON report
                rapport = cloture.rapport_json or {}
                rapport['inventaire'] = resume_stock
                cloture.rapport_json = rapport
                cloture.save(update_fields=['rapport_json'])
        except ImportError:
            pass  # App inventaire non installée
```

- [ ] **Step 4: Lancer tous les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_inventaire.py -v
docker exec lespass_django poetry run pytest tests/pytest/ -q --tb=line 2>&1 | tail -20
```

Expected: tous passent, 0 régression.

- [ ] **Step 5: Ruff check final**

```bash
docker exec lespass_django poetry run ruff check --fix inventaire/
docker exec lespass_django poetry run ruff format inventaire/
```

---

### Task 11 : Action ajustement inventaire dans l'admin

**Files:**
- Modify: `Administration/admin/inventaire.py` (ajouter get_urls + vue)
- Create: `Administration/templates/admin/inventaire/ajustement_form.html`

- [ ] **Step 1: Ajouter l'action ajustement dans MouvementStockAdmin**

Ce n'est pas sur MouvementStockAdmin (lecture seule) mais sur POSProductAdmin. Ajouter dans `Administration/admin/products.py`, dans la classe `POSProductAdmin` :

```python
    # Template avec bouton ajustement inventaire
    # / Template with inventory adjustment button
    change_form_after_template = "admin/inventaire/ajustement_form.html"

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/ajustement-stock/',
                self.admin_site.admin_view(
                    csrf_protect(require_POST(self._ajustement_stock_view))
                ),
                name='basebillet_posproduct_ajustement_stock',
            ),
        ]
        return custom_urls + urls

    def _ajustement_stock_view(self, request, object_id):
        """
        Traite un ajustement de stock depuis l'admin.
        / Processes a stock adjustment from the admin.
        """
        from inventaire.models import Stock
        from inventaire.serializers import AjustementSerializer
        from inventaire.services import StockService

        product = get_object_or_404(Product, pk=object_id)

        try:
            stock = product.stock_inventaire
        except Stock.DoesNotExist:
            messages.error(request, _("Ce produit n'a pas de stock configuré."))
            return redirect(request.META.get("HTTP_REFERER", "/"))

        serializer = AjustementSerializer(data=request.POST)
        if not serializer.is_valid():
            messages.error(request, str(serializer.errors))
            return redirect(request.META.get("HTTP_REFERER", "/"))

        StockService.ajuster_inventaire(
            stock=stock,
            stock_reel=serializer.validated_data['stock_reel'],
            motif=serializer.validated_data.get('motif', ''),
            utilisateur=request.user,
        )

        messages.success(
            request,
            _("Stock ajusté pour %(product)s.") % {'product': product.name},
        )
        return redirect(request.META.get("HTTP_REFERER", "/"))
```

Ajouter les imports nécessaires en haut du fichier si pas déjà présents :
```python
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
```

- [ ] **Step 2: Créer le template ajustement**

```html
<!-- Administration/templates/admin/inventaire/ajustement_form.html -->
<!--
FORMULAIRE D'AJUSTEMENT INVENTAIRE
/ Inventory adjustment form

LOCALISATION : Administration/templates/admin/inventaire/ajustement_form.html

Affiché sous le formulaire produit POS. Visible uniquement si
le produit a un Stock lié.
-->
{% load i18n %}

{% if original and original.stock_inventaire %}
{% with stock=original.stock_inventaire %}
<div style="margin-top: 20px; padding: 16px; border: 1px solid var(--color-primary-200, #e5e7eb); border-radius: 8px; background: var(--color-base-0, #fff);">
    <h3 style="margin: 0 0 12px 0; font-size: 16px; font-weight: 600;">
        <span style="margin-right: 6px;" aria-hidden="true">📦</span>
        {% translate "Ajustement inventaire" %}
    </h3>

    <p style="margin: 0 0 12px 0; color: var(--color-base-500, #6b7280);">
        {% translate "Stock actuel" %} :
        <strong>{{ stock.quantite }} {{ stock.get_unite_display }}</strong>
        {% if stock.est_en_alerte %}
            <span style="color: #d97706; font-weight: 600;">⚠ {% translate "Alerte" %}</span>
        {% elif stock.est_en_rupture %}
            <span style="color: #dc2626; font-weight: 600;">⛔ {% translate "Rupture" %}</span>
        {% endif %}
    </p>

    <form method="post"
          action="../ajustement-stock/"
          style="display: flex; gap: 8px; align-items: flex-end; flex-wrap: wrap;">
        {% csrf_token %}

        <div>
            <label for="stock_reel" style="display: block; font-size: 13px; margin-bottom: 4px;">
                {% translate "Stock réel compté" %}
            </label>
            <input type="number" name="stock_reel" id="stock_reel" required
                   style="padding: 8px 12px; border: 1px solid var(--color-base-300, #d1d5db); border-radius: 6px; width: 150px;"
                   placeholder="{{ stock.quantite }}"
                   data-testid="input-stock-reel">
        </div>

        <div>
            <label for="motif" style="display: block; font-size: 13px; margin-bottom: 4px;">
                {% translate "Motif (optionnel)" %}
            </label>
            <input type="text" name="motif" id="motif" maxlength="200"
                   style="padding: 8px 12px; border: 1px solid var(--color-base-300, #d1d5db); border-radius: 6px; width: 250px;"
                   placeholder="{% translate 'Inventaire physique' %}"
                   data-testid="input-motif-ajustement">
        </div>

        <button type="submit"
                style="padding: 8px 16px; background-color: #d97706; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 500;"
                data-testid="btn-ajustement-stock">
            {% translate "Ajuster" %}
        </button>
    </form>
</div>
{% endwith %}
{% endif %}
```

- [ ] **Step 3: Vérifier manage.py check + ruff**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run ruff check --fix Administration/admin/products.py Administration/admin/inventaire.py
```

- [ ] **Step 4: Lancer tous les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q --tb=line 2>&1 | tail -20
```

Expected: 0 régression.

---

### Task 12 : Templates POS — modale actions rapides

**Files:**
- Create: `inventaire/templates/inventaire/partial/modale_mouvement.html`

- [ ] **Step 1: Créer le template de la modale**

```html
<!-- inventaire/templates/inventaire/partial/modale_mouvement.html -->
<!--
MODALE D'ACTION RAPIDE STOCK (POS)
/ Quick stock action modal (POS)

LOCALISATION : inventaire/templates/inventaire/partial/modale_mouvement.html

Chargée en hx-get depuis le menu contextuel d'un article POS.
Soumet en hx-post vers StockViewSet (réception/perte/offert).

COMMUNICATION :
Reçoit : hx-get depuis le bouton article
Émet : hx-post vers /api/inventaire/stock/{pk}/{action}/
-->
{% load i18n %}

<div id="modale-stock" style="padding: 16px;" data-testid="modale-stock">
    <h4 style="margin: 0 0 12px;">
        {{ product_name }} — {{ action_label }}
    </h4>

    <form hx-post="{{ action_url }}"
          hx-target="#modale-stock"
          hx-swap="outerHTML">
        {% csrf_token %}

        <div style="margin-bottom: 12px;">
            <label for="quantite" style="display: block; margin-bottom: 4px;">
                {% translate "Quantité" %} ({{ unite_label }})
            </label>
            <input type="number" name="quantite" id="quantite" min="1" required
                   style="padding: 8px; border: 1px solid #ccc; border-radius: 4px; width: 120px;"
                   data-testid="input-quantite-mouvement">
        </div>

        <div style="margin-bottom: 12px;">
            <label for="motif" style="display: block; margin-bottom: 4px;">
                {% translate "Motif (optionnel)" %}
            </label>
            <input type="text" name="motif" id="motif" maxlength="200"
                   style="padding: 8px; border: 1px solid #ccc; border-radius: 4px; width: 100%;"
                   data-testid="input-motif-mouvement">
        </div>

        <div style="display: flex; gap: 8px;">
            <button type="submit"
                    style="padding: 8px 16px; background: var(--color-primary-600, #2563eb); color: white; border: none; border-radius: 4px; cursor: pointer;"
                    data-testid="btn-valider-mouvement">
                {% translate "Valider" %}
            </button>
            <button type="button"
                    onclick="this.closest('#modale-stock').remove()"
                    style="padding: 8px 16px; background: #6b7280; color: white; border: none; border-radius: 4px; cursor: pointer;"
                    data-testid="btn-annuler-mouvement">
                {% translate "Annuler" %}
            </button>
        </div>
    </form>
</div>
```

- [ ] **Step 2: Créer le dossier templates**

```bash
mkdir -p /home/jonas/TiBillet/dev/Lespass/inventaire/templates/inventaire/partial/
mkdir -p /home/jonas/TiBillet/dev/Lespass/Administration/templates/admin/inventaire/
```

---

### Task 13 : Documentation et CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`
- Create: `TECH DOC/A TESTER/inventaire-stock-pos.md`

- [ ] **Step 1: Mettre à jour le CHANGELOG**

Ajouter en haut de `CHANGELOG.md` :

```markdown
## XX. Gestion d'inventaire et stock POS / POS Inventory and Stock Management

**Quoi / What:** Nouvelle app `inventaire` (TENANT_APP) pour gérer le stock des produits POS. Stock optionnel par produit, 3 unités (pièces/cl/g), journal de mouvements (6 types), décrémentation atomique à la vente, alertes visuelles, actions rapides caissier, endpoint débit mètre pour capteur Pi.

**Pourquoi / Why:** Les bars et salles associatifs ont besoin de tracer leur stock pour l'AG et détecter les écarts (casse, offerts, vol). Système minimaliste adapté aux 20-50 références d'un petit lieu.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `inventaire/*` | Nouvelle app : models, services, views, serializers, urls, admin |
| `BaseBillet/models.py` | `module_inventaire` sur Configuration + `contenance` sur Price |
| `TiBillet/settings.py` | `'inventaire'` dans TENANT_APPS |
| `Administration/admin/dashboard.py` | MODULE_FIELDS + sidebar |
| `Administration/admin/products.py` | StockInline + ajustement |
| `Administration/admin/inventaire.py` | MouvementStockAdmin |
| `laboutik/views.py` | Branchement décrémentation + résumé clôture |

### Migration
- **Migration nécessaire / Migration required:** Oui
- `inventaire/migrations/0001_initial.py` + `BaseBillet/migrations/XXXX_module_inventaire_contenance.py`
- `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`
```

- [ ] **Step 2: Créer la doc de test**

Créer `TECH DOC/A TESTER/inventaire-stock-pos.md` avec les scénarios de test manuel (vérification admin, POS, actions rapides, alertes visuelles, clôture). Le contenu détaillé sera rédigé à l'implémentation.

- [ ] **Step 3: Lancer i18n**

```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
# Éditer les .po, supprimer les fuzzy
docker exec lespass_django poetry run django-admin compilemessages
```

- [ ] **Step 4: Tests finaux complets**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: 0 régression, 0 issue.
