# Stock Actions Admin — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Formulaire d'actions stock (réception, ajustement, offert, perte) sur la fiche Stock dans l'admin Unfold, avec ViewSet HTMX, template before aide sur MouvementStockAdmin, et documentation technique+utilisateur.

**Architecture:** Un `change_form_after_template` sur `StockAdmin` affiche un formulaire unique (quantité + motif + 4 boutons colorés). Chaque bouton fait un `hx-post` vers `StockActionViewSet` qui appelle `StockService`. Le partial HTMX retourné remplace le formulaire avec feedback + formulaire rechargé. L'ajustement stock existant sur POSProduct est déplacé ici.

**Tech Stack:** Django Unfold admin, HTMX (hx-post/hx-target), DRF ViewSet + Serializer, inline styles (contrainte Unfold)

---

## Vue d'ensemble des fichiers

| Fichier | Action | Responsabilité |
|---------|--------|----------------|
| `Administration/admin/inventaire.py` | Modifier | `StockAdmin.change_form_after_template` + `changeform_view` contexte + `MouvementStockAdmin.list_before_template` |
| `Administration/admin/products.py` | Modifier | Retirer `StockInline` + ajustement stock du changeform POSProduct |
| `Administration/templates/admin/inventaire/stock_actions.html` | Créer | Template after : formulaire 4 boutons + aide + aperçu mouvements |
| `Administration/templates/admin/inventaire/stock_actions_partial.html` | Créer | Partial HTMX renvoyé après action |
| `Administration/templates/admin/inventaire/mouvements_list_before.html` | Créer | Template before aide sur le filtre mouvements |
| `inventaire/views.py` | Modifier | Ajouter `StockActionViewSet` |
| `inventaire/urls.py` | Modifier | Route pour `StockActionViewSet` |
| `tests/pytest/test_stock_actions_admin.py` | Créer | Tests du ViewSet |
| `TECH DOC/A DOCUMENTER/inventaire-actions-stock.md` | Créer | Doc technique + utilisateur |

---

## Task 1 : StockActionViewSet + serializer + route

**Files:**
- Modify: `inventaire/views.py`
- Modify: `inventaire/urls.py`
- Test: `tests/pytest/test_stock_actions_admin.py`

### Contexte

`inventaire/views.py` a déjà `StockViewSet` (API POS) et `DebitMetreViewSet`. On ajoute `StockActionViewSet` — un ViewSet HTMX qui rend du HTML (pas du JSON). Il réutilise le `MouvementRapideSerializer` existant pour RE/OF/PE et `AjustementSerializer` pour AJ.

La permission : on vérifie que l'utilisateur est admin tenant (même logique que `TenantAdminPermissionWithRequest` mais pour DRF). On peut utiliser `IsAdminUser` de DRF puisque l'utilisateur est déjà connecté à l'admin.

La route sera sous l'admin : `/admin/inventaire/stock/<uuid:stock_uuid>/action/`. On l'enregistre via `StockAdmin.get_urls()` (pas via le router DRF) pour rester dans le namespace admin et bénéficier de `admin_view()`.

### Steps

- [ ] **Step 1 : Écrire le test**

Créer `tests/pytest/test_stock_actions_admin.py` :

