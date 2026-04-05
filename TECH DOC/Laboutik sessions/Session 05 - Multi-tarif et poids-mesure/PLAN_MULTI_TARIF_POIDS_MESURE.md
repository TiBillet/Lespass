# Multi-Tarif + Poids/Mesure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refondre l'overlay tarif pour supporter le multi-clic (overlay reste ouvert, panier visible) et ajouter un nouveau type de tarif "poids/mesure" avec pave numerique integre.

**Architecture:** 2 nouveaux champs DB (`Price.poids_mesure` + `LigneArticle.weight_quantity`), validation admin avec champs conditionnels JS existants, refonte JS de l'overlay (`tarif.js`) pour 3 types de boutons (fixe/libre/poids) + pave numerique, adaptation backend pour la decrementation stock par quantite variable et inclusion dans le HMAC LNE.

**Tech Stack:** Django 4.2, django-unfold (admin), vanilla JS (pave numerique), HTMX, CSS custom properties, ESC/POS (tickets)

**Spec:** `TECH DOC/Laboutik sessions/Session 05 - Multi-tarif et poids-mesure/DESIGN_MULTI_TARIF_POIDS_MESURE.md`

---

## File Map

| Fichier | Action |
|---------|--------|
| `BaseBillet/models.py` | Modifier : ajouter `Price.poids_mesure` BooleanField (ligne ~1330) |
| `BaseBillet/models.py` | Modifier : ajouter `LigneArticle.weight_quantity` IntegerField nullable (ligne ~3060) |
| `BaseBillet/migrations/XXXX_price_poids_mesure.py` | Creer : 1 migration (2 champs) |
| `Administration/admin/products.py` | Modifier : `POSPriceInline` (ligne 486) — ajouter `poids_mesure` dans fields, `inline_conditional_fields`, validation `clean()` |
| `laboutik/integrity.py` | Modifier : `calculer_hmac()` (ligne 41) — ajouter `weight_quantity` |
| `laboutik/views.py` | Modifier : `_construire_donnees_articles()` (ligne 446), `_extraire_articles_du_panier()` (ligne 2998), `_creer_lignes_articles()` (ligne 3280) |
| `laboutik/static/js/tarif.js` | Modifier : refonte complete — multi-clic, injection `#articles-zone`, pave numerique |
| `laboutik/static/css/tarif.css` | Creer : styles overlay, pave numerique, responsive V2s |
| `laboutik/static/js/addition.js` | Modifier : gerer `weightAmount`/`weightUnit` dans les inputs hidden |
| `laboutik/templates/cotton/articles.html` | Modifier : tuile avec icone balance et prix /kg ou /L |
| `laboutik/printing/formatters.py` | Modifier : format ticket "350g x 28,00E/kg" |
| `laboutik/reports.py` | Modifier : `calculer_detail_ventes()` — ajout `poids_total` optionnel |
| `tests/pytest/test_poids_mesure.py` | Creer : tests modele, validation admin, HMAC, decrementation stock |
| `tests/pytest/test_multi_tarif_overlay.py` | Creer : tests extraction panier avec `weight-*` |

---

### Task 1 : Modeles — Price.poids_mesure + LigneArticle.weight_quantity

**Files:**
- Modify: `BaseBillet/models.py:1328-1331` (apres `free_price`)
- Modify: `BaseBillet/models.py:3054-3060` (apres `total_ht`)
- Create: `BaseBillet/migrations/XXXX_price_poids_mesure.py`

- [ ] **Step 1: Ajouter `poids_mesure` sur Price**

Dans `BaseBillet/models.py`, apres le champ `free_price` (ligne ~1330), ajouter :

```python
    poids_mesure = models.BooleanField(
        default=False,
        verbose_name=_("Sale by weight/volume"),
        help_text=_(
            "If checked, the cashier enters the weight or volume at each sale. "
            "The price is per kg (for grams) or per liter (for centiliters)."
        ),
    )
```

- [ ] **Step 2: Ajouter `weight_quantity` sur LigneArticle**

Dans `BaseBillet/models.py`, apres le champ `total_ht` (ligne ~3060), ajouter :

