# Long Press POS — Panel Contextuel Article

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un long press sur les tuiles article POS qui ouvre un panel latéral avec menu d'actions et vue stock HTMX.

**Architecture:** Composant JS réutilisable `longpress.js` (Pointer Events, event delegation) émet un `CustomEvent("longpress")`. Le handler dans `articles.js` charge un panel latéral via `htmx.ajax()`. Les vues Django (`ArticlePanelViewSet`) retournent des partials HTMX. Les actions stock appellent `StockService` et retournent le template mis à jour.

**Tech Stack:** Django ViewSet, HTMX (htmx.ajax + hx-get/hx-post), Pointer Events API, CSS transitions, WebSocket broadcast existant.

**Spec de référence :** `TECH DOC/Laboutik sessions/Session 03 - Inventaire et stock/SPEC_LONGPRESS_POS.md`

---

## Structure des fichiers

| Fichier | Action | Responsabilité |
|---------|--------|----------------|
| `laboutik/static/js/longpress.js` | Créer | Détection long press réutilisable (Pointer Events + timer) |
| `laboutik/static/js/articles.js` | Modifier | Handler `longpress` → `htmx.ajax` + fermeture backdrop |
| `laboutik/static/css/articles.css` | Modifier | `.pressing` feedback + `#article-panel` + backdrop |
| `laboutik/templates/laboutik/views/common_user_interface.html` | Modifier | Ajouter `#article-panel` + `#article-panel-backdrop` + `<script>` longpress |
| `laboutik/templates/laboutik/partial/article_panel.html` | Créer | Menu principal (Stock actif + 5 boutons disabled) |
| `laboutik/templates/laboutik/partial/article_panel_stock.html` | Créer | Vue stock + formulaire actions HTMX |
| `laboutik/views.py` | Modifier | `ArticlePanelViewSet` (3 méthodes) + `build_stock_context()` |
| `laboutik/urls.py` | Modifier | 3 routes panel |
| `tests/pytest/test_longpress_panel.py` | Créer | Tests pytest pour les vues panel + actions stock |

---

### Task 1 : Composant long press JS

**Files:**
- Create: `laboutik/static/js/longpress.js`

- [ ] **Step 1 : Créer `longpress.js`**

```js
/**
 * LONGPRESS.JS — Détection d'appui long réutilisable
 * / Reusable long press detection component
 *
 * LOCALISATION : laboutik/static/js/longpress.js
 *
 * Utilise l'API Pointer Events (fonctionne tactile ET souris).
 * Écoute sur un conteneur parent via event delegation.
 * Émet un CustomEvent("longpress") avec bubbles:true sur l'élément cible.
 *
 * USAGE :
 *   initLongPress({
 *     container: document.getElementById('products'),
 *     selector: '.article-container',
 *     delay: 600,
 *     moveThreshold: 10
 *   })
 *
 * COMMUNICATION :
 * Émet : CustomEvent("longpress") sur l'élément cible
 *   detail: { productUuid: string, element: HTMLElement }
 */

/**
 * Initialise la détection de long press sur un conteneur.
 * / Initialize long press detection on a container.
 *
 * @param {Object} options
 * @param {HTMLElement} options.container - Conteneur parent (event delegation)
 * @param {String} options.selector - Sélecteur CSS des éléments cibles
 * @param {Number} options.delay - Délai en ms avant déclenchement (défaut 600)
 * @param {Number} options.moveThreshold - Seuil de mouvement en px pour annuler (défaut 10)
 */
function initLongPress(options) {
    const container = options.container
    const selector = options.selector
    const delay = options.delay || 600
    const moveThreshold = options.moveThreshold || 10

    let timer = null
    let startX = 0
    let startY = 0
    let activeElement = null
    // Flag pour bloquer le clic qui suit un long press réussi
    // / Flag to block the click that follows a successful long press
    let longPressTriggered = false

    container.addEventListener('pointerdown', function(e) {
        // Remonter au parent qui matche le sélecteur
        // / Walk up to the parent matching the selector
        const target = e.target.closest(selector)
        if (!target) return

        activeElement = target
        startX = e.clientX
        startY = e.clientY
        longPressTriggered = false

        // Feedback visuel progressif / Progressive visual feedback
        activeElement.classList.add('pressing')

        timer = setTimeout(function() {
            // Long press déclenché / Long press triggered
            activeElement.classList.remove('pressing')
            longPressTriggered = true

            activeElement.dispatchEvent(new CustomEvent('longpress', {
                bubbles: true,
                detail: {
                    productUuid: activeElement.dataset.uuid,
                    element: activeElement
                }
            }))

            activeElement = null
        }, delay)
    })

    container.addEventListener('pointermove', function(e) {
        if (!timer) return

        // Annuler si le doigt/souris bouge trop
        // / Cancel if finger/mouse moves too much
        const dx = e.clientX - startX
        const dy = e.clientY - startY
        const distance = Math.sqrt(dx * dx + dy * dy)

        if (distance > moveThreshold) {
            clearTimeout(timer)
            timer = null
            if (activeElement) {
                activeElement.classList.remove('pressing')
                activeElement = null
            }
        }
    })

    container.addEventListener('pointerup', function() {
        if (timer) {
            // Relâché avant le délai → annuler, laisser le clic normal
            // / Released before delay → cancel, let normal click through
            clearTimeout(timer)
            timer = null
        }
        if (activeElement) {
            activeElement.classList.remove('pressing')
            activeElement = null
        }
    })

    container.addEventListener('pointercancel', function() {
        if (timer) {
            clearTimeout(timer)
            timer = null
        }
        if (activeElement) {
            activeElement.classList.remove('pressing')
            activeElement = null
        }
    })

    // Bloquer le clic qui suit immédiatement un long press réussi.
    // Sans ça, pointerup déclenche un click → l'article est ajouté au panier.
    // / Block the click that immediately follows a successful long press.
    // Without this, pointerup fires a click → article gets added to cart.
    container.addEventListener('click', function(e) {
        if (longPressTriggered) {
            e.stopPropagation()
            e.preventDefault()
            longPressTriggered = false
        }
    }, true)  // capture phase pour intercepter avant manageKey
}
```

