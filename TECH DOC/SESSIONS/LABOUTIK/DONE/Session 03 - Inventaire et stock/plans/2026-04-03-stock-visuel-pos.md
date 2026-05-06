# Affichage visuel stock dans le POS — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Afficher l'état du stock (alerte/rupture/bloquant) sur les tuiles articles du POS, avec mise à jour temps réel via WebSocket après chaque vente.

**Architecture:** Enrichir `_construire_donnees_articles()` avec les données stock, rendre des pastilles visuelles dans le template Cotton, et broadcaster les mises à jour via le channel layer Redis existant (`laboutik-jauges-{schema}`) après chaque décrémentation de stock.

**Tech Stack:** Django, HTMX OOB swap, Django Channels (WebSocket), CSS

---

## Vue d'ensemble des fichiers

| Fichier | Action | Responsabilité |
|---------|--------|----------------|
| `laboutik/views.py` | Modifier | Enrichir `_construire_donnees_articles()` + broadcast dans `_creer_lignes_articles()` |
| `laboutik/templates/cotton/articles.html` | Modifier | Pastille stock sur les tuiles standard |
| `laboutik/templates/laboutik/partial/hx_stock_badge.html` | Créer | Template OOB swap pour mise à jour WebSocket |
| `laboutik/static/css/articles.css` | Modifier | Styles pastille stock (3 états) |
| `laboutik/static/js/articles.js` | Modifier | Bloquer clic sur articles bloquants |
| `wsocket/broadcast.py` | Modifier | Ajouter `broadcast_stock_update()` |
| `wsocket/consumers.py` | Modifier | Ajouter handler `stock_update()` |
| `tests/pytest/test_stock_visuel_pos.py` | Créer | Tests pytest pour données articles + broadcast |

---

## Task 1 : Helper `_formater_stock_lisible()` + enrichissement données articles

**Files:**
- Modify: `laboutik/views.py:225-375` (`_construire_donnees_articles()`)
- Test: `tests/pytest/test_stock_visuel_pos.py`

### Contexte

`_construire_donnees_articles()` (laboutik/views.py:225) construit la liste de dicts articles pour le POS. Actuellement, la requête Product utilise `select_related('categorie_pos')` et `prefetch_related(prix_euros_prefetch)`. Il faut ajouter `select_related('stock_inventaire')` et enrichir chaque article dict avec les données stock.

Le helper `_formater_stock_lisible()` formate la quantité pour l'affichage :
- `UN` : "3 restants" / "3 remaining"
- `CL` : "1.5 L" (si >= 100cl) ou "50 cl"
- `GR` : "1.2 kg" (si >= 1000g) ou "800 g"

### Steps

- [ ] **Step 1 : Écrire le test pour `_formater_stock_lisible()`**

Créer `tests/pytest/test_stock_visuel_pos.py` :

```python
"""
Tests pour l'affichage visuel du stock dans le POS.
/ Tests for stock visual display in the POS.

LOCALISATION : tests/pytest/test_stock_visuel_pos.py
"""
import pytest

from laboutik.views import _formater_stock_lisible


class TestFormaterStockLisible:
    """
    Teste le formatage de la quantité de stock pour l'affichage POS.
    / Tests stock quantity formatting for POS display.
    """

    def test_unites_pieces(self):
        """Pièces : affiche "N restants" / Units: displays "N remaining" """
        resultat = _formater_stock_lisible(3, "UN")
        assert resultat == "3"

    def test_unites_pieces_zero(self):
        """Pièces à zéro / Units at zero"""
        resultat = _formater_stock_lisible(0, "UN")
        assert resultat == "0"

    def test_unites_pieces_negatif(self):
        """Pièces négatif / Negative units"""
        resultat = _formater_stock_lisible(-2, "UN")
        assert resultat == "-2"

    def test_centilitres_conversion_litres(self):
        """CL >= 100 → affiche en litres / CL >= 100 → displays in liters"""
        resultat = _formater_stock_lisible(150, "CL")
        assert resultat == "1.5 L"

    def test_centilitres_sous_100(self):
        """CL < 100 → affiche en cl / CL < 100 → displays in cl"""
        resultat = _formater_stock_lisible(50, "CL")
        assert resultat == "50 cl"

    def test_centilitres_exact_litre(self):
        """CL = 100 → affiche 1 L (pas 1.0 L) / CL = 100 → shows 1 L"""
        resultat = _formater_stock_lisible(100, "CL")
        assert resultat == "1 L"

    def test_grammes_conversion_kg(self):
        """GR >= 1000 → affiche en kg / GR >= 1000 → displays in kg"""
        resultat = _formater_stock_lisible(1200, "GR")
        assert resultat == "1.2 kg"

    def test_grammes_sous_1000(self):
        """GR < 1000 → affiche en g / GR < 1000 → displays in g"""
        resultat = _formater_stock_lisible(800, "GR")
        assert resultat == "800 g"

    def test_grammes_exact_kg(self):
        """GR = 1000 → affiche 1 kg (pas 1.0 kg) / GR = 1000 → shows 1 kg"""
        resultat = _formater_stock_lisible(1000, "GR")
        assert resultat == "1 kg"

    def test_centilitres_zero(self):
        """CL à zéro / CL at zero"""
        resultat = _formater_stock_lisible(0, "CL")
        assert resultat == "0 cl"
```