```python
    # Quantite saisie par le caissier pour les ventes au poids/volume (en unite stock : g ou cl).
    # Null pour les ventes classiques (tarif fixe ou prix libre).
    # Donnee elementaire LNE (exigence 3) : necessaire au calcul du total HT.
    # / Weight/volume entered by cashier for weight-based sales (in stock unit: g or cl).
    # Null for standard sales (fixed or free price).
    # LNE elementary data (requirement 3): necessary to compute total excl. tax.
    weight_quantity = models.IntegerField(
        null=True, blank=True,
        verbose_name=_("Quantity by weight/volume"),
        help_text=_(
            "Amount entered by cashier in stock unit (g or cl). "
            "Null for standard sales."
        ),
    )
```

- [ ] **Step 3: Generer et appliquer la migration**

Run: `docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations BaseBillet -n price_poids_mesure`
Run: `docker exec lespass_django poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing`
Expected: Migration appliquee sans erreur.

- [ ] **Step 4: Verifier manage.py check**

Run: `docker exec lespass_django poetry run python /DjangoFiles/manage.py check`
Expected: `System check identified no issues.`

---

### Task 2 : HMAC — inclure weight_quantity dans calculer_hmac()

**Files:**
- Modify: `laboutik/integrity.py:41-57`
- Create: `tests/pytest/test_poids_mesure.py`

- [ ] **Step 1: Ecrire les tests HMAC**

Creer `tests/pytest/test_poids_mesure.py` :

```python
"""
tests/pytest/test_poids_mesure.py — Tests poids/mesure : HMAC, modele, validation.
/ Tests for weight/volume sales: HMAC, model, validation.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_poids_mesure.py -v
"""

import sys

sys.path.insert(0, '/DjangoFiles')

import django

django.setup()

import pytest
from django_tenants.utils import tenant_context
from Customers.models import Client


TENANT_SCHEMA = 'lespass'


def _get_tenant():
    return Client.objects.get(schema_name=TENANT_SCHEMA)


class TestHmacWeightQuantity:
    """Le HMAC doit inclure weight_quantity pour la conformite LNE exigence 8.
    / HMAC must include weight_quantity for LNE compliance requirement 8."""

    def test_hmac_avec_weight_quantity_different_de_sans(self):
        """Le HMAC d'une ligne avec weight_quantity=350 est different d'une ligne sans.
        / HMAC of a line with weight_quantity=350 differs from one without."""
        from laboutik.integrity import calculer_hmac
        from unittest.mock import MagicMock

        # Ligne sans weight_quantity / Line without weight_quantity
        ligne_sans = MagicMock()
        ligne_sans.uuid = '00000000-0000-0000-0000-000000000001'
        ligne_sans.datetime = None
        ligne_sans.amount = 980
        ligne_sans.total_ht = 817
        ligne_sans.qty = 1
        ligne_sans.vat = 20.0
        ligne_sans.payment_method = 'CA'
        ligne_sans.status = 'V'
        ligne_sans.sale_origin = 'LB'
        ligne_sans.weight_quantity = None

        # Ligne avec weight_quantity / Line with weight_quantity
        ligne_avec = MagicMock()
        ligne_avec.uuid = '00000000-0000-0000-0000-000000000001'
        ligne_avec.datetime = None
        ligne_avec.amount = 980
        ligne_avec.total_ht = 817
        ligne_avec.qty = 1
        ligne_avec.vat = 20.0
        ligne_avec.payment_method = 'CA'
        ligne_avec.status = 'V'
        ligne_avec.sale_origin = 'LB'
        ligne_avec.weight_quantity = 350

        cle = 'test-secret-key'
        hmac_sans = calculer_hmac(ligne_sans, cle, '')
        hmac_avec = calculer_hmac(ligne_avec, cle, '')

        assert hmac_sans != hmac_avec, \
            "Le HMAC doit etre different quand weight_quantity change"

    def test_hmac_weight_quantity_none_produit_chaine_vide(self):
        """weight_quantity=None produit '' dans le hash (retrocompatible).
        / weight_quantity=None produces '' in the hash (backward compatible)."""
        from laboutik.integrity import calculer_hmac
        from unittest.mock import MagicMock

        ligne = MagicMock()
        ligne.uuid = '00000000-0000-0000-0000-000000000002'
        ligne.datetime = None
        ligne.amount = 500
        ligne.total_ht = 417
        ligne.qty = 1
        ligne.vat = 20.0
        ligne.payment_method = 'CA'
        ligne.status = 'V'
        ligne.sale_origin = 'LB'
        ligne.weight_quantity = None

        cle = 'test-secret-key'
        hmac_result = calculer_hmac(ligne, cle, '')

        # Le HMAC doit etre un hex de 64 caracteres
        # / HMAC must be a 64-char hex string
        assert len(hmac_result) == 64
        assert all(c in '0123456789abcdef' for c in hmac_result)
```