- [ ] **Step 2 : Vérifier la syntaxe**

Ouvrir le fichier dans le navigateur ou lancer un linter JS si disponible. Pas de dépendance, pas de module — c'est un script classique qui déclare une fonction globale `initLongPress()`.

---

### Task 2 : CSS — feedback `.pressing` + panel latéral

**Files:**
- Modify: `laboutik/static/css/articles.css` (après la section `/* --- PASTILLE STOCK --- */`, ligne ~446)

- [ ] **Step 1 : Ajouter les styles `.pressing` et panel**

Ajouter à la fin de `articles.css` (après la dernière `@media` query, ligne 459) :

```css
/* --- LONG PRESS FEEDBACK --- */
/* Retour visuel pendant l'appui long (600ms).
   La tuile s'assombrit et rétrécit légèrement.
   / Visual feedback during long press (600ms).
   Tile darkens and slightly shrinks. */
.article-container.pressing {
    transform: scale(0.97);
    filter: brightness(0.85);
    transition: transform 300ms ease, filter 300ms ease;
}

/* Désactiver le :active natif pendant le pressing
   (sinon double effet scale)
   / Disable native :active during pressing
   (otherwise double scale effect) */
.article-container.pressing:active {
    transform: scale(0.97);
}


/* --- PANEL CONTEXTUEL ARTICLE --- */
/* Panel latéral droit pour les actions contextuelles (long press).
   Slide-in depuis la droite, visible quand non vide.
   / Right side panel for contextual actions (long press).
   Slides in from right, visible when not empty. */
#article-panel {
    position: absolute;
    right: 0;
    top: 0;
    width: 40%;
    height: 100%;
    z-index: 1001;
    background: var(--gris00, #1a1a2e);
    color: var(--blanc01, #fff);
    box-shadow: -2px 0 12px rgba(0, 0, 0, 0.4);
    overflow-y: auto;
    transform: translateX(100%);
    transition: transform 300ms ease;
    font-family: "Luciole-regular", sans-serif;
}

#article-panel:not(:empty) {
    transform: translateX(0);
}

/* Backdrop sombre — clic dessus ferme le panel.
   Sibling du panel dans le DOM, activé via :has() du panel.
   / Dark backdrop — click closes the panel.
   Sibling of panel in DOM, activated via panel :has(). */
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

/* Plein écran sur mobile / tablette portrait
   / Full screen on mobile / portrait tablet */
@media (max-width: 768px) {
    #article-panel {
        width: 100%;
    }
}


/* --- PANEL : COMPOSANTS INTERNES --- */
/* / Panel: internal components */

.panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.panel-title {
    font-size: 1.3rem;
    font-weight: bold;
    flex: 1;
    margin-right: 8px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.panel-close-btn {
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.1);
    color: var(--blanc01, #fff);
    font-size: 1.3rem;
    cursor: pointer;
    flex-shrink: 0;
    transition: background-color 150ms ease;
}

.panel-close-btn:hover {
    background: rgba(255, 255, 255, 0.2);
}

.panel-body {
    padding: 16px 20px;
    display: flex;
    flex-direction: column;
    gap: 10px;
}

/* Bouton menu du panel (Stock, Catégorie, etc.)
   / Panel menu button (Stock, Category, etc.) */
.panel-menu-btn {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    padding: 14px 16px;
    border: none;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.08);
    color: var(--blanc01, #fff);
    font-size: 1.1rem;
    font-family: "Luciole-regular", sans-serif;
    cursor: pointer;
    text-align: left;
    transition: background-color 150ms ease, transform 100ms ease;
}

.panel-menu-btn:hover {
    background: rgba(255, 255, 255, 0.15);
}

.panel-menu-btn:active {
    transform: scale(0.98);
}

.panel-menu-btn[disabled] {
    opacity: 0.35;
    cursor: not-allowed;
    pointer-events: none;
}

.panel-menu-icon {
    font-size: 1.3rem;
    width: 24px;
    text-align: center;
    flex-shrink: 0;
}

.panel-menu-label {
    flex: 1;
}

.panel-menu-badge {
    font-size: 0.8rem;
    padding: 2px 8px;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.1);
    opacity: 0.6;
}

/* Bouton retour (← Retour) / Back button */
.panel-back-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 0;
    border: none;
    background: transparent;
    color: var(--blanc01, #fff);
    font-size: 1rem;
    font-family: "Luciole-regular", sans-serif;
    cursor: pointer;
    opacity: 0.8;
    transition: opacity 150ms ease;
}

.panel-back-btn:hover {
    opacity: 1;
}


/* --- PANEL STOCK : VUE DÉTAILLÉE --- */
/* / Panel stock: detailed view */

.stock-info-card {
    padding: 14px 16px;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.06);
}

.stock-info-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 4px 0;
}

.stock-info-label {
    font-size: 0.95rem;
    opacity: 0.7;
}

.stock-info-value {
    font-size: 1.2rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
}

.stock-badge-ok {
    color: var(--vert01, #00e676);
}

.stock-badge-alerte {
    color: var(--warning, #ff9800);
}

.stock-badge-rupture {
    color: var(--rouge01, #e53935);
}

.stock-separator {
    height: 1px;
    background: rgba(255, 255, 255, 0.1);
    margin: 12px 0;
}

/* Formulaire actions stock / Stock action form */
.stock-form-group {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.stock-form-label {
    font-size: 0.9rem;
    opacity: 0.7;
}

.stock-form-input-row {
    display: flex;
    align-items: center;
    gap: 8px;
}

.stock-form-input {
    height: 48px;
    width: 100px;
    font-size: 1.3rem;
    text-align: center;
    border: 2px solid rgba(255, 255, 255, 0.25);
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.08);
    color: #fff;
    font-variant-numeric: tabular-nums;
    font-family: "Luciole-regular", sans-serif;
}

.stock-form-input:focus {
    outline: none;
    border-color: var(--vert01, #00e676);
}

.stock-form-unit {
    font-size: 1.1rem;
    font-weight: 600;
    opacity: 0.8;
}

.stock-form-motif {
    height: 40px;
    width: 100%;
    padding: 0 12px;
    font-size: 1rem;
    border: 2px solid rgba(255, 255, 255, 0.15);
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.05);
    color: #fff;
    font-family: "Luciole-regular", sans-serif;
}

.stock-form-motif:focus {
    outline: none;
    border-color: rgba(255, 255, 255, 0.4);
}

.stock-form-motif::placeholder {
    color: rgba(255, 255, 255, 0.3);
}

/* Boutons d'action stock / Stock action buttons */
.stock-actions-grid {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.stock-action-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    width: 100%;
    height: 48px;
    border: none;
    border-radius: 10px;
    font-size: 1.1rem;
    font-weight: 600;
    font-family: "Luciole-regular", sans-serif;
    cursor: pointer;
    color: #fff;
    transition: transform 100ms ease, filter 100ms ease;
}

.stock-action-btn:active {
    transform: scale(0.97);
}

.stock-action-btn-reception {
    background: var(--vert03, #2e7d32);
}

.stock-action-btn-offert {
    background: var(--bleu03, #0345ea);
}

.stock-action-btn-perte {
    background: var(--rouge07, #b71c1c);
}

/* Lien admin / Admin link */
.stock-admin-link {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 10px;
    font-size: 0.9rem;
    color: var(--blanc01, #fff);
    opacity: 0.6;
    text-decoration: none;
    transition: opacity 150ms ease;
}

.stock-admin-link:hover {
    opacity: 1;
}

/* Message feedback après action stock / Feedback message after stock action */
.stock-feedback {
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 0.95rem;
    font-weight: 600;
    text-align: center;
    animation: overlay-fade-up 300ms ease;
}

.stock-feedback-success {
    background: rgba(46, 125, 50, 0.3);
    color: var(--vert01, #00e676);
}

.stock-feedback-error {
    background: rgba(183, 28, 28, 0.3);
    color: var(--rouge01, #e53935);
}
```