- [ ] **Step 2 : Lancer le test pour vérifier qu'il échoue**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_stock_visuel_pos.py -v
```

Attendu : FAIL — `ImportError: cannot import name '_formater_stock_lisible'`

- [ ] **Step 3 : Implémenter `_formater_stock_lisible()` et enrichir `_construire_donnees_articles()`**

Dans `laboutik/views.py`, ajouter le helper AVANT `_construire_donnees_articles()` (vers la ligne 220) :

```python
def _formater_stock_lisible(quantite, unite):
    """
    Formate la quantité de stock en texte lisible pour l'affichage POS.
    / Formats stock quantity as readable text for POS display.

    LOCALISATION : laboutik/views.py

    Regles de conversion :
    - UN (pièces) : "3" / "-2"
    - CL (centilitres) : "1.5 L" si >= 100, sinon "50 cl"
    - GR (grammes) : "1.2 kg" si >= 1000, sinon "800 g"
    / Conversion rules:
    - UN (units): "3" / "-2"
    - CL (centiliters): "1.5 L" if >= 100, else "50 cl"
    - GR (grams): "1.2 kg" if >= 1000, else "800 g"
    """
    if unite == "CL":
        if quantite >= 100:
            valeur_en_litres = quantite / 100
            # Pas de décimale si c'est un nombre entier (1 L, pas 1.0 L)
            # / No decimal if it's a whole number
            if valeur_en_litres == int(valeur_en_litres):
                return f"{int(valeur_en_litres)} L"
            return f"{valeur_en_litres:g} L"
        return f"{quantite} cl"

    if unite == "GR":
        if quantite >= 1000:
            valeur_en_kg = quantite / 1000
            if valeur_en_kg == int(valeur_en_kg):
                return f"{int(valeur_en_kg)} kg"
            return f"{valeur_en_kg:g} kg"
        return f"{quantite} g"

    # UN (pièces) ou unite inconnue → nombre brut
    # / UN (units) or unknown unit → raw number
    return str(quantite)
```

Puis modifier `_construire_donnees_articles()` :

**a)** Ajouter `select_related('stock_inventaire')` à la requête (ligne 252-258) :

```python
    produits = list(
        point_de_vente_instance.products
        .filter(Q(methode_caisse__isnull=False) | Q(categorie_article=Product.ADHESION))
        .select_related('categorie_pos', 'stock_inventaire')
        .prefetch_related(prix_euros_prefetch)
        .order_by('poids', 'name')
    )
```

Note : `select_related` sur un OneToOne fait un LEFT JOIN — les produits sans Stock auront `stock_inventaire` qui lève `RelatedObjectDoesNotExist` (c'est le comportement normal).

**b)** Après la construction de `article_dict` (après la ligne 372, avant `articles.append(article_dict)`), ajouter l'enrichissement stock :

```python
        # --- Données stock pour l'affichage dans la tuile POS ---
        # Si le produit a un Stock lié, on enrichit le dict avec l'état du stock.
        # Sinon, stock_quantite=None signifie "pas de gestion de stock".
        # / If the product has a linked Stock, enrich the dict with stock state.
        # Otherwise, stock_quantite=None means "no stock management".
        from inventaire.models import Stock
        try:
            stock_du_produit = product.stock_inventaire
            est_en_rupture = stock_du_produit.est_en_rupture()
            article_dict['stock_quantite'] = stock_du_produit.quantite
            article_dict['stock_unite'] = stock_du_produit.unite
            article_dict['stock_en_alerte'] = stock_du_produit.est_en_alerte()
            article_dict['stock_en_rupture'] = est_en_rupture
            article_dict['stock_bloquant'] = (
                est_en_rupture and not stock_du_produit.autoriser_vente_hors_stock
            )
            article_dict['stock_quantite_lisible'] = _formater_stock_lisible(
                stock_du_produit.quantite, stock_du_produit.unite
            )
        except Stock.DoesNotExist:
            article_dict['stock_quantite'] = None
