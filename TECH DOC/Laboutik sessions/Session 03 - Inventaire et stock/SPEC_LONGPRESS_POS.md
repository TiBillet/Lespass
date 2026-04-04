# Spec — Long press POS : panel contextuel article

**Session 27** — 2026-04-04
**Statut** : Design validé, en attente d'implémentation

---

## 1. Objectif

Permettre au caissier d'accéder à des actions contextuelles sur un article
directement depuis le POS, sans naviguer vers l'admin Django.

Le **long press** (600ms) sur une tuile article ouvre un **panel latéral droit**
avec un menu d'actions. La première action implémentée est **Stock** (réception,
offert, perte). Les autres actions sont des boutons grisés (placeholder) pour
les futures sessions.

## 2. Geste long press

### Composant réutilisable : `longpress.js`

Fichier JS autonome (~40 lignes), sans dépendance. Utilise l'API Pointer Events
(fonctionne tactile ET souris).

**Paramètres :**
- Conteneur parent (event delegation)
- Sélecteur des éléments cibles (`.article-container`)
- Délai : 600ms
- Seuil de mouvement : 10px (annulation si le doigt/souris bouge trop)

**Comportement :**

| Événement | Action |
|-----------|--------|
| `pointerdown` sur cible | Ajoute classe `.pressing` + démarre timer 600ms |
| `pointermove` > 10px | Annule timer, retire `.pressing` |
| `pointerup` avant 600ms | Annule timer, retire `.pressing`, laisse le clic normal |
| Timer atteint 600ms | Retire `.pressing`, `preventDefault`, émet `CustomEvent("longpress")` |

**Détail du CustomEvent :**
```js
new CustomEvent("longpress", {
    bubbles: true,
    detail: {
        productUuid: element.dataset.uuid,
        element: element
    }
})
```

### Feedback visuel pendant le press

Classe CSS `.pressing` appliquée pendant les 600ms :

```css
.article-container.pressing {
    transform: scale(0.97);
    filter: brightness(0.85);
    transition: transform 300ms ease, filter 300ms ease;
}
```

Le retour visuel est progressif — le caissier voit la tuile s'assombrir et
comprend que "quelque chose se passe".

### Intégration dans `articles.js`

Handler sur `#products` :

```js
document.getElementById('products').addEventListener('longpress', function(e) {
    const uuid = e.detail.productUuid
    htmx.ajax('GET', `/pos/article/${uuid}/panel/`, {
        target: '#article-panel'
    })
})
```

## 3. Panel latéral

### Structure HTML

Ajout dans `common_user_interface.html` :

```html
<div id="article-panel"></div>
<div id="article-panel-backdrop"></div>
```

### CSS

```css
#article-panel {
    position: absolute;
    right: 0;
    top: 0;
    width: 40%;
    height: 100%;
    z-index: 1001;
    background: var(--bs-body-bg);
    box-shadow: -2px 0 8px rgba(0, 0, 0, 0.3);
    overflow-y: auto;
    transform: translateX(100%);
    transition: transform 300ms ease;
}

#article-panel:not(:empty) {
    transform: translateX(0);
}

/* Backdrop sombre quand le panel est ouvert */
/* Clic sur le backdrop = ferme le panel */
#article-panel-backdrop {
    display: none;
    position: absolute;
    left: 0;
    top: 0;
    width: 100%;
    height: 100%;
    z-index: 1000;
    background: rgba(0, 0, 0, 0.4);
}

#article-panel:not(:empty) ~ #article-panel-backdrop {
    display: block;
}

/* Plein écran sur mobile / tablette portrait */
@media (max-width: 768px) {
    #article-panel {
        width: 100%;
    }
}
```

### Fermeture du panel

- Clic sur le backdrop → JS vide `#article-panel` (`.innerHTML = ''`)
- Bouton `[✕]` dans le template → idem
- Le `:empty` fait disparaître panel + backdrop automatiquement

## 4. Templates HTMX