- [ ] **Step 2: Lancer les tests — doivent echouer (weight_quantity pas encore dans le HMAC)**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_poids_mesure.py::TestHmacWeightQuantity -v`
Expected: FAIL — `AttributeError: Mock object has no attribute 'weight_quantity'` ou le test passe mais les HMAC sont identiques (selon l'ordre d'implementation).

- [ ] **Step 3: Modifier calculer_hmac() pour inclure weight_quantity**

Dans `laboutik/integrity.py`, remplacer les lignes 41-57 :

```python
    donnees = json.dumps([
        str(ligne.uuid),
        str(ligne.datetime.isoformat()) if ligne.datetime else '',
        ligne.amount,
        ligne.total_ht,
        # Normaliser qty et vat en string avec 6 decimales pour que le hash
        # soit identique que l'objet vienne de la memoire (int/float)
        # ou de la DB (Decimal avec 6 decimales).
        # / Normalize qty and vat to 6-decimal strings so the hash is
        # identical whether the object comes from memory or from DB.
        f"{float(ligne.qty):.6f}",
        f"{float(ligne.vat):.2f}",
        ligne.payment_method or '',
        ligne.status or '',
        ligne.sale_origin or '',
        # Quantite poids/volume saisie par le caissier (donnee elementaire LNE exigence 3).
        # None → '' pour retrocompatibilite avec les lignes existantes.
        # / Weight/volume quantity entered by cashier (LNE elementary data requirement 3).
        # None → '' for backward compatibility with existing lines.
        str(ligne.weight_quantity) if ligne.weight_quantity is not None else '',
        previous_hmac,
    ])
```

- [ ] **Step 4: Lancer les tests HMAC — doivent passer**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_poids_mesure.py::TestHmacWeightQuantity -v`
Expected: 2 PASS

- [ ] **Step 5: Verifier que les tests d'integrite existants passent toujours**

Run: `docker exec lespass_django poetry run pytest tests/pytest/ -k "hmac or integrity or verify" -v`
Expected: tous PASS (les lignes existantes ont `weight_quantity=None` → `''`, le HMAC ne change pas pour elles).

**ATTENTION :** Si des tests existants echouent ici, c'est parce qu'ils utilisent des mocks de LigneArticle qui n'ont pas `weight_quantity`. Ajouter `weight_quantity=None` aux mocks concernes.

---

### Task 3 : Admin — POSPriceInline avec poids_mesure et validation

**Files:**
- Modify: `Administration/admin/products.py:486-492` (POSPriceInline)
- Modify: `Administration/admin/products.py:1310` (POSProductAdmin.changeform_view)

- [ ] **Step 1: Ajouter la validation clean() sur BasePriceInlineForm**

Dans `Administration/admin/products.py`, dans la classe `BasePriceInlineForm` (ligne ~292), ajouter apres `clean_prix()` :

```python
    def clean(self):
        cleaned = super().clean()
        poids_mesure = cleaned.get("poids_mesure", False)
        free_price = cleaned.get("free_price", False)
        contenance = cleaned.get("contenance")

        # Exclusion prix libre / poids_mesure
        # / Mutual exclusion: free price / weight-based
        if poids_mesure and free_price:
            raise forms.ValidationError(
                _("A price cannot be both free price and weight/volume-based."),
                code="invalid",
            )

        # Exclusion contenance / poids_mesure
        # / Mutual exclusion: contenance / weight-based
        if poids_mesure and contenance:
            raise forms.ValidationError(
                _("Contenance is incompatible with weight/volume sales "
                  "(quantity is entered at each sale)."),
                code="invalid",
            )

        return cleaned
```

- [ ] **Step 2: Modifier POSPriceInline — ajouter poids_mesure + champs conditionnels**

Remplacer la classe `POSPriceInline` (lignes 486-492) par :

```python
class POSPriceInline(BasePriceInline):
    """Inline tarifs pour les produits de caisse (POS).
    Ajoute contenance (volume par vente) et poids_mesure (vente au poids/volume).
    Le stock POS est gere par l'app inventaire.
    / Price inline for POS products.
    Adds contenance (volume per sale) and poids_mesure (weight/volume sales).
    POS stock managed by inventaire app."""

    fields = ("name", "prix", "poids_mesure", "contenance", ("publish", "order"))

    # Champs conditionnels : contenance cache si poids_mesure coche
    # (la quantite est saisie a chaque vente, pas fixe).
    # / Conditional fields: contenance hidden if poids_mesure checked
    # (quantity is entered at each sale, not fixed).
    inline_conditional_fields = {
        "contenance": "poids_mesure == false",
    }

    class Media:
        js = ("admin/js/inline_conditional_fields.js",)
```