```

Note : l'import `from inventaire.models import Stock` est nécessaire dans le try/except pour catcher `Stock.DoesNotExist`. On peut le mettre en haut du fichier dans les imports.

- [ ] **Step 4 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_stock_visuel_pos.py -v
```

Attendu : PASS pour les 10 tests de formatage.

- [ ] **Step 5 : Test d'intégration — données stock dans les articles**

Ajouter au même fichier `tests/pytest/test_stock_visuel_pos.py` :

```python
from django.test import RequestFactory
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.utils import tenant_context

from BaseBillet.models import Product, Price, Configuration
from laboutik.models import PointDeVente
from laboutik.views import _construire_donnees_articles
from inventaire.models import Stock


class TestDonneesArticlesAvecStock(FastTenantTestCase):
    """
    Vérifie que _construire_donnees_articles() enrichit les articles
    avec les données stock quand un Stock existe.
    / Verifies that _construire_donnees_articles() enriches articles
    with stock data when a Stock exists.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.schema_name = "test_stock_visuel"
        tenant.name = "Test Stock Visuel"

    def test_article_sans_stock_a_stock_quantite_none(self):
        """
        Un produit sans Stock lié a stock_quantite=None.
        / A product without linked Stock has stock_quantite=None.
        """
        # Créer un PV avec un produit sans stock
        # / Create a PV with a product without stock
        product = Product.objects.create(
            name="Cafe sans stock",
            categorie_article=Product.VENTE,
            methode_caisse="VT",
            publish=True,
        )
        Price.objects.create(
            product=product,
            name="Normal",
            prix=2.50,
            publish=True,
        )
        pv = PointDeVente.objects.create(
            name="PV test stock",
            comportement=PointDeVente.VENTE,
        )
        pv.products.add(product)

        articles = _construire_donnees_articles(pv)

        assert len(articles) >= 1
        article_cafe = next(a for a in articles if a['name'] == "Cafe sans stock")
        assert article_cafe['stock_quantite'] is None

    def test_article_avec_stock_alerte(self):
        """
        Un produit avec Stock sous le seuil a stock_en_alerte=True.
        / A product with Stock below threshold has stock_en_alerte=True.
        """
        product = Product.objects.create(
            name="Biere stock alerte",
            categorie_article=Product.VENTE,
            methode_caisse="VT",
            publish=True,
        )
        Price.objects.create(
            product=product,
            name="Pinte",
            prix=5.00,
            publish=True,
        )
        Stock.objects.create(
            product=product,
            quantite=3,
            unite="UN",
            seuil_alerte=5,
        )
        pv = PointDeVente.objects.create(
            name="PV test alerte",
            comportement=PointDeVente.VENTE,
        )
        pv.products.add(product)

        articles = _construire_donnees_articles(pv)
        article_biere = next(a for a in articles if a['name'] == "Biere stock alerte")

        assert article_biere['stock_quantite'] == 3
        assert article_biere['stock_en_alerte'] is True
        assert article_biere['stock_en_rupture'] is False
        assert article_biere['stock_bloquant'] is False

    def test_article_avec_stock_bloquant(self):
        """
        Un produit en rupture avec autoriser_vente_hors_stock=False
        a stock_bloquant=True.
        / A product out of stock with autoriser_vente_hors_stock=False
        has stock_bloquant=True.
        """
        product = Product.objects.create(
            name="Vin rupture bloquante",
            categorie_article=Product.VENTE,
            methode_caisse="VT",
            publish=True,
        )
        Price.objects.create(
            product=product,
            name="Verre",
            prix=4.00,
            publish=True,
        )
        Stock.objects.create(
            product=product,
            quantite=0,
            unite="CL",
            seuil_alerte=500,
            autoriser_vente_hors_stock=False,
        )
        pv = PointDeVente.objects.create(
            name="PV test bloquant",
            comportement=PointDeVente.VENTE,
        )
        pv.products.add(product)

        articles = _construire_donnees_articles(pv)
        article_vin = next(a for a in articles if a['name'] == "Vin rupture bloquante")

        assert article_vin['stock_quantite'] == 0
        assert article_vin['stock_en_rupture'] is True
        assert article_vin['stock_bloquant'] is True
        assert article_vin['stock_quantite_lisible'] == "0 cl"
```