### Niveau 1 : Menu principal

**Template :** `laboutik/templates/laboutik/partial/article_panel.html`

**URL :** `GET /pos/article/{product_uuid}/panel/`

```
┌──────────────────────────┐
│ {product.name}      [✕]  │
│ ════════════════════════  │
│                          │
│ ▶ Stock                  │  hx-get, hx-target="#article-panel"
│                          │
│   Catégorie         ░░   │  disabled
│   Point de vente    ░░   │  disabled
│   Prix              ░░   │  disabled
│   Apparence         ░░   │  disabled
│   Dupliquer         ░░   │  disabled
│                          │
└──────────────────────────┘
```

**Contexte template :**
- `product` : instance Product
- `has_stock` : booléen (Stock existe pour ce produit)
- `admin_url` : lien vers la fiche admin du produit

Le bouton Stock est actif seulement si `has_stock` est True.
Si le produit n'a pas de stock configuré, le bouton Stock est grisé avec
un message "(pas de stock configuré)".

### Niveau 2 : Vue stock

**Template :** `laboutik/templates/laboutik/partial/article_panel_stock.html`

**URL :** `GET /pos/article/{product_uuid}/stock/`

```
┌──────────────────────────┐
│ ← Retour          Stock  │  hx-get=".../panel/", hx-target="#article-panel"
│ ════════════════════════  │
│                          │
│ {product.name}           │
│ Stock : {qte} {unite} {badge}│
│ Alerte : {seuil} {unite}│
│ ════════════════════════  │
│                          │
│ Quantité : [____] {unite}│
│ Motif :    [__________]  │
│                          │
│ [+ Réception]            │  hx-post=".../stock/reception/"
│ [  Offert   ]            │  hx-post=".../stock/offert/"
│ [  Perte    ]            │  hx-post=".../stock/perte/"
│                          │
│ [Voir dans admin ↗]      │  <a href> classique
└──────────────────────────┘
```

**Contexte template :**
- `product` : instance Product
- `stock` : instance Stock
- `quantite_affichee` : quantité en unité pratique (L, kg) — conversion serveur
- `unite_affichee` : unité pratique (L, kg, pièces)
- `seuil_alerte` : seuil en unité pratique
- `etat` : "ok" | "alerte" | "rupture"
- `admin_stock_url` : lien admin vers la fiche Stock

**Attributs HTMX des boutons d'action :**
```html
<form>
    <input type="number" name="quantite" min="1" required>
    <input type="text" name="motif" maxlength="200">
    <button hx-post="/pos/article/{uuid}/stock/reception/"
            hx-target="#article-panel"
            hx-swap="innerHTML">
        + Réception
    </button>
    <!-- idem offert, perte -->
</form>
```

**Après soumission :**
- Le POST retourne le même template `article_panel_stock.html` mis à jour
- Header `HX-Trigger: stockUpdated` pour rafraîchir le badge sur la tuile
- `broadcast_stock_update()` pour synchroniser les autres caisses via WebSocket

## 5. Vues Django

### ArticlePanelViewSet dans `laboutik/views.py`

Conforme DJC : `ViewSet` explicite, pas de ModelViewSet.

```python
class ArticlePanelViewSet(ViewSet):
    """
    Panel contextuel article POS.
    Contextual article panel for POS.
    """
    permission_classes = [HasLaBoutikAccess]

    def panel(self, request, product_uuid):
        """GET — menu principal / main menu"""
        product = get_object_or_404(Product, uuid=product_uuid)
        stock = Stock.objects.filter(product=product).first()
        context = {
            "product": product,
            "has_stock": stock is not None,
        }
        return render(request, "laboutik/partial/article_panel.html", context)

    def stock_detail(self, request, product_uuid):
        """GET — vue stock détaillée / detailed stock view"""
        product = get_object_or_404(Product, uuid=product_uuid)
        stock = get_object_or_404(Stock, product=product)
        context = build_stock_context(product, stock)
        return render(request, "laboutik/partial/article_panel_stock.html", context)

    def stock_action(self, request, product_uuid, action):
        """POST — action stock (reception/offert/perte)"""
        product = get_object_or_404(Product, uuid=product_uuid)
        stock = get_object_or_404(Stock, product=product)
        serializer = MouvementRapideSerializer(data=request.POST)
        serializer.is_valid(raise_exception=True)
        # StockService.creer_mouvement(...)
        # broadcast_stock_update(...)
        context = build_stock_context(product, stock)
        response = render(request, "laboutik/partial/article_panel_stock.html", context)
        response["HX-Trigger"] = "stockUpdated"
        return response
```