- [ ] **Step 3: Ajouter le support conditional_fields sur POSProductAdmin**

Dans `POSProductAdmin` (ligne ~1310), ajouter `change_form_after_template` et `changeform_view` (meme pattern que MembershipProductAdmin) :

```python
    change_form_after_template = "admin/product/inline_conditional_fields.html"

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        # Collecte les regles conditionnelles de chaque inline qui en declare
        # / Collect conditional rules from each inline that declares them
        extra_context = extra_context or {}
        regles_conditionnelles = {}
        for inline_class in self.get_inlines(request, None):
            regles_inline = getattr(inline_class, "inline_conditional_fields", None)
            if regles_inline:
                prefixe = inline_class.model._meta.model_name + "s"
                regles_conditionnelles[prefixe] = regles_inline
        if regles_conditionnelles:
            extra_context["inline_conditional_rules"] = json.dumps(regles_conditionnelles)
        return super().changeform_view(request, object_id, form_url, extra_context)
```

**Note :** on utilise `self.get_inlines(request, None)` au lieu de `self.inlines` car POSProductAdmin a un `get_inlines()` dynamique (StockInline en mode add).

- [ ] **Step 4: Verifier la syntaxe et manage.py check**

Run: `docker exec lespass_django poetry run python /DjangoFiles/manage.py check`
Expected: `System check identified no issues.`

- [ ] **Step 5: Ecrire les tests de validation admin**

Ajouter dans `tests/pytest/test_poids_mesure.py` :

```python
class TestPoidsMesureValidation:
    """Validation admin : exclusions mutuelles poids_mesure / free_price / contenance.
    / Admin validation: mutual exclusions weight/free/contenance."""

    def test_poids_mesure_et_free_price_rejete(self, admin_client):
        """poids_mesure=True et free_price=True → erreur validation.
        / poids_mesure=True and free_price=True → validation error."""
        from Administration.admin.products import BasePriceInlineForm
        from BaseBillet.models import Price, Product

        with tenant_context(_get_tenant()):
            product = Product.objects.filter(methode_caisse__isnull=False).first()
            assert product is not None

            form = BasePriceInlineForm(data={
                'product': product.pk,
                'name': 'Test',
                'prix': '10.00',
                'free_price': True,
                'poids_mesure': True,
                'publish': True,
                'order': 100,
            })
            assert not form.is_valid(), "Le formulaire devrait etre invalide"
            assert '__all__' in form.errors

    def test_poids_mesure_et_contenance_rejete(self, admin_client):
        """poids_mesure=True et contenance renseignee → erreur validation.
        / poids_mesure=True and contenance set → validation error."""
        from Administration.admin.products import BasePriceInlineForm
        from BaseBillet.models import Product

        with tenant_context(_get_tenant()):
            product = Product.objects.filter(methode_caisse__isnull=False).first()

            form = BasePriceInlineForm(data={
                'product': product.pk,
                'name': 'Test',
                'prix': '10.00',
                'free_price': False,
                'poids_mesure': True,
                'contenance': 50,
                'publish': True,
                'order': 100,
            })
            assert not form.is_valid()
            assert '__all__' in form.errors

    def test_poids_mesure_seul_accepte(self, admin_client):
        """poids_mesure=True seul (sans free_price ni contenance) → valide.
        / poids_mesure=True alone (no free_price or contenance) → valid."""
        from Administration.admin.products import BasePriceInlineForm
        from BaseBillet.models import Product

        with tenant_context(_get_tenant()):
            product = Product.objects.filter(methode_caisse__isnull=False).first()

            form = BasePriceInlineForm(data={
                'product': product.pk,
                'name': 'Test poids',
                'prix': '28.00',
                'free_price': False,
                'poids_mesure': True,
                'publish': True,
                'order': 100,
            })
            # Le formulaire peut avoir d'autres erreurs (champs manquants),
            # mais pas l'erreur d'exclusion mutuelle
            # / Form may have other errors but not mutual exclusion
            if not form.is_valid():
                assert '__all__' not in form.errors, \
                    f"Erreur inattendue : {form.errors['__all__']}"
```