```python
"""
Tests pour StockActionViewSet — actions manuelles de stock depuis l'admin.
/ Tests for StockActionViewSet — manual stock actions from admin.

LOCALISATION : tests/pytest/test_stock_actions_admin.py

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_stock_actions_admin.py -v
"""

import sys
sys.path.insert(0, "/DjangoFiles")

import django
django.setup()

import pytest
from django.test import RequestFactory
from django_tenants.test.cases import FastTenantTestCase

from BaseBillet.models import Product, Price
from inventaire.models import Stock, MouvementStock, TypeMouvement


class TestStockActionView(FastTenantTestCase):
    """
    Teste les 4 actions manuelles de stock depuis l'admin.
    / Tests the 4 manual stock actions from admin.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.schema_name = "test_stock_actions"
        tenant.name = "Test Stock Actions"

    def setUp(self):
        self.product = Product.objects.create(
            name="Biere test action",
            categorie_article=Product.VENTE,
            methode_caisse="VT",
            publish=True,
        )
        Price.objects.create(
            product=self.product,
            name="Pinte",
            prix=5.00,
            publish=True,
        )
        self.stock = Stock.objects.create(
            product=self.product,
            quantite=20,
            unite="UN",
            seuil_alerte=5,
        )

    def test_reception_augmente_le_stock(self):
        """Réception +10 → stock passe de 20 à 30."""
        from inventaire.views import stock_action_view
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin_user = User.objects.create_superuser(
            email="admin_reception@test.com", password="test"
        )

        factory = RequestFactory()
        request = factory.post("", {
            "type_mouvement": "RE",
            "quantite": "10",
            "motif": "Livraison Metro",
        })
        request.user = admin_user

        response = stock_action_view(request, str(self.stock.pk))
        assert response.status_code == 200

        self.stock.refresh_from_db()
        assert self.stock.quantite == 30

        dernier_mouvement = MouvementStock.objects.filter(
            stock=self.stock
        ).order_by("-cree_le").first()
        assert dernier_mouvement.type_mouvement == TypeMouvement.RE
        assert dernier_mouvement.quantite == 10

    def test_ajustement_remplace_le_stock(self):
        """Ajustement stock_reel=15 → stock passe de 20 à 15 (delta -5)."""
        from inventaire.views import stock_action_view
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin_user = User.objects.create_superuser(
            email="admin_ajust@test.com", password="test"
        )

        factory = RequestFactory()
        request = factory.post("", {
            "type_mouvement": "AJ",
            "quantite": "15",
            "motif": "Inventaire physique",
        })
        request.user = admin_user

        response = stock_action_view(request, str(self.stock.pk))
        assert response.status_code == 200

        self.stock.refresh_from_db()
        assert self.stock.quantite == 15

    def test_perte_diminue_le_stock(self):
        """Perte 3 → stock passe de 20 à 17."""
        from inventaire.views import stock_action_view
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin_user = User.objects.create_superuser(
            email="admin_perte@test.com", password="test"
        )

        factory = RequestFactory()
        request = factory.post("", {
            "type_mouvement": "PE",
            "quantite": "3",
            "motif": "Casse",
        })
        request.user = admin_user

        response = stock_action_view(request, str(self.stock.pk))
        assert response.status_code == 200

        self.stock.refresh_from_db()
        assert self.stock.quantite == 17

    def test_offert_diminue_le_stock(self):
        """Offert 2 → stock passe de 20 à 18."""
        from inventaire.views import stock_action_view
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin_user = User.objects.create_superuser(
            email="admin_offert@test.com", password="test"
        )

        factory = RequestFactory()
        request = factory.post("", {
            "type_mouvement": "OF",
            "quantite": "2",
            "motif": "Degustation",
        })
        request.user = admin_user

        response = stock_action_view(request, str(self.stock.pk))
        assert response.status_code == 200

        self.stock.refresh_from_db()
        assert self.stock.quantite == 18

    def test_type_invalide_retourne_erreur(self):
        """Un type VE (vente auto) est refusé."""
        from inventaire.views import stock_action_view
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin_user = User.objects.create_superuser(
            email="admin_invalide@test.com", password="test"
        )

        factory = RequestFactory()
        request = factory.post("", {
            "type_mouvement": "VE",
            "quantite": "5",
        })
        request.user = admin_user

        response = stock_action_view(request, str(self.stock.pk))
        # La réponse contient le formulaire avec erreur (status 200 car c'est du HTML)
        assert response.status_code == 200
        # Le stock n'a pas changé
        self.stock.refresh_from_db()
        assert self.stock.quantite == 20
```