- [ ] **Step 6 : Lancer tous les tests du fichier**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_stock_visuel_pos.py -v
```

Attendu : PASS pour les 13 tests.

- [ ] **Step 7 : Vérifier la non-régression POS**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_pos_*.py tests/pytest/test_laboutik_*.py -v --tb=short
```

---

## Task 2 : Template pastille stock + CSS

**Files:**
- Modify: `laboutik/templates/cotton/articles.html`
- Modify: `laboutik/static/css/articles.css`
- Create: `laboutik/templates/laboutik/partial/hx_stock_badge.html`

### Contexte

Le template `cotton/articles.html` boucle sur `pv.articles` et rend chaque tuile standard (lignes 18-107). On ajoute une pastille stock dans le footer de la tuile, juste avant le badge quantité. La pastille a 3 états visuels : alerte (orange), rupture (rouge), bloquant (grisé + non cliquable).

Le template OOB `hx_stock_badge.html` rend exactement le même HTML que la pastille dans `articles.html`, mais avec `hx-swap-oob="innerHTML"` pour la mise à jour WebSocket.

### Steps

- [ ] **Step 1 : Ajouter les styles pastille stock dans `articles.css`**

Ajouter à la fin de `laboutik/static/css/articles.css`, AVANT le media query Sunmi (avant `@media only screen and (width > 1278px)`) :

```css
/* --- PASTILLE STOCK --- */
/* Badge indiquant l'état du stock sur la tuile article
   3 états : alerte (orange), rupture (rouge), bloquant (grisé)
   / Stock badge on article tile
   3 states: alert (orange), out of stock (red), blocking (greyed out) */

.article-stock-badge {
    position: absolute;
    top: 5px;
    right: 5px;
    padding: 2px 7px;
    border-radius: 8px;
    font-size: 0.78rem;
    font-weight: 700;
    line-height: 1.3;
    white-space: nowrap;
    z-index: 2;
    pointer-events: none;
    user-select: none;
}

.article-stock-badge-alerte {
    background-color: rgba(245, 158, 11, 0.9);
    color: #000;
}

.article-stock-badge-rupture {
    background-color: rgba(239, 68, 68, 0.9);
    color: #fff;
}

/* Article bloquant : grisé, non cliquable, opacité réduite
   Le pointer-events:none empêche le clic (JS aussi vérifie data-stock-bloquant)
   / Blocking article: greyed out, not clickable, reduced opacity
   pointer-events:none prevents click (JS also checks data-stock-bloquant) */
.article-bloquant {
    opacity: 0.4;
    pointer-events: none;
    filter: grayscale(60%);
}
```

- [ ] **Step 2 : Modifier le template `cotton/articles.html`**

Dans `laboutik/templates/cotton/articles.html`, modifier la tuile standard.

**a)** Ajouter `data-stock-bloquant` et la classe `.article-bloquant` sur le container (ligne 18-24). Remplacer le bloc `<div` d'ouverture de la tuile standard :

L'ancien code (lignes 18-24) :
```html
<div data-uuid="{{article.id}}" data-name="{{article.name}}" data-price="{{article.prix}}" data-currency="{{ currency_data.symbol }}" data-group="{{article.bt_groupement.groupe}}"
    data-multi-tarif="{{ article.multi_tarif|yesno:'true,false' }}"
    data-est-adhesion="{{ article.est_adhesion|yesno:'true,false' }}"
    data-tarifs='{{ article.tarifs_json }}'
    class="article-container cat-{{ article.categorie.id}}{% if article.est_adhesion %} article-adhesion{% endif %}"
    style="background-color:{{ article.couleur_backgr }};"
    data-testid="article-{{ article.id }}">
```

Le nouveau code :
```html
<div data-uuid="{{article.id}}" data-name="{{article.name}}" data-price="{{article.prix}}" data-currency="{{ currency_data.symbol }}" data-group="{{article.bt_groupement.groupe}}"
    data-multi-tarif="{{ article.multi_tarif|yesno:'true,false' }}"
    data-est-adhesion="{{ article.est_adhesion|yesno:'true,false' }}"
    data-tarifs='{{ article.tarifs_json }}'
    {% if article.stock_bloquant %}data-stock-bloquant="true"{% endif %}
    class="article-container cat-{{ article.categorie.id}}{% if article.est_adhesion %} article-adhesion{% endif %}{% if article.stock_bloquant %} article-bloquant{% endif %}"
    style="background-color:{{ article.couleur_backgr }};"
    data-testid="article-{{ article.id }}">
```