- [ ] **Step 6: Lancer les tests de validation**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_poids_mesure.py::TestPoidsMesureValidation -v`
Expected: 3 PASS

- [ ] **Step 7: Lancer les tests admin existants (regression)**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_price_inline_refactoring.py tests/pytest/test_admin_proxy_products.py -v`
Expected: tous PASS

---

### Task 4 : Creation automatique du Stock + validation unite

**Files:**
- Modify: `Administration/admin/products.py` (POSProductAdmin.save_related)

- [ ] **Step 1: Ajouter save_related sur POSProductAdmin**

Dans `POSProductAdmin`, ajouter apres `changeform_view()` :

```python
    def save_related(self, request, form, formsets, change):
        """Apres sauvegarde des inlines : si un tarif a poids_mesure=True
        et que le produit n'a pas de Stock, en creer un vide.
        / After saving inlines: if a price has poids_mesure=True
        and the product has no Stock, create an empty one."""
        super().save_related(request, form, formsets, change)
        produit = form.instance

        # Verifier si un tarif poids_mesure existe pour ce produit
        # / Check if a weight-based price exists for this product
        a_tarif_poids = produit.prices.filter(poids_mesure=True).exists()
        if not a_tarif_poids:
            return

        # Verifier si le produit a deja un Stock
        # / Check if the product already has a Stock
        try:
            stock_existant = produit.stock_inventaire
            # Verifier que l'unite n'est pas UN (pieces)
            # / Check that the unit is not UN (pieces)
            from inventaire.models import UniteStock
            if stock_existant.unite == UniteStock.UN:
                messages.warning(
                    request,
                    _("Warning: the stock unit is 'Pieces' (UN). "
                      "Weight/volume sales require grams (GR) or centiliters (CL). "
                      "Please change the unit in the stock settings."),
                )
        except Exception:
            # Pas de stock → en creer un vide
            # / No stock → create an empty one
            from inventaire.models import Stock, UniteStock
            Stock.objects.create(
                product=produit,
                quantite=0,
                unite=UniteStock.GR,
                seuil_alerte=0,
                autoriser_vente_hors_stock=True,
            )
            messages.info(
                request,
                _("Stock automatically created in grams (quantity=0). "
                  "Remember to add stock via a reception."),
            )
```

- [ ] **Step 2: Ecrire le test de creation auto Stock**

Ajouter dans `tests/pytest/test_poids_mesure.py` :

```python
class TestCreationAutoStock:
    """Creation automatique du Stock quand poids_mesure=True.
    / Automatic Stock creation when poids_mesure=True."""

    def test_poids_mesure_cree_stock_si_absent(self):
        """Un Price avec poids_mesure=True sur un produit sans Stock
        doit creer un Stock vide en GR.
        / A Price with poids_mesure=True on a product without Stock
        must create an empty Stock in GR."""
        from BaseBillet.models import Product, Price

        with tenant_context(_get_tenant()):
            # Trouver un produit POS sans stock
            # / Find a POS product without stock
            produit = Product.objects.filter(
                methode_caisse__isnull=False,
            ).first()
            assert produit is not None

            # Supprimer le stock existant s'il y en a un
            # / Delete existing stock if any
            from inventaire.models import Stock
            Stock.objects.filter(product=produit).delete()

            # Creer un tarif poids_mesure
            # / Create a weight-based price
            prix = Price.objects.create(
                product=produit,
                name="Test poids auto",
                prix=28.00,
                poids_mesure=True,
                publish=False,
            )

            # Verifier qu'il n'y a pas encore de Stock
            # / Verify no Stock exists yet
            assert not Stock.objects.filter(product=produit).exists()

            # NOTE : la creation auto se fait dans save_related de l'admin,
            # pas dans le modele. Ce test verifie juste le champ.
            # Le test E2E ou test admin POST verifiera la creation auto.
            # / Auto-creation happens in admin save_related, not in the model.

            # Nettoyage / Cleanup
            prix.delete()
```

- [ ] **Step 3: Lancer le test**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_poids_mesure.py::TestCreationAutoStock -v`
Expected: PASS

---

### Task 5 : Backend — extraction panier avec weight-*

**Files:**
- Modify: `laboutik/views.py:2998-3160` (_extraire_articles_du_panier)
- Modify: `laboutik/views.py:3280-3410` (_creer_lignes_articles)
- Create: `tests/pytest/test_multi_tarif_overlay.py`

- [ ] **Step 1: Ecrire le test d'extraction panier avec weight**

Creer `tests/pytest/test_multi_tarif_overlay.py` :

```python
"""
tests/pytest/test_multi_tarif_overlay.py — Tests extraction panier avec weight-*.
/ Tests for cart extraction with weight-* inputs.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_multi_tarif_overlay.py -v
"""