- [ ] **Step 2 : Lancer le test pour vérifier qu'il échoue**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_stock_actions_admin.py -v
```

Attendu : FAIL — `ImportError: cannot import name 'stock_action_view'`

- [ ] **Step 3 : Créer le serializer `StockActionSerializer`**

Ajouter dans `inventaire/serializers.py` :

```python
class StockActionSerializer(serializers.Serializer):
    """
    Validation pour les actions manuelles de stock depuis l'admin.
    Couvre les 4 types manuels : réception, ajustement, offert, perte.
    / Validation for manual stock actions from admin.
    Covers 4 manual types: reception, adjustment, offered, loss.

    LOCALISATION : inventaire/serializers.py
    """

    TYPES_MANUELS_CHOICES = [
        ("RE", _("Réception")),
        ("AJ", _("Ajustement")),
        ("OF", _("Offert")),
        ("PE", _("Perte/casse")),
    ]

    type_mouvement = serializers.ChoiceField(
        choices=TYPES_MANUELS_CHOICES,
        error_messages={
            "invalid_choice": _("Type de mouvement invalide."),
        },
    )
    quantite = serializers.IntegerField(
        min_value=0,
        error_messages={
            "min_value": _("La quantité doit être positive ou nulle."),
            "required": _("La quantité est requise."),
        },
    )
    motif = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
    )
```

- [ ] **Step 4 : Créer `stock_action_view` dans `inventaire/views.py`**

Ajouter à la fin de `inventaire/views.py` :

```python
from django.template.loader import render_to_string
from django.http import HttpResponse


def stock_action_view(request, stock_uuid):
    """
    Vue pour les actions manuelles de stock depuis l'admin.
    Reçoit un POST avec type_mouvement, quantite, motif.
    Retourne un partial HTML (feedback + formulaire rechargé).
    / View for manual stock actions from admin.
    Receives POST with type_mouvement, quantite, motif.
    Returns HTML partial (feedback + reloaded form).

    LOCALISATION : inventaire/views.py

    FLUX :
    1. Reçoit POST depuis stock_actions.html (bouton HTMX)
    2. Valide avec StockActionSerializer
    3. Dispatche vers StockService selon type_mouvement
    4. Relit le stock depuis la DB (refresh_from_db)
    5. Rend le partial stock_actions_partial.html
    """
    from inventaire.serializers import StockActionSerializer

    stock = get_object_or_404(Stock, pk=stock_uuid)

    serializer = StockActionSerializer(data=request.POST)

    message_feedback = None
    erreur_feedback = None

    if serializer.is_valid():
        type_mouvement = serializer.validated_data["type_mouvement"]
        quantite = serializer.validated_data["quantite"]
        motif = serializer.validated_data.get("motif", "")
        utilisateur = request.user if request.user.is_authenticated else None

        if type_mouvement == TypeMouvement.AJ:
            # Ajustement : quantite = stock réel compté
            # / Adjustment: quantite = real counted stock
            StockService.ajuster_inventaire(
                stock=stock,
                stock_reel=quantite,
                motif=motif,
                utilisateur=utilisateur,
            )
        else:
            # Réception, offert, perte
            # / Reception, offered, loss
            StockService.creer_mouvement(
                stock=stock,
                type_mouvement=type_mouvement,
                quantite=quantite,
                motif=motif,
                utilisateur=utilisateur,
            )

        stock.refresh_from_db()

        # Construire le message de feedback
        # / Build feedback message
        label_type = dict(StockActionSerializer.TYPES_MANUELS_CHOICES).get(
            type_mouvement, type_mouvement
        )
        from laboutik.views import _formater_stock_lisible
        stock_lisible = _formater_stock_lisible(stock.quantite, stock.unite)
        message_feedback = f"{label_type} effectuée. Stock actuel : {stock_lisible}"
    else:
        erreur_feedback = str(serializer.errors)
        stock.refresh_from_db()

    # Derniers mouvements pour l'aperçu
    # / Recent movements for preview
    derniers_mouvements = (
        MouvementStock.objects.filter(stock=stock)
        .select_related("cree_par")
        .order_by("-cree_le")[:5]
    )

    contexte = {
        "stock": stock,
        "product_name": stock.product.name,
        "derniers_mouvements": derniers_mouvements,
        "message_feedback": message_feedback,
        "erreur_feedback": erreur_feedback,
    }

    html = render_to_string(
        "admin/inventaire/stock_actions_partial.html",
        contexte,
        request=request,
    )
    return HttpResponse(html)
