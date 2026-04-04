# PriceInline Refactoring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le PriceInline unique (TabularInline) par 4 StackedInline collapsibles specifiques a chaque type de produit, sans migration.

**Architecture:** 4 classes StackedInline heritant d'une base commune (BasePriceInline), chacune avec ses fields en dur et son formulaire dedie. Pattern natif Unfold `collapsible = True`. Un seul fichier modifie : `Administration/admin/products.py`.

**Tech Stack:** Django admin, django-unfold (StackedInline, collapsible), django-tenants

**Spec:** `TECH DOC/Laboutik sessions/Session 04 - PriceInline refactoring/DESIGN_PRICEINLINE_REFACTORING.md`

---

## File Map

| Fichier | Action |
|---------|--------|
| `Administration/admin/products.py` | Modifier : supprimer PriceInlineChangeForm + PriceInline, creer 4 nouveaux inlines + 2 forms, brancher dans les 4 *Admin |
| `tests/pytest/test_price_inline_refactoring.py` | Creer : 8 tests (smoke + validation + soumission) |

---

### Task 1 : Ecrire les tests smoke pour les 4 change pages

**Files:**
- Create: `tests/pytest/test_price_inline_refactoring.py`

- [ ] **Step 1: Creer le fichier de tests avec les 4 smoke tests**

```python
"""
tests/pytest/test_price_inline_refactoring.py — Tests PriceInline StackedInline par proxy.
/ Tests for proxy-specific StackedInline PriceInlines.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_price_inline_refactoring.py -v
"""

import os
import sys

sys.path.insert(0, '/DjangoFiles')

import django

django.setup()

import pytest

from django_tenants.utils import schema_context

from BaseBillet.models import Product, TicketProduct, MembershipProduct, POSProduct, Price

TENANT_SCHEMA = 'lespass'


class TestPriceInlineSmoke:
    """Smoke tests : les 4 change pages admin chargent avec le formset Price.
    / Smoke tests: all 4 admin change pages load with the Price formset."""

    def test_product_change_page_has_price_formset(self, admin_client):
        """ProductAdmin change page contient le formset prices.
        / ProductAdmin change page contains prices formset."""
        with schema_context(TENANT_SCHEMA):
            product = Product.objects.exclude(
                categorie_article__in=[Product.RECHARGE_CASHLESS, Product.DON]
            ).first()
            assert product is not None, "Aucun Product en base"
            resp = admin_client.get(f'/admin/BaseBillet/product/{product.pk}/change/')
            assert resp.status_code == 200
            html = resp.content.decode()
            assert 'prices-TOTAL_FORMS' in html, "Formset prices absent"

    def test_ticketproduct_change_page_has_price_formset(self, admin_client):
        """TicketProductAdmin change page contient le formset prices.
        / TicketProductAdmin change page contains prices formset."""
        with schema_context(TENANT_SCHEMA):
            product = TicketProduct.objects.first()
            assert product is not None, "Aucun TicketProduct en base"
            resp = admin_client.get(f'/admin/BaseBillet/ticketproduct/{product.pk}/change/')
            assert resp.status_code == 200
            html = resp.content.decode()
            assert 'prices-TOTAL_FORMS' in html, "Formset prices absent"

    def test_membershipproduct_change_page_has_price_formset(self, admin_client):
        """MembershipProductAdmin change page contient le formset prices.
        / MembershipProductAdmin change page contains prices formset."""
        with schema_context(TENANT_SCHEMA):
            product = MembershipProduct.objects.first()
            assert product is not None, "Aucun MembershipProduct en base"
            resp = admin_client.get(f'/admin/BaseBillet/membershipproduct/{product.pk}/change/')
            assert resp.status_code == 200
            html = resp.content.decode()
            assert 'prices-TOTAL_FORMS' in html, "Formset prices absent"

    def test_posproduct_change_page_has_price_formset(self, admin_client):
        """POSProductAdmin change page contient le formset prices.
        / POSProductAdmin change page contains prices formset."""
        with schema_context(TENANT_SCHEMA):
            product = POSProduct.objects.first()
            assert product is not None, "Aucun POSProduct en base"
            resp = admin_client.get(f'/admin/BaseBillet/posproduct/{product.pk}/change/')
            assert resp.status_code == 200
            html = resp.content.decode()
            assert 'prices-TOTAL_FORMS' in html, "Formset prices absent"
```