---

### Task 3 : Structure HTML — panel + backdrop + scripts

**Files:**
- Modify: `laboutik/templates/laboutik/views/common_user_interface.html`

- [ ] **Step 1 : Ajouter le panel et le backdrop dans le template**

Ajouter juste avant la fermeture `</main>` (ligne 119, avant `<c-footer />`) :

```html
	{# PANEL CONTEXTUEL ARTICLE — long press sur tuile
	   Contient : menu d'actions (Stock, Catégorie, PDV, ...) puis vue détaillée.
	   Vide par défaut = invisible (CSS :empty). Rempli par htmx.ajax().
	   / ARTICLE CONTEXT PANEL — long press on tile
	   Contains: actions menu then detail view. Empty = invisible. Filled by htmx.ajax(). #}
	<div id="article-panel"></div>
	<div id="article-panel-backdrop"></div>
```

- [ ] **Step 2 : Ajouter les scripts longpress.js et le handler dans le bloc `<script>`**

Dans `common_user_interface.html`, ajouter la balise `<script>` de longpress.js **avant** le `<script>` existant (ligne 123) :

```html
<script src="{% static 'js/longpress.js' %}"></script>
```

Puis dans le bloc `document.addEventListener('DOMContentLoaded', ...)` existant (ligne 231-235), ajouter **après** les 3 écouteurs existants :

```js
	// Long press sur les tuiles article → ouvre le panel contextuel
	// / Long press on article tiles → opens contextual panel
	initLongPress({
		container: document.querySelector('#products'),
		selector: '.article-container',
		delay: 600,
		moveThreshold: 10
	})

	// Fermeture du panel via le backdrop
	// / Close panel via backdrop click
	document.getElementById('article-panel-backdrop').addEventListener('click', function() {
		document.getElementById('article-panel').innerHTML = ''
	})
```

- [ ] **Step 3 : Ajouter le handler `longpress` dans `articles.js`**

Modifier `laboutik/static/js/articles.js`. Dans le bloc `DOMContentLoaded` (ligne 273-284), ajouter après l'écouteur `htmx:wsAfterMessage` (ligne 283) :

```js
	// Long press sur un article → charger le panel contextuel via HTMX
	// / Long press on article → load contextual panel via HTMX
	document.querySelector('#products').addEventListener('longpress', function(e) {
		const uuid = e.detail.productUuid
		if (!uuid) return
		htmx.ajax('GET', '/laboutik/article-panel/' + uuid + '/panel/', {
			target: '#article-panel',
			swap: 'innerHTML'
		})
	})
```

- [ ] **Step 4 : Ajouter la fermeture du panel dans `articles.js` (fonction utilitaire)**

Ajouter **avant** le bloc `DOMContentLoaded` dans `articles.js` :

```js
/**
 * Ferme le panel contextuel article (vide son contenu).
 * Appelé par les boutons [✕] dans les partials du panel.
 * / Closes the article context panel (empties its content).
 * Called by [✕] buttons in panel partials.
 *
 * LOCALISATION : laboutik/static/js/articles.js
 */
function closeArticlePanel() {
	document.getElementById('article-panel').innerHTML = ''
}
```

---