```

- [ ] **Step 5 : Ajouter la route dans `StockAdmin.get_urls()`**

Dans `Administration/admin/inventaire.py`, ajouter dans `StockAdmin` :

```python
    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/action/',
                self.admin_site.admin_view(self._stock_action_view),
                name='inventaire_stock_action',
            ),
        ]
        return custom_urls + urls

    def _stock_action_view(self, request, object_id):
        """Proxy vers stock_action_view (helper module-level interdit dans Unfold)."""
        from inventaire.views import stock_action_view
        return stock_action_view(request, object_id)
```

Note : `_stock_action_view` est une méthode de la classe car `get_urls` utilise `self.admin_site.admin_view()`. Mais le travail réel est dans `stock_action_view()` au niveau module dans `inventaire/views.py`.

- [ ] **Step 6 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_stock_actions_admin.py -v
```

Attendu : 5/5 PASS

- [ ] **Step 7 : Ruff + non-régression**

```bash
docker exec lespass_django poetry run ruff check --fix inventaire/views.py inventaire/serializers.py
docker exec lespass_django poetry run ruff format inventaire/views.py inventaire/serializers.py
docker exec lespass_django poetry run pytest tests/pytest/test_inventaire.py tests/pytest/test_stock_visuel_pos.py -v --tb=short
```

---

## Task 2 : Templates (stock_actions + partial + mouvements before)

**Files:**
- Create: `Administration/templates/admin/inventaire/stock_actions.html`
- Create: `Administration/templates/admin/inventaire/stock_actions_partial.html`
- Create: `Administration/templates/admin/inventaire/mouvements_list_before.html`

### Contexte

3 templates Unfold admin — tous en inline styles (pas de Tailwind custom). Utiliser `{% translate %}` pour tout texte visible. `{% csrf_token %}` obligatoire dans le formulaire.

### Steps

- [ ] **Step 1 : Créer `stock_actions.html`** (template after sur Stock changeform)

Créer `Administration/templates/admin/inventaire/stock_actions.html` :

```html
<!--
FORMULAIRE D'ACTIONS STOCK — 4 boutons : réception, ajustement, offert, perte
/ STOCK ACTIONS FORM — 4 buttons: reception, adjustment, offered, loss

LOCALISATION : Administration/templates/admin/inventaire/stock_actions.html

Affiché sous le formulaire Stock (change_form_after_template sur StockAdmin).
Chaque bouton envoie un hx-post vers StockAdmin._stock_action_view()
qui appelle StockService. Le partial stock_actions_partial.html est renvoyé
et remplace le contenu du conteneur #stock-actions-container.

CONTEXT :
- stock : instance Stock
- product_name : nom du produit
- derniers_mouvements : 5 derniers MouvementStock
- stock_action_url : URL du ViewSet action
-->
{% load i18n %}

{% if original %}
<div id="stock-actions-container"
     style="margin-top: 24px;"
     aria-live="polite"
     data-testid="stock-actions-container">
    {% include "admin/inventaire/stock_actions_partial.html" %}
</div>
{% endif %}
```

- [ ] **Step 2 : Créer `stock_actions_partial.html`** (partial HTMX)

Créer `Administration/templates/admin/inventaire/stock_actions_partial.html` :