- [ ] **Step 2: Lancer les tests pour verifier qu'ils passent AVANT le refactoring**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_price_inline_refactoring.py::TestPriceInlineSmoke -v`
Expected: 4 PASS (les pages chargent deja avec l'ancien PriceInline)

---

### Task 2 : Ecrire les tests de validation et soumission

**Files:**
- Modify: `tests/pytest/test_price_inline_refactoring.py`

- [ ] **Step 1: Ajouter les tests de validation et champs specifiques**

Ajouter a la fin du fichier `tests/pytest/test_price_inline_refactoring.py` :

```python
class TestPriceInlineFields:
    """Tests que chaque inline affiche les bons champs specifiques.
    / Tests that each inline shows the correct specific fields."""

    def test_ticket_inline_has_stock_field(self, admin_client):
        """TicketPriceInline affiche le champ stock.
        / TicketPriceInline displays the stock field."""
        with schema_context(TENANT_SCHEMA):
            product = TicketProduct.objects.first()
            assert product is not None
            resp = admin_client.get(f'/admin/BaseBillet/ticketproduct/{product.pk}/change/')
            html = resp.content.decode()
            # Le champ stock doit etre present dans le formset inline
            # / The stock field must be present in the inline formset
            assert 'id_prices-0-stock' in html or 'name="prices-0-stock"' in html, \
                "Champ stock absent de TicketPriceInline"

    def test_membership_inline_has_subscription_type_field(self, admin_client):
        """MembershipPriceInline affiche le champ subscription_type.
        / MembershipPriceInline displays the subscription_type field."""
        with schema_context(TENANT_SCHEMA):
            product = MembershipProduct.objects.first()
            assert product is not None
            resp = admin_client.get(f'/admin/BaseBillet/membershipproduct/{product.pk}/change/')
            html = resp.content.decode()
            assert 'id_prices-0-subscription_type' in html or 'name="prices-0-subscription_type"' in html, \
                "Champ subscription_type absent de MembershipPriceInline"

    def test_pos_inline_has_contenance_field(self, admin_client):
        """POSPriceInline affiche le champ contenance.
        / POSPriceInline displays the contenance field."""
        with schema_context(TENANT_SCHEMA):
            product = POSProduct.objects.first()
            assert product is not None
            resp = admin_client.get(f'/admin/BaseBillet/posproduct/{product.pk}/change/')
            html = resp.content.decode()
            assert 'id_prices-0-contenance' in html or 'name="prices-0-contenance"' in html, \
                "Champ contenance absent de POSPriceInline"

    def test_base_inline_does_not_have_contenance(self, admin_client):
        """BasePriceInline (ProductAdmin) n'affiche PAS contenance.
        / BasePriceInline (ProductAdmin) does NOT display contenance."""
        with schema_context(TENANT_SCHEMA):
            # Prendre un produit qui N'est PAS un POSProduct (pas de methode_caisse)
            # / Take a product that is NOT a POSProduct (no methode_caisse)
            product = Product.objects.filter(
                categorie_article__in=[Product.BILLET, Product.ADHESION],
            ).first()
            assert product is not None
            resp = admin_client.get(f'/admin/BaseBillet/product/{product.pk}/change/')
            html = resp.content.decode()
            # contenance ne doit PAS etre dans le formset pour un produit non-POS
            # / contenance must NOT be in the formset for a non-POS product
            assert 'name="prices-0-contenance"' not in html, \
                "Champ contenance ne devrait pas etre dans BasePriceInline"
```

- [ ] **Step 2: Lancer les tests de champs — certains doivent echouer AVANT le refactoring**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_price_inline_refactoring.py::TestPriceInlineFields -v`
Expected:
- `test_ticket_inline_has_stock_field` : FAIL (stock pas dans l'ancien PriceInline)
- `test_membership_inline_has_subscription_type_field` : PASS (subscription_type est deja dans l'ancien inline)
- `test_pos_inline_has_contenance_field` : depend (contenance est conditionnel dans l'ancien)
- `test_base_inline_does_not_have_contenance` : PASS

---

### Task 3 : Creer BasePriceInlineForm et MembershipPriceInlineForm

**Files:**
- Modify: `Administration/admin/products.py:292-324` (remplacer PriceInlineChangeForm)

- [ ] **Step 1: Remplacer PriceInlineChangeForm par les 2 nouveaux formulaires**

Dans `Administration/admin/products.py`, remplacer les lignes 292-324 (classe `PriceInlineChangeForm`) par :

```python
class BasePriceInlineForm(ModelForm):
    """Formulaire de base pour les tarifs inline (StackedInline).
    Validation commune : prix entre 0 et 1 EUR interdit.
    / Base form for inline prices (StackedInline).
    Common validation: price between 0 and 1 EUR forbidden."""

    class Meta:
        model = Price
        fields = "__all__"

    def clean_prix(self):
        prix = self.cleaned_data.get("prix")
        if 0 < prix < 1:
            raise forms.ValidationError(
                _("A rate cannot be between 0€ and 1€"), code="invalid"
            )
        return prix


class MembershipPriceInlineForm(BasePriceInlineForm):
    """Formulaire inline specifique aux tarifs adhesion.
    Ajoute la validation : duree obligatoire + coherence paiement recurrent.
    / Inline form specific to membership prices.
    Adds validation: duration required + recurring payment coherence."""

    def clean_subscription_type(self):
        product = self.cleaned_data.get("product")
        subscription_type = self.cleaned_data.get("subscription_type")
        if product and product.categorie_article == Product.ADHESION:
            if subscription_type == Price.NA:
                raise forms.ValidationError(
                    _("A subscription must have a duration"), code="invalid"
                )
        return subscription_type

    def clean_recurring_payment(self):
        recurring_payment = self.cleaned_data.get("recurring_payment")
        if not recurring_payment:
            return recurring_payment

        # Verifier que le produit est bien une adhesion
        # / Verify the product is indeed a membership
        if hasattr(self.instance, "product"):
            categorie_product = self.instance.product.categorie_article
        elif self.cleaned_data.get("product"):
            categorie_product = self.cleaned_data["product"].categorie_article
        else:
            raise forms.ValidationError(_("No product ?"), code="invalid")

        if categorie_product and categorie_product != Product.ADHESION:
            raise forms.ValidationError(
                _("A recurring payment plan must have a membership-type product."),
                code="invalid",
            )

        # Verifier que subscription_type est defini
        # / Verify subscription_type is set
        if self.data.get("subscription_type") not in [
            Price.DAY,
            Price.WEEK,
            Price.MONTH,
            Price.CAL_MONTH,
            Price.YEAR,
        ]:
            raise forms.ValidationError(
                _("A recurring payment must have a membership term. Re-enter the term just above."),
                code="invalid",
            )

        return recurring_payment
```

- [ ] **Step 2: Verifier que le fichier est syntaxiquement correct**

Run: `docker exec lespass_django python -c "import Administration.admin.products; print('OK')"`
Expected: `OK`

---

### Task 4 : Creer les 4 StackedInline

**Files:**
- Modify: `Administration/admin/products.py:327-357` (remplacer PriceInline)

- [ ] **Step 1: Ajouter l'import StackedInline**

Dans `Administration/admin/products.py`, ligne 15, modifier l'import Unfold :

Remplacer :
```python
from unfold.admin import ModelAdmin, TabularInline
```
Par :
```python
from unfold.admin import ModelAdmin, StackedInline, TabularInline
```

- [ ] **Step 2: Remplacer PriceInline par les 4 nouveaux inlines**

Remplacer les lignes 327-357 (classe `PriceInline` + ses methodes) par :

```python
class BasePriceInline(StackedInline):
    """Inline de base pour les tarifs (StackedInline collapsible Unfold).
    Champs communs a tous les types de produit.
    / Base inline for prices (Unfold collapsible StackedInline).
    Common fields for all product types."""

    model = Price
    fk_name = "product"
    form = BasePriceInlineForm
    collapsible = True
    extra = 0
    show_change_link = True
    fields = ("name", "prix", "free_price", "publish", "order")

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_change_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)

    def has_view_permission(self, request, obj=None):
        return TenantAdminPermissionWithRequest(request)