### Task 4 : Vues Django — ArticlePanelViewSet

**Files:**
- Modify: `laboutik/views.py`
- Modify: `laboutik/urls.py`

- [ ] **Step 1 : Ajouter les imports nécessaires**

Dans `laboutik/views.py`, vérifier que ces imports sont présents (la plupart le sont déjà) :

```python
# Déjà importés :
# from django.shortcuts import render, get_object_or_404
# from rest_framework import viewsets
# from BaseBillet.models import Product
# from BaseBillet.permissions import HasLaBoutikAccess
# from inventaire.models import Stock

# À ajouter si absent :
from inventaire.models import TypeMouvement
from inventaire.serializers import MouvementRapideSerializer
from inventaire.services import StockService
from wsocket.broadcast import broadcast_stock_update
```

- [ ] **Step 2 : Ajouter `build_stock_context()` dans `laboutik/views.py`**

Ajouter après la fonction `_formater_stock_lisible()` (après ligne 277) :

```python
def _build_stock_context(product, stock, message_feedback=None, erreur_feedback=None):
    """
    Construit le contexte pour le template article_panel_stock.html.
    Convertit les unités de base en unités pratiques pour l'affichage.
    / Builds context for article_panel_stock.html template.
    Converts base units to practical units for display.

    LOCALISATION : laboutik/views.py
    """
    quantite_lisible = _formater_stock_lisible(stock.quantite, stock.unite)
    seuil_lisible = ""
    if stock.seuil_alerte is not None:
        seuil_lisible = _formater_stock_lisible(stock.seuil_alerte, stock.unite)

    # Déterminer l'unité pratique pour le champ de saisie
    # / Determine practical unit for the input field
    unite_saisie_map = {
        "UN": _("pièces"),
        "CL": "cl",
        "GR": "g",
    }
    unite_saisie = unite_saisie_map.get(stock.unite, stock.unite)

    # Déterminer l'état du stock / Determine stock state
    if stock.est_en_rupture():
        etat = "rupture"
    elif stock.est_en_alerte():
        etat = "alerte"
    else:
        etat = "ok"

    return {
        "product": product,
        "stock": stock,
        "quantite_lisible": quantite_lisible,
        "seuil_lisible": seuil_lisible,
        "unite_saisie": unite_saisie,
        "etat": etat,
        "message_feedback": message_feedback,
        "erreur_feedback": erreur_feedback,
    }
```

- [ ] **Step 3 : Ajouter `ArticlePanelViewSet` dans `laboutik/views.py`**

Ajouter à la fin du fichier (après la dernière classe/fonction) :

```python
class ArticlePanelViewSet(viewsets.ViewSet):
    """
    Panel contextuel article POS — menu d'actions + vue stock.
    Ouvert par un long press sur une tuile article.
    / Article context panel for POS — actions menu + stock view.
    Opened by a long press on an article tile.

    LOCALISATION : laboutik/views.py

    URLS :
        GET  /laboutik/article-panel/{product_uuid}/panel/  → menu principal
        GET  /laboutik/article-panel/{product_uuid}/stock/   → vue stock
        POST /laboutik/article-panel/{product_uuid}/stock/{action}/ → action stock

    TEMPLATES :
        laboutik/partial/article_panel.html       → menu principal
        laboutik/partial/article_panel_stock.html  → vue stock détaillée
    """

    permission_classes = [HasLaBoutikAccess]

    ACTIONS_AUTORISEES = ["reception", "offert", "perte"]

    # Mapping action URL → TypeMouvement / URL action → movement type mapping
    ACTION_TYPE_MAP = {
        "reception": TypeMouvement.RE,
        "offert": TypeMouvement.OF,
        "perte": TypeMouvement.PE,
    }

    def panel(self, request, product_uuid):
        """
        GET — Menu principal du panel contextuel.
        / GET — Main menu of the context panel.
        """
        product = get_object_or_404(Product, uuid=product_uuid)
        stock = Stock.objects.filter(product=product).first()

        context = {
            "product": product,
            "has_stock": stock is not None,
        }
        return render(request, "laboutik/partial/article_panel.html", context)

    def stock_detail(self, request, product_uuid):
        """
        GET — Vue stock détaillée avec formulaire d'actions.
        / GET — Detailed stock view with action form.
        """
        product = get_object_or_404(Product, uuid=product_uuid)
        stock = get_object_or_404(Stock, product=product)
        context = _build_stock_context(product, stock)
        return render(request, "laboutik/partial/article_panel_stock.html", context)

    def stock_action(self, request, product_uuid, action):
        """
        POST — Exécute une action stock (reception/offert/perte).
        Retourne la vue stock mise à jour + header HX-Trigger.
        / POST — Execute a stock action. Returns updated stock view + HX-Trigger header.
        """
        # Valider l'action contre la whitelist / Validate action against whitelist
        if action not in self.ACTIONS_AUTORISEES:
            return HttpResponse("Action invalide", status=400)

        product = get_object_or_404(Product, uuid=product_uuid)
        stock = get_object_or_404(Stock, product=product)

        serializer = MouvementRapideSerializer(data=request.POST)
        if not serializer.is_valid():
            # Extraire les messages d'erreur lisibles
            # / Extract readable error messages
            messages_erreur = []
            for champ, erreurs in serializer.errors.items():
                for erreur in erreurs:
                    messages_erreur.append(str(erreur))
            erreur_feedback = " ".join(messages_erreur)

            context = _build_stock_context(product, stock, erreur_feedback=erreur_feedback)
            return render(request, "laboutik/partial/article_panel_stock.html", context)

        type_mouvement = self.ACTION_TYPE_MAP[action]

        StockService.creer_mouvement(
            stock=stock,
            type_mouvement=type_mouvement,
            quantite=serializer.validated_data["quantite"],
            motif=serializer.validated_data.get("motif", ""),
            utilisateur=request.user if request.user.is_authenticated else None,
        )

        stock.refresh_from_db()

        # Broadcast WebSocket pour synchroniser les autres caisses
        # / WebSocket broadcast to sync other POS terminals
        from django.db import connection

        donnees_broadcast = [{
            "product_uuid": str(product.uuid),
            "quantite": stock.quantite,
            "unite": stock.unite,
            "en_alerte": stock.est_en_alerte(),
            "en_rupture": stock.est_en_rupture(),
            "bloquant": stock.est_en_rupture() and not stock.autoriser_vente_hors_stock,
            "quantite_lisible": _formater_stock_lisible(stock.quantite, stock.unite),
        }]
        broadcast_stock_update(donnees_broadcast)

        # Message de feedback / Feedback message
        label_action = {
            "reception": _("Réception"),
            "offert": _("Offert"),
            "perte": _("Perte"),
        }
        quantite_lisible = _formater_stock_lisible(stock.quantite, stock.unite)
        message = f"{label_action[action]} effectuée. Stock : {quantite_lisible}"

        context = _build_stock_context(product, stock, message_feedback=message)
        response = render(request, "laboutik/partial/article_panel_stock.html", context)
        response["HX-Trigger"] = "stockUpdated"
        return response
```