**b)** Ajouter la pastille stock APRÈS l'icône catégorie (après ligne 37, avant la zone visuelle) :

```html
    {% comment %}
    PASTILLE STOCK — badge en haut à droite de la tuile
    3 états : alerte (orange), rupture (rouge), pas de badge si stock normal ou pas géré
    Mise à jour en temps réel via WebSocket OOB swap (hx_stock_badge.html)
    / STOCK BADGE — top-right badge on the tile
    3 states: alert (orange), out of stock (red), no badge if normal or unmanaged
    Real-time update via WebSocket OOB swap (hx_stock_badge.html)
    {% endcomment %}
    <div id="stock-badge-{{ article.id }}"
         aria-live="polite"
         data-testid="stock-badge-{{ article.id }}">
        {% if article.stock_en_alerte %}
        <span class="article-stock-badge article-stock-badge-alerte"
              data-testid="stock-badge-alerte">{{ article.stock_quantite_lisible }}</span>
        {% elif article.stock_en_rupture %}
        <span class="article-stock-badge article-stock-badge-rupture"
              data-testid="stock-badge-rupture">{% translate "Épuisé" %}</span>
        {% endif %}
    </div>
```

- [ ] **Step 3 : Créer le template OOB `hx_stock_badge.html`**

Créer `laboutik/templates/laboutik/partial/hx_stock_badge.html` :

```html
{% load i18n %}
<!--
PASTILLE STOCK OOB — mise à jour via WebSocket après chaque vente
/ Stock badge OOB — real-time update via WebSocket after each sale

LOCALISATION : laboutik/templates/laboutik/partial/hx_stock_badge.html

Ce partial est rendu par broadcast_stock_update() (wsocket/broadcast.py)
et envoyé via WebSocket à toutes les caisses du tenant.

Chaque badge a un ID unique "stock-badge-{product_uuid}".
Les caisses qui n'affichent pas ce produit n'ont pas cet ID dans leur DOM.
HTMX ignore silencieusement le swap — pas d'erreur.

CONTEXT :
- produits_stock[] : liste de dicts {product_uuid, quantite, unite, en_alerte, en_rupture, bloquant, quantite_lisible}
-->

{% for produit in produits_stock %}
<div id="stock-badge-{{ produit.product_uuid }}" hx-swap-oob="innerHTML">
    {% if produit.en_alerte %}
    <span class="article-stock-badge article-stock-badge-alerte"
          data-testid="stock-badge-alerte">{{ produit.quantite_lisible }}</span>
    {% elif produit.en_rupture %}
    <span class="article-stock-badge article-stock-badge-rupture"
          data-testid="stock-badge-rupture">{% translate "Épuisé" %}</span>
    {% endif %}
</div>

{% if produit.bloquant %}
<script>
(function() {
    var el = document.querySelector('[data-uuid="{{ produit.product_uuid }}"]');
    if (el) { el.classList.add('article-bloquant'); el.dataset.stockBloquant = 'true'; }
})();
</script>
{% elif not produit.en_rupture and not produit.en_alerte %}
<script>
(function() {
    var el = document.querySelector('[data-uuid="{{ produit.product_uuid }}"]');
    if (el) { el.classList.remove('article-bloquant'); delete el.dataset.stockBloquant; }
})();
</script>
{% endif %}
{% endfor %}
```

Note : Les petits blocs `<script>` inline mettent à jour les classes CSS du container (`article-bloquant`, `data-stock-bloquant`). C'est nécessaire parce que le OOB swap ne met à jour que le contenu du badge (`innerHTML`), pas les attributs du parent. Ces scripts ne contiennent aucune logique métier — ils synchronisent juste le DOM avec l'état calculé par le serveur.

- [ ] **Step 4 : Vérifier visuellement dans le navigateur**

Recharger la page POS et vérifier :
- Un produit avec stock normal → pas de badge
- Un produit avec stock sous seuil → pastille orange avec quantité
- Un produit en rupture bloquante → grisé + pastille rouge "Épuisé"