import sys

sys.path.insert(0, '/DjangoFiles')

import django

django.setup()

import pytest
from django_tenants.utils import tenant_context
from Customers.models import Client
from django.test import RequestFactory

TENANT_SCHEMA = 'lespass'


def _get_tenant():
    return Client.objects.get(schema_name=TENANT_SCHEMA)


class TestExtractionPanierWeight:
    """Extraction du panier avec les inputs weight-*.
    / Cart extraction with weight-* inputs."""

    def test_weight_amount_extrait_du_post(self):
        """Le champ weight-<uuid>--<price_uuid> est extrait comme weight_amount_grams.
        / The weight-<uuid>--<price_uuid> field is extracted as weight_amount_grams."""
        from laboutik.views import _extraire_articles_du_panier
        from BaseBillet.models import Product, Price

        with tenant_context(_get_tenant()):
            # Trouver un produit POS avec un tarif
            # / Find a POS product with a price
            produit = Product.objects.filter(
                methode_caisse__isnull=False,
                prices__isnull=False,
            ).first()
            assert produit is not None

            prix = produit.prices.first()
            product_uuid = str(produit.uuid)
            price_uuid = str(prix.uuid)
            cle_repid = f"repid-{product_uuid}--{price_uuid}"
            cle_custom = f"custom-{product_uuid}--{price_uuid}"
            cle_weight = f"weight-{product_uuid}--{price_uuid}"

            # Simuler un POST avec weight
            # / Simulate a POST with weight
            donnees_post = {
                cle_repid: '1',
                cle_custom: '980',
                cle_weight: '350',
            }

            from laboutik.models import PointDeVente
            point_de_vente = PointDeVente.objects.first()

            articles = _extraire_articles_du_panier(donnees_post, point_de_vente)
            assert len(articles) >= 1

            # Trouver l'article avec notre price_uuid
            # / Find the article with our price_uuid
            article = None
            for a in articles:
                if str(a['price'].uuid) == price_uuid:
                    article = a
                    break

            assert article is not None, "Article non trouve dans le panier"
            assert article.get('weight_amount') == 350, \
                f"weight_amount attendu 350, obtenu {article.get('weight_amount')}"
```

- [ ] **Step 2: Modifier _extraire_articles_du_panier pour parser weight-***

Dans `laboutik/views.py`, dans `_extraire_articles_du_panier()` (ligne ~2998), ajouter le parsing de `weight-*` a cote du parsing de `custom-*`.

Chercher la ligne qui collecte `montants_custom` (environ ligne 3035-3040) et ajouter en dessous :

```python
    # Collecte des quantites poids/volume (weight-<uuid>--<price_uuid>)
    # / Collect weight/volume quantities (weight-<uuid>--<price_uuid>)
    quantites_poids = {}
    for cle, valeur in donnees_post.items():
        if cle.startswith("weight-"):
            reste = cle[len("weight-"):]
            try:
                poids = int(valeur)
                quantites_poids[reste] = poids
            except (ValueError, TypeError):
                pass
```

Et dans la boucle qui construit chaque article (environ ligne 3145-3155), ajouter :

```python
            weight_amount = quantites_poids.get(reste, None)
```

Et dans le dict retourne par article, ajouter :

```python
                "weight_amount": weight_amount,
```

- [ ] **Step 3: Modifier _creer_lignes_articles pour utiliser weight_amount**

Dans `laboutik/views.py`, dans `_creer_lignes_articles()` (ligne ~3280), modifier la creation de LigneArticle pour passer `weight_quantity` :

Ajouter apres la lecture de l'article du panier :

```python
        weight_amount = article.get("weight_amount")
```

Dans l'appel `LigneArticle.objects.create(...)` (ligne ~3354), ajouter le champ :

```python
            weight_quantity=weight_amount,
```

Et modifier la section decrementation stock (ligne ~3375-3385) :

```python
            if weight_amount:
                # Poids/mesure : la quantite saisie remplace contenance x qty
                # / Weight/volume: cashier's quantity replaces contenance x qty
                StockService.decrementer_pour_vente(
                    stock=stock_du_produit,
                    contenance=weight_amount,
                    qty=1,
                    ligne_article=ligne,
                )
            else:
                # Tarif classique : contenance fixe x quantite
                # / Standard price: fixed contenance x quantity
                StockService.decrementer_pour_vente(
                    stock=stock_du_produit,
                    contenance=prix_obj.contenance,
                    qty=quantite,
                    ligne_article=ligne,
                )