- [ ] **Step 4 : Ajouter les routes dans `laboutik/urls.py`**

Modifier `laboutik/urls.py`. Ajouter l'import et les routes :

```python
# laboutik/urls.py
from django.urls import path
from rest_framework import routers

from laboutik.views import (
    ArticlePanelViewSet,
    CaisseViewSet,
    CommandeViewSet,
    PaiementViewSet,
)

router = routers.DefaultRouter()
router.register(r'caisse', CaisseViewSet, basename='laboutik-caisse')
router.register(r'paiement', PaiementViewSet, basename='laboutik-paiement')
router.register(r'commande', CommandeViewSet, basename='laboutik-commande')

# Panel contextuel article — hors router DRF (URLs manuelles)
# / Article context panel — outside DRF router (manual URLs)
_panel = ArticlePanelViewSet.as_view({"get": "panel"})
_stock_detail = ArticlePanelViewSet.as_view({"get": "stock_detail"})
_stock_action = ArticlePanelViewSet.as_view({"post": "stock_action"})

urlpatterns = [
    path(
        "article-panel/<uuid:product_uuid>/panel/",
        _panel,
        name="article-panel",
    ),
    path(
        "article-panel/<uuid:product_uuid>/stock/",
        _stock_detail,
        name="article-panel-stock",
    ),
    path(
        "article-panel/<uuid:product_uuid>/stock/<str:action>/",
        _stock_action,
        name="article-panel-stock-action",
    ),
] + router.urls
```

- [ ] **Step 5 : Vérifier `manage.py check`**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: `System check identified no issues.`

---

### Task 5 : Template — menu principal du panel

**Files:**
- Create: `laboutik/templates/laboutik/partial/article_panel.html`

- [ ] **Step 1 : Créer le template du menu principal**

```html
{# article_panel.html — Menu principal du panel contextuel article
   / Article context panel main menu

   LOCALISATION : laboutik/templates/laboutik/partial/article_panel.html

   CONTEXTE :
     product  — instance Product
     has_stock — booléen (Stock existe pour ce produit)

   CHARGÉ PAR : ArticlePanelViewSet.panel() via htmx.ajax()
   INJECTÉ DANS : #article-panel (innerHTML)
#}
{% load i18n %}

<div class="panel-header">
    <span class="panel-title">{{ product.name }}</span>
    <button class="panel-close-btn"
            onclick="closeArticlePanel()"
            aria-label="{% translate 'Fermer' %}"
            data-testid="panel-close">
        ✕
    </button>
</div>

<div class="panel-body">
    {# Stock — actif seulement si le produit a un stock configuré
       / Stock — active only if the product has configured stock #}
    {% if has_stock %}
    <button class="panel-menu-btn"
            hx-get="/laboutik/article-panel/{{ product.uuid }}/stock/"
            hx-target="#article-panel"
            hx-swap="innerHTML"
            data-testid="panel-btn-stock">
        <span class="panel-menu-icon">📦</span>
        <span class="panel-menu-label">{% translate "Stock" %}</span>
    </button>
    {% else %}
    <button class="panel-menu-btn" disabled
            data-testid="panel-btn-stock-disabled">
        <span class="panel-menu-icon">📦</span>
        <span class="panel-menu-label">{% translate "Stock" %}</span>
        <span class="panel-menu-badge">{% translate "non configuré" %}</span>
    </button>
    {% endif %}

    {# Boutons futurs — désactivés (placeholder)
       / Future buttons — disabled (placeholder) #}
    <button class="panel-menu-btn" disabled data-testid="panel-btn-categorie">
        <span class="panel-menu-icon">🏷️</span>
        <span class="panel-menu-label">{% translate "Catégorie" %}</span>
        <span class="panel-menu-badge">{% translate "bientôt" %}</span>
    </button>

    <button class="panel-menu-btn" disabled data-testid="panel-btn-pdv">
        <span class="panel-menu-icon">🏪</span>
        <span class="panel-menu-label">{% translate "Point de vente" %}</span>
        <span class="panel-menu-badge">{% translate "bientôt" %}</span>
    </button>

    <button class="panel-menu-btn" disabled data-testid="panel-btn-prix">
        <span class="panel-menu-icon">💰</span>
        <span class="panel-menu-label">{% translate "Prix" %}</span>
        <span class="panel-menu-badge">{% translate "bientôt" %}</span>
    </button>

    <button class="panel-menu-btn" disabled data-testid="panel-btn-apparence">
        <span class="panel-menu-icon">🎨</span>
        <span class="panel-menu-label">{% translate "Apparence" %}</span>
        <span class="panel-menu-badge">{% translate "bientôt" %}</span>
    </button>

    <button class="panel-menu-btn" disabled data-testid="panel-btn-dupliquer">
        <span class="panel-menu-icon">📋</span>
        <span class="panel-menu-label">{% translate "Dupliquer" %}</span>
        <span class="panel-menu-badge">{% translate "bientôt" %}</span>
    </button>
</div>
```