- [ ] **Step 5 : Lancer les tests POS existants**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_pos_*.py tests/pytest/test_laboutik_*.py -v --tb=short
```

---

## Task 3 : Bloquer le clic JS sur articles bloquants

**Files:**
- Modify: `laboutik/static/js/articles.js:73-103` (`manageKey()`)

### Contexte

`manageKey()` (articles.js:73) est le handler de clic sur les tuiles. Il remonte au `.article-container` parent et lit les `data-*`. Si `data-stock-bloquant="true"`, on ignore le clic.

### Steps

- [ ] **Step 1 : Modifier `manageKey()` pour bloquer les articles en rupture**

Dans `laboutik/static/js/articles.js`, dans `manageKey()` (ligne 73), ajouter le check APRÈS le `if (ele.classList.contains('article-container'))` :

```javascript
function manageKey(event) {
    const ele = event.target.parentNode

    if (ele.classList.contains('article-container')) {
        // Si le stock est bloquant (rupture + vente hors stock interdite),
        // on ignore le clic — l'article est grisé visuellement.
        // / If stock is blocking (out of stock + sales not allowed),
        // ignore the click — the article is visually greyed out.
        if (ele.dataset.stockBloquant === 'true') {
            return
        }

        const articleUuid = ele.dataset.uuid
        // ... reste du code inchangé
```

Note : le CSS `pointer-events: none` sur `.article-bloquant` empêche déjà le clic de remonter. Ce check JS est une sécurité supplémentaire (ceinture et bretelles) pour le cas où le CSS serait contourné (ex: OOB swap en cours).

- [ ] **Step 2 : Lancer les tests existants**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_pos_*.py -v --tb=short
```

---

## Task 4 : Broadcast WebSocket après décrémentation stock

**Files:**
- Modify: `wsocket/broadcast.py` — ajouter `broadcast_stock_update()`
- Modify: `wsocket/consumers.py` — ajouter handler `stock_update()`
- Modify: `laboutik/views.py:2760-2775` — appeler le broadcast dans `_creer_lignes_articles()`
- Test: `tests/pytest/test_stock_visuel_pos.py`

### Contexte

Pattern existant : `broadcast_jauge_event()` dans `wsocket/broadcast.py` rend un template OOB et l'envoie au group `laboutik-jauges-{schema}`. Le consumer a un handler `jauge_update()` qui fait `self.send(text_data=event["html"])`. On reproduit exactement ce pattern pour le stock.

`_creer_lignes_articles()` tourne dans un `atomic()`. Le broadcast doit se faire via `transaction.on_commit()` pour éviter d'envoyer des données si la transaction rollback. On collecte tous les product_uuid qui ont eu un stock décrémenté, puis on broadcast en une seule fois.

### Steps

- [ ] **Step 1 : Ajouter `broadcast_stock_update()` dans `wsocket/broadcast.py`**

Ajouter à la fin du fichier :

```python
def broadcast_stock_update(produits_stock_data):
    """
    Broadcast la mise à jour des badges stock à toutes les caisses du tenant.
    / Broadcasts stock badge updates to all POS terminals in the tenant.

    LOCALISATION : wsocket/broadcast.py

    Appelé via transaction.on_commit() depuis _creer_lignes_articles()
    après chaque décrémentation de stock.

    Le group laboutik-jauges-{schema} est déjà rejoint par tous les consumers
    (voir LaboutikConsumer.connect()).

    :param produits_stock_data: liste de dicts avec les données stock mises à jour.
        Chaque dict : {product_uuid, quantite, unite, en_alerte, en_rupture, bloquant, quantite_lisible}
    """
    from django.db import connection

    if not produits_stock_data:
        return

    group_name = f"laboutik-jauges-{connection.schema_name}"

    logger.info(
        f"[WS] Broadcast stock update : {len(produits_stock_data)} produit(s) "
        f"→ {group_name}"
    )

    broadcast_html(
        group_name=group_name,
        template_name="laboutik/partial/hx_stock_badge.html",
        context={"produits_stock": produits_stock_data},
        message_type="stock_update",
    )
```

- [ ] **Step 2 : Ajouter le handler `stock_update()` dans le consumer**

Dans `wsocket/consumers.py`, ajouter la méthode dans `LaboutikConsumer` (après `notification()`) :

```python
    async def stock_update(self, event):
        """
        Reçoit une mise à jour de stock depuis le group Redis
        et la pousse au navigateur (OOB swap des badges stock).
        / Receives a stock update from the Redis group and pushes it to the browser.
        """
        await self.send(text_data=event["html"])
```

- [ ] **Step 3 : Brancher le broadcast dans `_creer_lignes_articles()`**

Dans `laboutik/views.py`, modifier `_creer_lignes_articles()`.

**a)** Ajouter un accumulateur avant la boucle (après `lignes_creees = []`, ligne 2720) :

```python
    lignes_creees = []
    # Accumulateur des produits dont le stock a été décrémenté.
    # On broadcastera la mise à jour via WebSocket après le commit.
    # / Accumulator of products whose stock was decremented.
    # We'll broadcast the update via WebSocket after commit.
    produits_stock_mis_a_jour = []
```

**b)** Modifier le bloc try/except stock (lignes 2760-2775). Après `StockService.decrementer_pour_vente()`, relire le stock depuis la DB (car `F()` ne met pas à jour l'instance en mémoire) et collecter les données :

```python
        # --- Décrémentation stock inventaire ---
        # Si le produit a un Stock lié, on décrémente automatiquement.
        # Après décrémentation, on relire le stock depuis la DB
        # (F() ne met pas à jour l'instance en mémoire).
        # / If the product has a linked Stock, auto-decrement.
        # After decrement, re-read stock from DB (F() doesn't update in-memory instance).
        try:
            stock_du_produit = produit.stock_inventaire
            StockService.decrementer_pour_vente(
                stock=stock_du_produit,
                contenance=prix_obj.contenance,
                qty=quantite,
                ligne_article=ligne,
            )

            # Relire le stock depuis la DB pour avoir la quantité à jour
            # / Re-read stock from DB to get updated quantity
            stock_du_produit.refresh_from_db()

            produits_stock_mis_a_jour.append({
                "product_uuid": str(produit.uuid),
                "quantite": stock_du_produit.quantite,
                "unite": stock_du_produit.unite,
                "en_alerte": stock_du_produit.est_en_alerte(),
                "en_rupture": stock_du_produit.est_en_rupture(),
                "bloquant": (
                    stock_du_produit.est_en_rupture()
                    and not stock_du_produit.autoriser_vente_hors_stock
                ),
                "quantite_lisible": _formater_stock_lisible(
                    stock_du_produit.quantite, stock_du_produit.unite
                ),
            })
        except Exception:
            # Pas de stock géré pour ce produit — comportement normal
            # / No stock managed for this product — normal behavior
            pass
```

**c)** Après la boucle HMAC (après `return lignes_creees`, ligne 2812), le broadcast est en dehors de la fonction. On le fait plutôt JUSTE AVANT le return, via `on_commit()` :