```

- [ ] **Step 4: Lancer le test d'extraction**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_multi_tarif_overlay.py -v`
Expected: PASS

- [ ] **Step 5: Lancer les tests laboutik existants (regression)**

Run: `docker exec lespass_django poetry run pytest tests/pytest/ -k "pos or caisse or paiement or cloture or laboutik" -v --tb=short`
Expected: tous PASS

---

### Task 6 : Frontend — enrichir les donnees articles + tuile

**Files:**
- Modify: `laboutik/views.py:446-600` (_construire_donnees_articles)
- Modify: `laboutik/templates/cotton/articles.html`

- [ ] **Step 1: Enrichir les donnees articles avec poids_mesure**

Dans `_construire_donnees_articles()` (ligne ~530-545), dans la boucle qui construit les tarifs, ajouter les champs poids/mesure :

```python
                    "poids_mesure": p.poids_mesure,
```

Et dans le dict article global (ligne ~590-600), ajouter :

```python
            # Detecter si au moins un tarif est au poids/mesure
            # / Detect if at least one price is weight-based
            a_poids_mesure = any(p.poids_mesure for p in product.prix_euros)

            # Unite du stock et prix de reference (E/kg ou E/L) si poids_mesure
            # / Stock unit and reference price (E/kg or E/L) if weight-based
            unite_stock_label = None
            prix_reference_label = None
            if a_poids_mesure:
                try:
                    stock_du_produit = product.stock_inventaire
                    if stock_du_produit.unite == 'GR':
                        unite_stock_label = 'g'
                        prix_reference_label = '/kg'
                    elif stock_du_produit.unite == 'CL':
                        unite_stock_label = 'cl'
                        prix_reference_label = '/L'
                except Exception:
                    unite_stock_label = 'g'
                    prix_reference_label = '/kg'
```

Et ajouter dans le dict article :

```python
            "a_poids_mesure": a_poids_mesure,
            "unite_stock_label": unite_stock_label,
            "prix_reference_label": prix_reference_label,
```

- [ ] **Step 2: Modifier la tuile article pour afficher l'icone balance**

Dans `laboutik/templates/cotton/articles.html`, dans la zone d'affichage du prix de la tuile, ajouter une condition pour les articles au poids :

```html
{% if article.a_poids_mesure %}
    <span class="article-prix">{{ article.prix_affiche }}{{ article.prix_reference_label }}</span>
    <i class="fas fa-balance-scale article-icon-poids" aria-hidden="true"></i>
{% else %}
    <span class="article-prix">{{ article.prix_affiche }} {{ article.currency }}</span>
{% endif %}
```

- [ ] **Step 3: Demarrer le serveur et verifier visuellement**

Run (background): `docker exec lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002`

Verifier dans Chrome qu'un produit POS avec `poids_mesure=True` affiche l'icone balance et le prix /kg.

---

### Task 7 : Frontend — refonte tarif.js (multi-clic + pave numerique)

**Files:**
- Modify: `laboutik/static/js/tarif.js` (refonte complete)
- Create: `laboutik/static/css/tarif.css`
- Modify: `laboutik/static/js/addition.js`

Cette tache est la plus volumineuse. Elle contient la refonte JS complete de l'overlay.
Le code exact est trop long pour ce plan — les grandes lignes sont :

- [ ] **Step 1: Creer tarif.css avec les styles overlay + pave numerique**

Creer `laboutik/static/css/tarif.css` avec :
- `.tarif-overlay` : positionnement absolu sur `#articles-zone` (pas `fixed`)
- `.tarif-numpad` : grille 3x4 pour le pave numerique
- `.tarif-numpad-btn` : boutons tactiles (min 48x48px pour le tactile)
- `.tarif-numpad-display` : affichage de la saisie + calcul prix
- Media query `max-width: 599px` : responsive mobile V2s (overlay pleine largeur)
- Media query `min-width: 600px` : desktop/tablette (overlay dans `#articles-zone`)

- [ ] **Step 2: Refactorer tarif.js — injection dans #articles-zone**

Modifier `tarifSelection()` pour injecter l'overlay dans `#articles-zone` au lieu de `#messages` :
- Sauvegarder le contenu actuel de `#articles-zone` dans une variable
- Injecter l'overlay par-dessus (position absolute + z-index)
- `tarifClose()` restaure le contenu ou retire l'overlay