---

### Task 6 : Template — vue stock détaillée

**Files:**
- Create: `laboutik/templates/laboutik/partial/article_panel_stock.html`

- [ ] **Step 1 : Créer le template de la vue stock**

```html
{# article_panel_stock.html — Vue stock détaillée + actions rapides
   / Detailed stock view + quick actions

   LOCALISATION : laboutik/templates/laboutik/partial/article_panel_stock.html

   CONTEXTE :
     product           — instance Product
     stock             — instance Stock
     quantite_lisible  — str ("12 L", "800 g", "3")
     seuil_lisible     — str (vide si pas de seuil)
     unite_saisie      — str ("cl", "g", "pièces")
     etat              — "ok" | "alerte" | "rupture"
     message_feedback  — str ou None (message succès après action)
     erreur_feedback   — str ou None (message erreur après action)

   CHARGÉ PAR :
     ArticlePanelViewSet.stock_detail() — GET
     ArticlePanelViewSet.stock_action() — POST (retourne ce même template)

   INJECTÉ DANS : #article-panel (innerHTML)
#}
{% load i18n %}

<div class="panel-header">
    <button class="panel-back-btn"
            hx-get="/laboutik/article-panel/{{ product.uuid }}/panel/"
            hx-target="#article-panel"
            hx-swap="innerHTML"
            data-testid="panel-back">
        ← {% translate "Retour" %}
    </button>
    <span class="panel-title" style="text-align: right;">{% translate "Stock" %}</span>
    <button class="panel-close-btn"
            onclick="closeArticlePanel()"
            aria-label="{% translate 'Fermer' %}">
        ✕
    </button>
</div>

<div class="panel-body">
    {# Message de feedback après action / Feedback message after action #}
    {% if message_feedback %}
    <div class="stock-feedback stock-feedback-success" data-testid="stock-feedback-success">
        {{ message_feedback }}
    </div>
    {% endif %}
    {% if erreur_feedback %}
    <div class="stock-feedback stock-feedback-error" data-testid="stock-feedback-error">
        {{ erreur_feedback }}
    </div>
    {% endif %}

    {# Informations stock / Stock information #}
    <div class="stock-info-card" data-testid="stock-info">
        <div style="font-weight: bold; font-size: 1.1rem; margin-bottom: 8px;">
            {{ product.name }}
        </div>
        <div class="stock-info-row">
            <span class="stock-info-label">{% translate "Stock actuel" %}</span>
            <span class="stock-info-value stock-badge-{{ etat }}"
                  data-testid="stock-quantite">
                {{ quantite_lisible }}
            </span>
        </div>
        {% if seuil_lisible %}
        <div class="stock-info-row">
            <span class="stock-info-label">{% translate "Seuil d'alerte" %}</span>
            <span class="stock-info-value">{{ seuil_lisible }}</span>
        </div>
        {% endif %}
    </div>

    <div class="stock-separator"></div>

    {# Formulaire actions stock / Stock action form
       Un seul formulaire, 3 boutons submit avec hx-post différent.
       / Single form, 3 submit buttons with different hx-post. #}
    <form id="stock-action-form">
        {% csrf_token %}

        <div class="stock-form-group">
            <label class="stock-form-label" for="stock-quantite-input">
                {% translate "Quantité" %}
            </label>
            <div class="stock-form-input-row">
                <input type="number"
                       id="stock-quantite-input"
                       name="quantite"
                       class="stock-form-input"
                       min="1"
                       value="1"
                       required
                       data-testid="stock-input-quantite">
                <span class="stock-form-unit">{{ unite_saisie }}</span>
            </div>
        </div>

        <div class="stock-form-group" style="margin-top: 4px;">
            <label class="stock-form-label" for="stock-motif-input">
                {% translate "Motif" %} <small style="opacity: 0.5;">({% translate "optionnel" %})</small>
            </label>
            <input type="text"
                   id="stock-motif-input"
                   name="motif"
                   class="stock-form-motif"
                   maxlength="200"
                   placeholder="{% translate 'Raison du mouvement...' %}"
                   data-testid="stock-input-motif">
        </div>

        <div class="stock-separator"></div>

        <div class="stock-actions-grid">
            <button type="submit"
                    class="stock-action-btn stock-action-btn-reception"
                    hx-post="/laboutik/article-panel/{{ product.uuid }}/stock/reception/"
                    hx-target="#article-panel"
                    hx-swap="innerHTML"
                    hx-include="#stock-action-form"
                    data-testid="stock-btn-reception">
                + {% translate "Réception" %}
            </button>
            <button type="submit"
                    class="stock-action-btn stock-action-btn-offert"
                    hx-post="/laboutik/article-panel/{{ product.uuid }}/stock/offert/"
                    hx-target="#article-panel"
                    hx-swap="innerHTML"
                    hx-include="#stock-action-form"
                    data-testid="stock-btn-offert">
                🎁 {% translate "Offert" %}
            </button>
            <button type="submit"
                    class="stock-action-btn stock-action-btn-perte"
                    hx-post="/laboutik/article-panel/{{ product.uuid }}/stock/perte/"
                    hx-target="#article-panel"
                    hx-swap="innerHTML"
                    hx-include="#stock-action-form"
                    data-testid="stock-btn-perte">
                ⚠ {% translate "Perte" %}
            </button>
        </div>
    </form>

    <div class="stock-separator"></div>

    {# Lien vers l'admin Stock / Link to admin Stock #}
    <a href="/adminstaff/inventaire/stock/{{ stock.pk }}/change/"
       class="stock-admin-link"
       target="_blank"
       data-testid="stock-admin-link">
        {% translate "Voir dans l'admin" %} ↗
    </a>
</div>
```