Ajouter AVANT `return lignes_creees` (vers ligne 2811) :

```python
    # --- Broadcast WebSocket des badges stock mis à jour ---
    # on_commit() : le broadcast ne s'exécute qu'après le commit de la transaction.
    # Si la transaction rollback, le broadcast n'est jamais envoyé.
    # / WebSocket broadcast of updated stock badges.
    # on_commit(): broadcast only runs after transaction commit.
    if produits_stock_mis_a_jour:
        from django.db import transaction
        from wsocket.broadcast import broadcast_stock_update

        # Copie de la liste pour que la closure capture les données actuelles
        # / Copy the list so the closure captures current data
        donnees_a_broadcaster = list(produits_stock_mis_a_jour)
        transaction.on_commit(
            lambda: broadcast_stock_update(donnees_a_broadcaster)
        )

    return lignes_creees
```

- [ ] **Step 4 : Écrire le test pour le broadcast**

Ajouter dans `tests/pytest/test_stock_visuel_pos.py` :

```python
from unittest.mock import patch, MagicMock


class TestBroadcastStockApresVente(FastTenantTestCase):
    """
    Vérifie que _creer_lignes_articles() collecte les données stock
    pour le broadcast WebSocket après décrémentation.
    / Verifies that _creer_lignes_articles() collects stock data
    for WebSocket broadcast after decrement.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.schema_name = "test_stock_broadcast"
        tenant.name = "Test Stock Broadcast"

    def test_broadcast_stock_appele_apres_decrementation(self):
        """
        Après une vente d'un produit avec stock, broadcast_stock_update()
        est enregistré via on_commit() avec les données stock à jour.
        / After selling a product with stock, broadcast_stock_update()
        is registered via on_commit() with updated stock data.
        """
        from laboutik.views import _creer_lignes_articles
        from laboutik.models import PointDeVente

        # Créer le produit avec stock
        # / Create product with stock
        product = Product.objects.create(
            name="Soda broadcast test",
            categorie_article=Product.VENTE,
            methode_caisse="VT",
            publish=True,
        )
        price = Price.objects.create(
            product=product,
            name="Normal",
            prix=3.00,
            publish=True,
        )
        Stock.objects.create(
            product=product,
            quantite=10,
            unite="UN",
            seuil_alerte=3,
        )

        pv = PointDeVente.objects.create(
            name="PV broadcast test",
            comportement=PointDeVente.VENTE,
        )

        articles_panier = [{
            'product': product,
            'price': price,
            'quantite': 1,
            'prix_centimes': 300,
        }]

        # Mocker broadcast_stock_update pour vérifier qu'il est appelé
        # / Mock broadcast_stock_update to verify it's called
        with patch('laboutik.views.broadcast_stock_update') as mock_broadcast:
            # Note : on_commit() s'exécute immédiatement dans les tests
            # (pas de transaction réelle wrappée)
            # / on_commit() fires immediately in tests (no real wrapping transaction)
            _creer_lignes_articles(
                articles_panier,
                "espece",
                point_de_vente=pv,
            )

            # Vérifier que le broadcast a été appelé avec les bonnes données
            # / Verify broadcast was called with correct data
            mock_broadcast.assert_called_once()
            donnees = mock_broadcast.call_args[0][0]
            assert len(donnees) == 1
            assert donnees[0]['product_uuid'] == str(product.uuid)
            assert donnees[0]['quantite'] == 9  # 10 - 1
            assert donnees[0]['en_alerte'] is False
            assert donnees[0]['en_rupture'] is False
```