`build_stock_context()` : fonction helper qui convertit les unités de base
(cl, g) en unités pratiques (L, kg) pour l'affichage.

### Validation

Réutilisation de `MouvementRapideSerializer` existant (quantite + motif).
La quantité est saisie en unité pratique par le caissier, convertie côté
serveur avant appel à `StockService`.

### Permissions

`HasLaBoutikAccess` : API key OU session admin. Le caissier connecté en
session admin peut faire les actions stock. Un terminal sans session admin
voit le panel mais les boutons d'action sont masqués.

## 6. URLs

Dans `laboutik/urls.py` :

```python
# Panel contextuel article / Article context panel
path("pos/article/<uuid:product_uuid>/panel/",
     ArticlePanelViewSet.as_view({"get": "panel"}),
     name="article-panel"),
path("pos/article/<uuid:product_uuid>/stock/",
     ArticlePanelViewSet.as_view({"get": "stock_detail"}),
     name="article-panel-stock"),
path("pos/article/<uuid:product_uuid>/stock/<str:action>/",
     ArticlePanelViewSet.as_view({"post": "stock_action"}),
     name="article-panel-stock-action"),
```

## 7. Sécurité

- **CSRF** : les formulaires HTMX incluent le token CSRF (middleware Django)
- **Permissions** : `HasLaBoutikAccess` sur toutes les vues
- **Validation** : `MouvementRapideSerializer` (quantite min=1, motif max=200)
- **XSS** : pas de HTML généré côté JS, tout est server-side via templates Django (auto-escaped)
- **Injection URL** : `action` validée contre une whitelist `["reception", "offert", "perte"]` dans la vue

## 8. Fichiers à créer / modifier

| Fichier | Action | Contenu |
|---------|--------|---------|
| `laboutik/static/js/longpress.js` | **Créer** | Détection long press réutilisable (~40 lignes) |
| `laboutik/static/js/articles.js` | **Modifier** | Handler longpress → htmx.ajax |
| `laboutik/static/css/articles.css` | **Modifier** | `.pressing` feedback + `#article-panel` + backdrop |
| `laboutik/templates/laboutik/views/common_user_interface.html` | **Modifier** | Ajouter `#article-panel` + `#article-panel-backdrop` |
| `laboutik/templates/laboutik/partial/article_panel.html` | **Créer** | Menu principal (6 boutons dont 5 disabled) |
| `laboutik/templates/laboutik/partial/article_panel_stock.html` | **Créer** | Vue stock + formulaire actions |
| `laboutik/views.py` | **Modifier** | ArticlePanelViewSet (3 méthodes) |
| `laboutik/urls.py` | **Modifier** | 3 routes panel |

## 9. Vision future (hors scope session 27)

Les boutons grisés du menu principal seront implémentés dans des sessions dédiées :

- **Catégorie** : déplacer l'article dans une autre catégorie POS
- **Point de vente** : déplacer vers un autre PDV
- **Prix** : ajouter/modifier les prix
- **Apparence** : modifier icône et couleur de la tuile
- **Dupliquer** : copie complète du produit + prices

Chaque action = un nouveau template partial + une méthode dans ArticlePanelViewSet.
Le composant `longpress.js` et le panel latéral sont réutilisés tels quels.