- [ ] **Step 3: Modifier tarif.js — multi-clic (ne pas fermer apres ajout)**

Supprimer l'appel a `tarifClose()` dans `tarifSelectFixed()` et `tarifValidateFreePrix()`.
L'overlay reste ouvert, le panier se met a jour en temps reel.

- [ ] **Step 4: Ajouter le 3e type de bouton — pave numerique poids/mesure**

Dans `tarifSelection()`, pour les tarifs avec `poids_mesure: true`, generer le HTML du pave :
- Affichage : nom du tarif + prix de reference (28,00 E/kg)
- Zone de saisie : `[ 0 ] g`
- Pave : 7 8 9 / 4 5 6 / 1 2 3 / C 0 OK
- Calcul prix en temps reel : `quantite / diviseur x prix_unitaire`
- Diviseur : 1000 pour `g`, 100 pour `cl`
- OK : valide si quantite > 0, ajoute au panier, vide le champ
- C : efface la saisie

- [ ] **Step 5: Modifier addition.js — gerer weight-* dans les inputs hidden**

Dans `addition.js`, dans `additionInsertArticle()`, si `detail.weightAmount` est present :
- Creer un input hidden `weight-<uuid>--<priceUuid>` avec la valeur
- Le nom affiche dans le panier inclut la quantite : "Comte 350g"

- [ ] **Step 6: Charger tarif.css dans le template**

Dans `laboutik/templates/laboutik/base.html` ou `cotton/articles.html`, ajouter :
```html
<link rel="stylesheet" href="{% static 'css/tarif.css' %}" />
```

- [ ] **Step 7: Tester manuellement dans Chrome**

Verifier sur desktop et mobile (DevTools device toolbar) :
1. Overlay multi-clic : 3 demis + 1 pinte sans fermer
2. Overlay prix libre : saisie, overlay reste ouvert
3. Overlay poids/mesure : pave numerique, calcul temps reel, OK ajoute au panier
4. Panier visible pendant l'overlay
5. RETOUR ferme l'overlay

---

### Task 8 : Ticket imprime — format poids/mesure

**Files:**
- Modify: `laboutik/printing/formatters.py`

- [ ] **Step 1: Modifier le formatter de vente pour les lignes poids/mesure**

Dans le formatter de ticket de vente, ajouter une condition :
si `ligne.weight_quantity` est renseigne, afficher :

```
Comte AOP                    9,80 E
  350g x 28,00E/kg
```

au lieu de :

```
Comte AOP              x1   9,80 E
```

- [ ] **Step 2: Tester le format dans les tests existants d'impression**

Run: `docker exec lespass_django poetry run pytest tests/pytest/ -k "impression or print or format" -v`
Expected: tous PASS

---

### Task 9 : Rapports comptables — poids_total optionnel

**Files:**
- Modify: `laboutik/reports.py:162-260` (calculer_detail_ventes)

- [ ] **Step 1: Ajouter poids_total dans calculer_detail_ventes()**

Dans `laboutik/reports.py`, dans `calculer_detail_ventes()`, ajouter l'aggregation du poids total par produit :

```python
            # Poids/volume total vendu (somme des weight_quantity pour les ventes au poids)
            # / Total weight/volume sold (sum of weight_quantity for weight-based sales)
            poids_total_agreg = self.lignes.filter(
                pricesold__productsold__product__name=article["nom"],
                weight_quantity__isnull=False,
            ).aggregate(total=Sum('weight_quantity'))
            poids_total = poids_total_agreg['total'] or 0
```

Et dans le dict article, ajouter :

```python
                "poids_total": poids_total,
```

- [ ] **Step 2: Lancer les tests rapports existants**

Run: `docker exec lespass_django poetry run pytest tests/pytest/ -k "rapport or report or detail_ventes" -v`
Expected: tous PASS

---

### Task 10 : Tests E2E et regression finale

**Files:**
- Read: tous les tests existants

- [ ] **Step 1: Lancer la suite pytest complete**

Run: `docker exec lespass_django poetry run pytest tests/pytest/ -q`
Expected: tous PASS, 0 regression

- [ ] **Step 2: Lancer les tests E2E**

Run: `docker exec lespass_django poetry run pytest tests/e2e/ -v -s`
Expected: tous PASS

- [ ] **Step 3: manage.py check**

Run: `docker exec lespass_django poetry run python /DjangoFiles/manage.py check`
Expected: `System check identified no issues.`