Note : Le mock cible `laboutik.views.broadcast_stock_update` car c'est là que l'import est fait (dans le `lambda` de `on_commit`). Comme les tests n'ont pas de transaction englobante, `on_commit()` fire immédiatement.

- [ ] **Step 5 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_stock_visuel_pos.py -v
```

- [ ] **Step 6 : Vérifier la non-régression complète**

```bash
docker exec lespass_django poetry run pytest tests/pytest/ -q --tb=short
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

- [ ] **Step 2 : Remplir les traductions**

Dans `locale/fr/LC_MESSAGES/django.po`, chercher "Épuisé" :
```
msgid "Épuisé"
msgstr "Épuisé"
```

Dans `locale/en/LC_MESSAGES/django.po` :
```
msgid "Épuisé"
msgstr "Out of stock"
```

- [ ] **Step 3 : Compiler**

```bash
docker exec lespass_django poetry run django-admin compilemessages
```

---

## Task 6 : Documentation et CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`
- Create: `A TESTER et DOCUMENTER/stock-visuel-pos.md`

### Steps

- [ ] **Step 1 : Mettre à jour CHANGELOG.md**

Ajouter en haut du fichier :

```markdown
## N. Affichage visuel stock dans le POS / Stock visual display in POS

**Quoi / What:** Pastille stock sur les tuiles articles POS avec mise à jour temps réel via WebSocket.
**Pourquoi / Why:** Le caissier doit voir d'un coup d'œil quels produits sont en alerte ou en rupture de stock.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | Enrichir `_construire_donnees_articles()` avec données stock, broadcast WS dans `_creer_lignes_articles()` |
| `laboutik/templates/cotton/articles.html` | Pastille stock sur les tuiles |
| `laboutik/templates/laboutik/partial/hx_stock_badge.html` | Template OOB swap pour WebSocket |
| `laboutik/static/css/articles.css` | Styles pastille stock (3 états) |
| `laboutik/static/js/articles.js` | Bloquer clic articles en rupture bloquante |
| `wsocket/broadcast.py` | `broadcast_stock_update()` |
| `wsocket/consumers.py` | Handler `stock_update()` |

### Migration
- **Migration nécessaire / Migration required:** Non
```

- [ ] **Step 2 : Créer le fichier de test manuel**

Créer `A TESTER et DOCUMENTER/stock-visuel-pos.md` avec les scénarios de test :
1. Produit sans stock → pas de badge
2. Produit stock normal (au-dessus du seuil) → pas de badge
3. Produit stock en alerte → pastille orange avec quantité
4. Produit en rupture non bloquante → pastille rouge "Épuisé", cliquable
5. Produit en rupture bloquante → grisé, non cliquable
6. Après une vente → badge mis à jour en temps réel (ouvrir 2 onglets POS)

---

## Résumé de l'ordre d'exécution

| Task | Dépend de | Ce que ça produit |
|------|-----------|-------------------|
| 1 | — | Helper + données stock dans les articles |
| 2 | 1 | Template + CSS des pastilles |
| 3 | 2 | Blocage clic JS |
| 4 | 1 | WebSocket broadcast après vente |
| 5 | 2 | Traductions |
| 6 | 1-5 | Documentation |

Tasks 2 et 4 peuvent être parallélisées (2 dépend de 1, 4 dépend de 1, mais pas l'un de l'autre).