---

### Task 7 : Tests pytest — vues panel

**Files:**
- Create: `tests/pytest/test_longpress_panel.py`

- [ ] **Step 1 : Écrire les tests**

```python
"""
Tests pour le panel contextuel article POS (long press).
/ Tests for the POS article context panel (long press).

LOCALISATION : tests/pytest/test_longpress_panel.py

Couvre :
- GET panel (menu principal)
- GET stock detail
- POST stock action (reception, offert, perte)
- Validation (quantite invalide, action invalide)
- Produit sans stock
"""

import uuid as uuid_module

import pytest
from django.test import RequestFactory
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import Product
from inventaire.models import Stock, UniteStock


TENANT_SCHEMA = "demo"


@pytest.fixture
def admin_user():
    """Crée un admin pour les requêtes authentifiées."""
    with schema_context(TENANT_SCHEMA):
        user, _ = TibilletUser.objects.get_or_create(
            email="admin-panel-test@test.local",
            defaults={"is_staff": True, "is_active": True},
        )
        return user


@pytest.fixture
def product_with_stock():
    """Crée un produit avec stock pour les tests."""
    with schema_context(TENANT_SCHEMA):
        product = Product.objects.create(
            name="Bière Test Panel",
            publish=True,
        )
        stock = Stock.objects.create(
            product=product,
            quantite=500,
            unite=UniteStock.CL,
            seuil_alerte=200,
        )
        return product, stock


@pytest.fixture
def product_without_stock():
    """Crée un produit sans stock."""
    with schema_context(TENANT_SCHEMA):
        product = Product.objects.create(
            name="Coca Test Panel",
            publish=True,
        )
        return product


@pytest.fixture
def factory():
    return RequestFactory()


@pytest.mark.django_db
class TestArticlePanelMenu:
    """Tests pour le menu principal du panel (GET panel/)."""

    def test_panel_avec_stock(self, factory, admin_user, product_with_stock):
        """Le menu affiche le bouton Stock actif si le produit a un stock."""
        product, stock = product_with_stock
        with schema_context(TENANT_SCHEMA):
            from laboutik.views import ArticlePanelViewSet

            view = ArticlePanelViewSet.as_view({"get": "panel"})
            request = factory.get(f"/laboutik/article-panel/{product.uuid}/panel/")
            request.user = admin_user

            response = view(request, product_uuid=product.uuid)

            assert response.status_code == 200
            content = response.content.decode()
            assert 'data-testid="panel-btn-stock"' in content
            assert "hx-get" in content

    def test_panel_sans_stock(self, factory, admin_user, product_without_stock):
        """Le menu affiche le bouton Stock désactivé si pas de stock."""
        product = product_without_stock
        with schema_context(TENANT_SCHEMA):
            from laboutik.views import ArticlePanelViewSet

            view = ArticlePanelViewSet.as_view({"get": "panel"})
            request = factory.get(f"/laboutik/article-panel/{product.uuid}/panel/")
            request.user = admin_user

            response = view(request, product_uuid=product.uuid)

            assert response.status_code == 200
            content = response.content.decode()
            assert 'data-testid="panel-btn-stock-disabled"' in content

    def test_panel_produit_inexistant(self, factory, admin_user):
        """404 si le produit n'existe pas."""
        with schema_context(TENANT_SCHEMA):
            from laboutik.views import ArticlePanelViewSet

            view = ArticlePanelViewSet.as_view({"get": "panel"})
            fake_uuid = uuid_module.uuid4()
            request = factory.get(f"/laboutik/article-panel/{fake_uuid}/panel/")
            request.user = admin_user

            response = view(request, product_uuid=fake_uuid)
            assert response.status_code == 404


@pytest.mark.django_db
class TestArticlePanelStock:
    """Tests pour la vue stock détaillée (GET stock/)."""

    def test_stock_detail(self, factory, admin_user, product_with_stock):
        """La vue stock affiche la quantité et les boutons d'action."""
        product, stock = product_with_stock
        with schema_context(TENANT_SCHEMA):
            from laboutik.views import ArticlePanelViewSet

            view = ArticlePanelViewSet.as_view({"get": "stock_detail"})
            request = factory.get(f"/laboutik/article-panel/{product.uuid}/stock/")
            request.user = admin_user

            response = view(request, product_uuid=product.uuid)

            assert response.status_code == 200
            content = response.content.decode()
            # 500 cl = 5 L
            assert "5 L" in content
            assert 'data-testid="stock-btn-reception"' in content
            assert 'data-testid="stock-btn-offert"' in content
            assert 'data-testid="stock-btn-perte"' in content

    def test_stock_detail_sans_stock(self, factory, admin_user, product_without_stock):
        """404 si le produit n'a pas de stock."""
        product = product_without_stock
        with schema_context(TENANT_SCHEMA):
            from laboutik.views import ArticlePanelViewSet

            view = ArticlePanelViewSet.as_view({"get": "stock_detail"})
            request = factory.get(f"/laboutik/article-panel/{product.uuid}/stock/")
            request.user = admin_user

            response = view(request, product_uuid=product.uuid)
            assert response.status_code == 404


@pytest.mark.django_db
class TestArticlePanelStockActions:
    """Tests pour les actions stock (POST stock/{action}/)."""

    def test_reception(self, factory, admin_user, product_with_stock):
        """POST reception ajoute du stock et retourne la vue mise à jour."""
        product, stock = product_with_stock
        with schema_context(TENANT_SCHEMA):
            from unittest.mock import patch

            from laboutik.views import ArticlePanelViewSet

            view = ArticlePanelViewSet.as_view({"post": "stock_action"})
            request = factory.post(
                f"/laboutik/article-panel/{product.uuid}/stock/reception/",
                data={"quantite": "100", "motif": "Livraison test"},
            )
            request.user = admin_user

            with patch("laboutik.views.broadcast_stock_update"):
                response = view(
                    request,
                    product_uuid=product.uuid,
                    action="reception",
                )

            assert response.status_code == 200
            assert response.get("HX-Trigger") == "stockUpdated"

            stock.refresh_from_db()
            # 500 + 100 = 600 cl
            assert stock.quantite == 600

    def test_perte(self, factory, admin_user, product_with_stock):
        """POST perte retire du stock."""
        product, stock = product_with_stock
        with schema_context(TENANT_SCHEMA):
            from unittest.mock import patch

            from laboutik.views import ArticlePanelViewSet

            view = ArticlePanelViewSet.as_view({"post": "stock_action"})
            request = factory.post(
                f"/laboutik/article-panel/{product.uuid}/stock/perte/",
                data={"quantite": "50", "motif": "Casse"},
            )
            request.user = admin_user

            with patch("laboutik.views.broadcast_stock_update"):
                response = view(
                    request,
                    product_uuid=product.uuid,
                    action="perte",
                )

            assert response.status_code == 200
            stock.refresh_from_db()
            # 500 - 50 = 450 cl
            assert stock.quantite == 450

    def test_offert(self, factory, admin_user, product_with_stock):
        """POST offert retire du stock."""
        product, stock = product_with_stock
        with schema_context(TENANT_SCHEMA):
            from unittest.mock import patch

            from laboutik.views import ArticlePanelViewSet

            view = ArticlePanelViewSet.as_view({"post": "stock_action"})
            request = factory.post(
                f"/laboutik/article-panel/{product.uuid}/stock/offert/",
                data={"quantite": "25"},
            )
            request.user = admin_user

            with patch("laboutik.views.broadcast_stock_update"):
                response = view(
                    request,
                    product_uuid=product.uuid,
                    action="offert",
                )

            assert response.status_code == 200
            stock.refresh_from_db()
            # 500 - 25 = 475 cl
            assert stock.quantite == 475

    def test_action_invalide(self, factory, admin_user, product_with_stock):
        """Une action non autorisée retourne 400."""
        product, stock = product_with_stock
        with schema_context(TENANT_SCHEMA):
            from laboutik.views import ArticlePanelViewSet

            view = ArticlePanelViewSet.as_view({"post": "stock_action"})
            request = factory.post(
                f"/laboutik/article-panel/{product.uuid}/stock/ajustement/",
                data={"quantite": "10"},
            )
            request.user = admin_user

            response = view(
                request,
                product_uuid=product.uuid,
                action="ajustement",
            )
            assert response.status_code == 400

    def test_quantite_invalide(self, factory, admin_user, product_with_stock):
        """Quantité 0 ou négative retourne le formulaire avec erreur."""
        product, stock = product_with_stock
        with schema_context(TENANT_SCHEMA):
            from laboutik.views import ArticlePanelViewSet

            view = ArticlePanelViewSet.as_view({"post": "stock_action"})
            request = factory.post(
                f"/laboutik/article-panel/{product.uuid}/stock/reception/",
                data={"quantite": "0"},
            )
            request.user = admin_user

            response = view(
                request,
                product_uuid=product.uuid,
                action="reception",
            )

            assert response.status_code == 200
            content = response.content.decode()
            assert 'data-testid="stock-feedback-error"' in content
            # Stock inchangé
            stock.refresh_from_db()
            assert stock.quantite == 500
```