```html
<!--
PARTIAL HTMX — formulaire d'actions stock + feedback
Renvoyé par stock_action_view() après chaque action.
/ HTMX partial — stock actions form + feedback.
Returned by stock_action_view() after each action.

LOCALISATION : Administration/templates/admin/inventaire/stock_actions_partial.html
-->
{% load i18n %}

<div style="padding: 20px; border: 1px solid var(--color-primary-200, #e5e7eb); border-radius: 10px; background: var(--color-base-0, #fff);">

    <h3 style="margin: 0 0 16px 0; font-size: 16px; font-weight: 600;">
        {% translate "Opérations de stock" %} — {{ product_name }}
    </h3>

    {% comment %}
    FEEDBACK — bandeau de succès ou d'erreur après une action
    / Feedback — success or error banner after an action
    {% endcomment %}
    {% if message_feedback %}
    <div style="padding: 10px 14px; margin-bottom: 16px; border-radius: 6px; background-color: #dcfce7; color: #166534; font-weight: 500;"
         data-testid="stock-action-success">
        {{ message_feedback }}
    </div>
    {% endif %}
    {% if erreur_feedback %}
    <div style="padding: 10px 14px; margin-bottom: 16px; border-radius: 6px; background-color: #fef2f2; color: #991b1b; font-weight: 500;"
         data-testid="stock-action-error">
        {{ erreur_feedback }}
    </div>
    {% endif %}

    {% comment %}
    AIDE — texte dépliable expliquant les 4 actions
    / HELP — collapsible text explaining the 4 actions
    {% endcomment %}
    <details style="margin-bottom: 16px;">
        <summary style="cursor: pointer; font-size: 13px; color: var(--color-base-500, #6b7280); user-select: none;">
            {% translate "Aide : comprendre les actions" %}
        </summary>
        <div style="margin-top: 8px; padding: 12px; background: var(--color-base-50, #f9fafb); border-radius: 6px; font-size: 13px; line-height: 1.6; color: var(--color-base-600, #4b5563);">
            <p style="margin: 0 0 8px 0;">
                <strong style="color: #16a34a;">{% translate "Réception" %}</strong> :
                {% translate "Ajoute du stock après une livraison. La quantité saisie est ajoutée au stock actuel." %}
            </p>
            <p style="margin: 0 0 8px 0;">
                <strong style="color: #d97706;">{% translate "Ajustement" %}</strong> :
                {% translate "Remplace la quantité actuelle par le stock réel compté lors d'un inventaire physique. Le système calcule le delta automatiquement." %}
            </p>
            <p style="margin: 0 0 8px 0;">
                <strong style="color: #2563eb;">{% translate "Offert" %}</strong> :
                {% translate "Retire du stock pour un produit offert. Attention : cette action n'apparaît PAS dans les ventes ni les rapports comptables. Pour offrir un produit avec traçabilité comptable, utilisez le bouton « Offrir » dans le POS." %}
            </p>
            <p style="margin: 0 0 4px 0;">
                <strong style="color: #dc2626;">{% translate "Perte/casse" %}</strong> :
                {% translate "Retire du stock pour un produit cassé, périmé ou perdu." %}
            </p>
            <p style="margin: 8px 0 0 0; font-style: italic;">
                {% translate "Chaque action est tracée dans le journal des mouvements de stock." %}
            </p>
        </div>
    </details>

    {% comment %}
    FORMULAIRE — quantité + motif + 4 boutons d'action
    Chaque bouton envoie un type_mouvement différent via hx-vals.
    / FORM — quantity + reason + 4 action buttons.
    Each button sends a different type_mouvement via hx-vals.
    {% endcomment %}
    <div style="display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap; margin-bottom: 16px;">
        <div>
            <label for="id_quantite_action" style="display: block; font-size: 13px; margin-bottom: 4px; font-weight: 500;">
                {% translate "Quantité" %}
            </label>
            <input type="number" name="quantite" id="id_quantite_action" required min="0"
                   form="stock-action-form"
                   style="padding: 8px 12px; border: 1px solid var(--color-base-300, #d1d5db); border-radius: 6px; width: 120px; font-size: 14px;"
                   data-testid="input-quantite-action">
        </div>

        <div style="flex: 1; min-width: 200px;">
            <label for="id_motif_action" style="display: block; font-size: 13px; margin-bottom: 4px; font-weight: 500;">
                {% translate "Motif" %} <span style="color: var(--color-base-400, #9ca3af);">({% translate "optionnel" %})</span>
            </label>
            <input type="text" name="motif" id="id_motif_action" maxlength="200"
                   form="stock-action-form"
                   style="padding: 8px 12px; border: 1px solid var(--color-base-300, #d1d5db); border-radius: 6px; width: 100%; font-size: 14px;"
                   data-testid="input-motif-action">
        </div>
    </div>

    {% comment %}
    4 boutons — chacun soumet le même formulaire avec un type_mouvement différent.
    Le formulaire est identifié par id="stock-action-form" et les inputs
    utilisent form="stock-action-form" pour y être rattachés.
    / 4 buttons — each submits the same form with a different type_mouvement.
    {% endcomment %}
    <form id="stock-action-form" method="post"
          hx-target="#stock-actions-container"
          hx-swap="innerHTML">
        {% csrf_token %}
        <div style="display: flex; gap: 8px; flex-wrap: wrap;">
            <button type="submit" name="type_mouvement" value="RE"
                    hx-post="{{ stock_action_url }}"
                    hx-include="#id_quantite_action, #id_motif_action"
                    style="padding: 8px 18px; background-color: #16a34a; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px;"
                    data-testid="btn-reception">
                {% translate "Réception" %}
            </button>
            <button type="submit" name="type_mouvement" value="AJ"
                    hx-post="{{ stock_action_url }}"
                    hx-include="#id_quantite_action, #id_motif_action"
                    style="padding: 8px 18px; background-color: #d97706; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px;"
                    data-testid="btn-ajustement">
                {% translate "Ajustement" %}
            </button>
            <button type="submit" name="type_mouvement" value="OF"
                    hx-post="{{ stock_action_url }}"
                    hx-include="#id_quantite_action, #id_motif_action"
                    style="padding: 8px 18px; background-color: #2563eb; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px;"
                    data-testid="btn-offert">
                {% translate "Offert" %}
            </button>
            <button type="submit" name="type_mouvement" value="PE"
                    hx-post="{{ stock_action_url }}"
                    hx-include="#id_quantite_action, #id_motif_action"
                    style="padding: 8px 18px; background-color: #dc2626; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px;"
                    data-testid="btn-perte">
                {% translate "Perte/casse" %}
            </button>
        </div>
    </form>

    {% comment %}
    APERÇU — 5 derniers mouvements + lien vers la liste complète
    / PREVIEW — 5 latest movements + link to full list
    {% endcomment %}
    {% if derniers_mouvements %}
    <div style="margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--color-base-200, #e5e7eb);">
        <h4 style="margin: 0 0 8px 0; font-size: 13px; font-weight: 600; color: var(--color-base-500, #6b7280);">
            {% translate "Derniers mouvements" %}
        </h4>
        <ul style="list-style: none; padding: 0; margin: 0; font-size: 13px;">
            {% for mvt in derniers_mouvements %}
            <li style="padding: 4px 0; color: var(--color-base-600, #4b5563);">
                {{ mvt.cree_le|date:"d/m H:i" }}
                — <strong>{{ mvt.get_type_mouvement_display }}</strong>
                {{ mvt.quantite|stringformat:"+d" }}
                {% if mvt.motif %} — <em>{{ mvt.motif }}</em>{% endif %}
            </li>
            {% endfor %}
        </ul>
        <a href="/admin/inventaire/mouvementstock/?stock__pk__exact={{ stock.pk }}"
           style="display: inline-block; margin-top: 8px; font-size: 13px; color: var(--color-primary-600, #2563eb);"
           data-testid="link-tous-mouvements">
            {% translate "Voir tous les mouvements de cet article" %} →
        </a>
    </div>
    {% endif %}

</div>
```