class TicketPriceInline(BasePriceInline):
    """Inline tarifs pour les produits billetterie.
    Ajoute stock (jauge) et max_per_user.
    / Price inline for ticket products.
    Adds stock (capacity) and max_per_user."""

    fields = ("name", "prix", "free_price", "stock", "max_per_user", "publish", "order")


class MembershipPriceInline(BasePriceInline):
    """Inline tarifs pour les produits adhesion.
    Ajoute les champs abonnement : duree, recurrence, engagement, adhesions obligatoires.
    / Price inline for membership products.
    Adds subscription fields: duration, recurrence, commitment, required memberships."""

    form = MembershipPriceInlineForm
    autocomplete_fields = ["adhesions_obligatoires"]
    fields = (
        "name",
        "prix",
        "free_price",
        "subscription_type",
        "recurring_payment",
        "iteration",
        "commitment",
        "adhesions_obligatoires",
        "publish",
        "order",
    )


class POSPriceInline(BasePriceInline):
    """Inline tarifs pour les produits de caisse (POS).
    Ajoute contenance (volume par vente).
    / Price inline for POS products.
    Adds contenance (volume per sale)."""

    fields = ("name", "prix", "free_price", "contenance", "publish", "order")
```

- [ ] **Step 3: Verifier la syntaxe**

Run: `docker exec lespass_django python -c "import Administration.admin.products; print('OK')"`
Expected: `OK`

---

### Task 5 : Brancher les inlines dans les 4 *Admin

**Files:**
- Modify: `Administration/admin/products.py` (4 endroits)

- [ ] **Step 1: ProductAdmin — remplacer PriceInline par BasePriceInline**

Ligne ~639 dans ProductAdmin :

Remplacer :
```python
    inlines = [PriceInline, ProductFormFieldInline]