- [ ] **Step 2 : Lancer les tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_longpress_panel.py -v
```

Expected: tous les tests passent.

---

### Task 8 : Test manuel end-to-end

- [ ] **Step 1 : Lancer le serveur**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002
```

- [ ] **Step 2 : Tester dans le navigateur**

1. Aller sur le POS (`/laboutik/caisse/`)
2. Se connecter avec une carte primaire
3. Sélectionner un point de vente
4. **Clic court** sur un article → l'article est ajouté au panier (comportement inchangé)
5. **Appui long** (600ms) sur un article → le panel latéral slide depuis la droite
6. Vérifier le menu : bouton Stock actif, 5 boutons grisés "bientôt"
7. Cliquer sur Stock → la vue stock s'affiche avec quantité et formulaire
8. Saisir une quantité (ex: 5) et cliquer "+ Réception" → feedback succès, quantité mise à jour
9. Cliquer "← Retour" → retour au menu principal
10. Cliquer le backdrop (zone sombre) → le panel se ferme
11. Cliquer ✕ → le panel se ferme
12. **Tester sur un article SANS stock** → le bouton Stock est grisé avec "non configuré"

- [ ] **Step 3 : Tester la responsivité**

1. Réduire la fenêtre à < 768px → le panel prend 100% de la largeur
2. Agrandir → le panel reprend 40%

---

## Dépendances entre tâches

```
Task 1 (longpress.js)     ─┐
Task 2 (CSS)               ├─→ Task 3 (HTML + intégration) ─→ Task 8 (test manuel)
Task 4 (views + urls)      ─┤
Task 5 (template menu)     ─┤
Task 6 (template stock)    ─┘
Task 7 (tests pytest)      ← dépend de Task 4
```

Tasks 1, 2, 4, 5, 6 sont indépendantes et peuvent être faites en parallèle.
Task 3 les assemble.
Task 7 teste Task 4.
Task 8 teste l'ensemble.