- [ ] **Step 3 : Créer `mouvements_list_before.html`** (aide filtre)

Créer `Administration/templates/admin/inventaire/mouvements_list_before.html` :

```html
<!--
AIDE FILTRE MOUVEMENTS — bandeau informatif au-dessus de la liste
/ FILTER HELP — informational banner above the list

LOCALISATION : Administration/templates/admin/inventaire/mouvements_list_before.html
-->
{% load i18n %}

<div style="padding: 12px 16px; margin-bottom: 16px; border-radius: 8px; background: var(--color-base-50, #f0f9ff); border: 1px solid var(--color-base-200, #bae6fd); font-size: 13px; line-height: 1.6; color: var(--color-base-600, #4b5563);"
     data-testid="mouvements-aide-filtre">
    <p style="margin: 0 0 4px 0; font-weight: 600;">
        {% translate "Par défaut, seuls les mouvements manuels sont affichés" %}
    </p>
    <p style="margin: 0;">
        {% translate "Les ventes et débits mètre (automatiques) sont masqués. Utilisez le filtre « Type de mouvement » → « Tout afficher » pour voir l'historique complet. Ce journal est en lecture seule : chaque mouvement est créé automatiquement lors d'une opération de stock." %}
    </p>
</div>
```

- [ ] **Step 4 : Vérifier les templates avec Django check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

---

## Task 3 : Brancher les templates sur les admins