```
Par :
```python
    inlines = [BasePriceInline, ProductFormFieldInline]
```

- [ ] **Step 2: TicketProductAdmin — remplacer PriceInline par TicketPriceInline**

Ligne ~998 dans TicketProductAdmin :

Remplacer :
```python
    inlines = [
        PriceInline
    ]  # Pas de ProductFormFieldInline (champs dynamiques = adhesions)
```
Par :
```python
    inlines = [TicketPriceInline]
```

- [ ] **Step 3: MembershipProductAdmin — remplacer PriceInline par MembershipPriceInline**

Ligne ~1015 dans MembershipProductAdmin :

Remplacer :
```python
    inlines = [PriceInline, ProductFormFieldInline]
```
Par :
```python
    inlines = [MembershipPriceInline, ProductFormFieldInline]
```

- [ ] **Step 4: POSProductAdmin — remplacer PriceInline par POSPriceInline dans inlines ET get_inlines**

Ligne ~1176 dans POSProductAdmin :

Remplacer :
```python
    inlines = [PriceInline]
```
Par :
```python
    inlines = [POSPriceInline]
```

Et dans `get_inlines()` (ligne ~1233) :

Remplacer :
```python
    def get_inlines(self, request, obj):
        if obj is None:
            from Administration.admin.inventaire import StockInline

            return [StockInline, PriceInline]
        return [PriceInline]
```
Par :
```python
    def get_inlines(self, request, obj):
        if obj is None:
            from Administration.admin.inventaire import StockInline

            return [StockInline, POSPriceInline]
        return [POSPriceInline]
```

- [ ] **Step 5: Verifier la syntaxe et que plus aucune reference a PriceInline n'existe**

Run: `docker exec lespass_django python -c "import Administration.admin.products; print('OK')" && grep -n 'PriceInline[^F]' /DjangoFiles/Administration/admin/products.py | grep -v 'BasePriceInline\|TicketPriceInline\|MembershipPriceInline\|POSPriceInline\|class.*Inline'`
Expected: `OK` et aucune ligne en sortie du grep (plus de reference a l'ancien PriceInline)

---

### Task 6 : Lancer les tests existants + nouveaux tests

**Files:**
- Read: `tests/pytest/test_price_inline_refactoring.py`
- Read: `tests/pytest/test_admin_proxy_products.py`

- [ ] **Step 1: Lancer les smoke tests (doivent passer)**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_price_inline_refactoring.py::TestPriceInlineSmoke -v`
Expected: 4 PASS

- [ ] **Step 2: Lancer les tests de champs specifiques (doivent passer maintenant)**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_price_inline_refactoring.py::TestPriceInlineFields -v`
Expected: 4 PASS

- [ ] **Step 3: Lancer les tests proxy existants (regression)**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_admin_proxy_products.py -v`
Expected: 6 PASS (aucune regression)

- [ ] **Step 4: Lancer les tests de duplication (regression)**

Run: `docker exec lespass_django poetry run pytest tests/pytest/test_product_duplication.py -v`
Expected: PASS

- [ ] **Step 5: Lancer manage.py check**

Run: `docker exec lespass_django poetry run python /DjangoFiles/manage.py check`
Expected: `System check identified no issues.`

---

### Task 7 : Verification visuelle dans le navigateur

**Files:** aucun

- [ ] **Step 1: Demarrer le serveur de dev**

Run (background): `docker exec lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002`

- [ ] **Step 2: Verifier visuellement les 4 pages admin**

Ouvrir dans Chrome et verifier que les inlines StackedInline sont bien collapsibles :

1. `https://lespass.tibillet.localhost/admin/BaseBillet/product/<uuid>/change/` — BasePriceInline
2. `https://lespass.tibillet.localhost/admin/BaseBillet/ticketproduct/<uuid>/change/` — TicketPriceInline avec stock
3. `https://lespass.tibillet.localhost/admin/BaseBillet/membershipproduct/<uuid>/change/` — MembershipPriceInline avec subscription_type
4. `https://lespass.tibillet.localhost/admin/BaseBillet/posproduct/<uuid>/change/` — POSPriceInline avec contenance

Verifier pour chaque page :
- Les tarifs existants apparaissent en lignes repliees
- Le clic sur un tarif deplie le formulaire complet
- Les champs specifiques sont presents
- Le bouton "Add another Price" fonctionne