**Files:**
- Modify: `Administration/admin/inventaire.py` — `StockAdmin` + `MouvementStockAdmin`

### Steps

- [ ] **Step 1 : Modifier `StockAdmin`**

Ajouter dans `StockAdmin` (après `fields`) :

```python
    change_form_after_template = "admin/inventaire/stock_actions.html"

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """
        Injecte le contexte pour le template after (actions stock).
        / Injects context for the after template (stock actions).
        """
        extra_context = extra_context or {}
        if object_id:
            stock = get_object_or_404(Stock, pk=object_id)
            derniers_mouvements = (
                MouvementStock.objects.filter(stock=stock)
                .select_related("cree_par")
                .order_by("-cree_le")[:5]
            )
            extra_context["stock"] = stock
            extra_context["product_name"] = stock.product.name
            extra_context["derniers_mouvements"] = derniers_mouvements
            extra_context["stock_action_url"] = f"/admin/inventaire/stock/{object_id}/action/"
        return super().changeform_view(request, object_id, form_url, extra_context)
```

Ajouter les imports nécessaires en haut du fichier : `from django.shortcuts import get_object_or_404`

Ajouter `get_urls` et `_stock_action_view` (voir Task 1 Step 5).

- [ ] **Step 2 : Modifier `MouvementStockAdmin`**

Ajouter dans `MouvementStockAdmin` :

```python
    list_before_template = "admin/inventaire/mouvements_list_before.html"
```

- [ ] **Step 3 : Vérifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

---

## Task 4 : Retirer StockInline + ajustement du changeform POSProduct

**Files:**
- Modify: `Administration/admin/products.py:1063-1171`

### Contexte

`POSProductAdmin` a actuellement :
- `inlines = [StockInline, PriceInline]` (ligne 1069)
- `change_form_after_template = "admin/inventaire/ajustement_form.html"` (ligne 1070)
- `get_urls()` avec route `ajustement-stock/` (lignes 1124-1136)
- `_ajustement_stock_view()` (lignes 1138-1171)

On retire tout sauf `StockInline` en mode add. On garde `PriceInline`.

### Steps

- [ ] **Step 1 : Modifier `POSProductAdmin`**

Remplacer la ligne `inlines` et retirer `change_form_after_template` :

```python
    inlines = [PriceInline]  # StockInline retiré — le stock se gère via /admin/inventaire/stock/
    # change_form_after_template retiré — l'ajustement est dans StockAdmin

    def get_inlines(self, request, obj):
        # En mode add (pas d'obj) : inclure StockInline pour créer le stock initial
        # En mode change : pas de StockInline (le stock se gère via StockAdmin)
        # / In add mode: include StockInline for initial stock creation
        # In change mode: no StockInline (stock managed via StockAdmin)
        if obj is None:
            from Administration.admin.inventaire import StockInline
            return [StockInline, PriceInline]
        return [PriceInline]
```

Retirer `get_urls()` et `_ajustement_stock_view()` (lignes 1124-1171).

Retirer l'import `from Administration.admin.inventaire import StockInline` en haut du fichier (ligne 24) — il est maintenant importé dynamiquement dans `get_inlines`.

- [ ] **Step 2 : Supprimer `ajustement_form.html`**

Supprimer `Administration/templates/admin/inventaire/ajustement_form.html` — remplacé par `stock_actions.html`.

- [ ] **Step 3 : Vérifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run pytest tests/pytest/test_inventaire.py tests/pytest/test_stock_visuel_pos.py tests/pytest/test_stock_actions_admin.py -v --tb=short
```

---

## Task 5 : Traductions i18n

**Files:**
- Modify: `locale/fr/LC_MESSAGES/django.po`
- Modify: `locale/en/LC_MESSAGES/django.po`

### Steps

- [ ] **Step 1 : Extraire les nouvelles chaînes**

```bash
docker exec lespass_django poetry run django-admin makemessages -l fr
docker exec lespass_django poetry run django-admin makemessages -l en
```

- [ ] **Step 2 : Remplir les traductions EN pour les nouvelles chaînes**

Chaînes à traduire (chercher dans les `.po`) :
- "Opérations de stock" → "Stock operations"
- "Aide : comprendre les actions" → "Help: understanding the actions"
- "Réception" → "Reception"
- "Ajustement" → "Adjustment"
- "Offert" → "Offered"
- "Perte/casse" → "Loss/breakage"
- Les textes d'aide détaillés
- "Derniers mouvements" → "Recent movements"
- "Voir tous les mouvements de cet article" → "View all movements for this item"
- "Par défaut, seuls les mouvements manuels sont affichés" → "By default, only manual movements are shown"
- etc.

FR : `msgstr` = `msgid` (texte source déjà en français)

- [ ] **Step 3 : Compiler**

```bash
docker exec lespass_django poetry run django-admin compilemessages
```

---

## Task 6 : Documentation technique et utilisateur

**Files:**
- Create: `TECH DOC/A DOCUMENTER/inventaire-actions-stock.md`

### Steps

- [ ] **Step 1 : Créer la documentation**

Créer `TECH DOC/A DOCUMENTER/inventaire-actions-stock.md` avec :

**Section 1 — Documentation technique :**
- Architecture : template after → hx-post → ViewSet → StockService → partial HTMX
- Fichiers modifiés/créés (tableau)
- StockActionSerializer : champs, validation
- stock_action_view : flux détaillé
- Route admin : `get_urls()` sur StockAdmin
- Distinction offert admin vs offert POS

**Section 2 — Documentation utilisateur :**
- Comment accéder : Admin → Inventaire → Stocks → cliquer sur un article
- Les 4 actions avec exemples concrets :
  - Réception : "Je reçois 24 bières → quantité = 24 → bouton Réception"
  - Ajustement : "Je compte 18 bières en stock → quantité = 18 → bouton Ajustement"
  - Offert : "J'offre 2 bières pour déguster → quantité = 2 → bouton Offert"
  - Perte : "3 bouteilles cassées → quantité = 3 → bouton Perte"
- Attention offert : "L'offert admin retire du stock mais n'apparaît PAS dans les rapports comptables. Pour un offert traçable en comptabilité, utiliser le POS."
- Consulter l'historique : lien "Voir tous les mouvements"
- Le filtre par défaut : mouvements manuels visibles, "Tout afficher" pour voir les ventes

**Section 3 — Scénarios de test manuels :**
1. Réception : vérifier stock augmenté + mouvement créé
2. Ajustement hausse : stock réel > stock actuel
3. Ajustement baisse : stock réel < stock actuel
4. Offert : stock diminué, aucune LigneArticle créée
5. Perte : stock diminué + mouvement type PE
6. Historique : lien vers mouvements filtrés par article

- [ ] **Step 2 : Mettre à jour CHANGELOG.md**

Ajouter en haut du CHANGELOG :

```markdown
## Formulaire d'actions stock dans l'admin / Stock actions form in admin

**Date :** Avril 2026
**Migration :** Non

**Quoi / What:** Formulaire HTMX sur la fiche Stock (réception, ajustement, offert, perte/casse) avec 4 boutons colorés. Template before aide sur les mouvements. Ajustement stock retiré de POSProduct. Documentation technique et utilisateur.

**Pourquoi / Why:** Centraliser la gestion de stock dans une page dédiée plutôt que la disperser dans le formulaire produit.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `inventaire/views.py` | `stock_action_view()` — endpoint HTMX |
| `inventaire/serializers.py` | `StockActionSerializer` |
| `Administration/admin/inventaire.py` | `StockAdmin` after template + contexte + get_urls, `MouvementStockAdmin` before template |
| `Administration/admin/products.py` | Retirer StockInline changeform + ajustement |
| `Administration/templates/admin/inventaire/` | 3 templates (stock_actions, partial, mouvements before) |

### Migration
- **Migration nécessaire :** Non
```

---

## Résumé de l'ordre d'exécution

| Task | Dépend de | Ce que ça produit |
|------|-----------|-------------------|
| 1 | — | ViewSet + serializer + tests |
| 2 | — | 3 templates HTML |
| 3 | 1, 2 | Branchement admin (after + before + get_urls) |
| 4 | 3 | Nettoyage POSProduct |
| 5 | 2, 3 | Traductions |
| 6 | 1-5 | Documentation |

Tasks 1 et 2 sont parallélisables.
