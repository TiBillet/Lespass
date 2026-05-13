# Spec — Explorer in-tenant pour `/federation/` (Réseau local) + refactor explorer.js solide pour prod

**Date :** 2026-05-13
**Auteur :** JonasFW13 (brainstorming avec Claude)
**Statut :** Validé, prêt pour writing-plans
**Contexte :** Suite du chantier M-To-V2 #02 (port app `seo/`). On rend l'explorer SEO accessible depuis chaque tenant sur l'URL `/federation/`, ET on profite du chantier pour solidifier le code de la carte pour la prod.

---

## Objectif

1. **Fonctionnel** : remplacer le contenu actuel de la page "Réseau local" (`/federation/` sur chaque tenant) par une vue de type explorer (carte Leaflet + liste filtrée), restreinte au tenant courant + ses lieux fédérés via `FederatedPlace`.
2. **Technique** : consolider le code de l'explorer (JS, CSS, widget HTML, builder data) en une **source unique** utilisée à la fois par le public `/explorer/` et par chaque tenant `/federation/`. Refactoriser le JS pour la prod (FALC, stable, pérenne).

Le label "Réseau local" dans la navbar et la condition de visibilité (`config.module_federation` + présence de `FederatedPlace` ou `AssetFedowPublic` fédéré) sont conservés à l'identique.

---

## Architecture source-unique

```
seo/
├── static/seo/
│   ├── vendor/leaflet/{leaflet,markercluster}.{css,js}   ← 1 fois (vendorisé)
│   ├── explorer.css                                       ← 1 fois (cleanup CSS mort)
│   └── explorer.js                                        ← 1 fois (IIFE refactoré)
├── services.py
│   └── build_explorer_data_for_tenants(uuids: list[str])  ← 1 fois (paramétré)
└── templates/seo/partials/
    └── explorer_widget.html                               ← 1 fois (HTML widget)
```

Deux wrappers triviaux (15-20 lignes, zéro logique) plug le widget dans le bon `base_template` :

| Wrapper | Étend | Périmètre data |
|---|---|---|
| `seo/templates/seo/explorer.html` | `seo/base.html` | Tous tenants (build_explorer_data_for_tenants(all_uuids)) |
| `BaseBillet/templates/reunion/views/federation/explorer.html` | `base_template` (skin du tenant) | tenant courant + FederatedPlace |

Les skins `faire_festival` / `htmx` n'ont pas leur propre wrapper : fallback automatique sur reunion via `get_skin_template()`.

---

## Périmètre fonctionnel (tenant `/federation/`)

### URL & visibilité

| Aspect | Comportement |
|---|---|
| URL | `/federation/` (inchangée) |
| Vue Python | `BaseBillet.views.FederationViewset.list()` (même méthode, contenu réécrit) |
| Condition d'affichage navbar | `config.module_federation AND (FederatedPlace.exists() OR AssetFedowPublic federated exists)` — inchangée |
| Label navbar | "Réseau local" — inchangé |
| État vide | Si aucune `FederatedPlace`, la page rend la carte avec le tenant courant seul + message *"Aucune autre place fédérée pour le moment."* |

### Données affichées (tenant)

```python
federated_uuids = {
    str(fp.tenant.uuid)
    for fp in FederatedPlace.objects.select_related('tenant').all()
}
federated_uuids.add(str(connection.tenant.uuid))  # le tenant courant inclus
sorted_uuids = sorted(federated_uuids)            # ordre stable
explorer_data = build_explorer_data_for_tenants(sorted_uuids)
```

Le tenant courant apparaît sur la carte avec un marker visuellement différent (classe CSS `explorer-pin--current`, couleur primaire).

**Hors scope** :
- `AssetFedowPublic` (monnaies locales) — pas affichées sur la carte, aligné avec le port allégé du SEO public.
- Tag filters (`include_tags`, `exclude_tags`, `membership_visible`) de `FederatedPlace` — non appliqués sur les events de l'explorer dans cette V1.

---

## Refactor explorer.js — 7 chantiers de solidification prod

### 1. Module IIFE — zéro pollution `window`

```js
(function () {
    'use strict';

    const config = { /* lu depuis #explorer-root data-* */ };
    const state = { data: null, filters: {}, map: null, markers: {}, view: 'list' };
    const dom = { root: null, list: null, map: null, search: null, pills: null };

    // ... functions ...

    function init() { ... }
    function destroy() { /* expose pour cleanup HTMX/SPA futur */ }

    document.addEventListener('DOMContentLoaded', init);
})();
```

### 2. Event delegation — zéro `onclick=` inline

Un listener sur `dom.list` qui délègue selon `closest('[data-...]')`. Idem pour `dom.pills`. Compatible CSP stricte, facile à grep, scalable.

### 3. Vendor Leaflet (plus de CDN unpkg.com)

```
seo/static/seo/vendor/leaflet/
├── leaflet.js
├── leaflet.css
├── markercluster.js
├── markercluster.css
└── images/ (default marker icons Leaflet)
```

Versions : Leaflet 1.9.4 + Leaflet.markercluster 1.5.3. ~250 KB total. Plus de dépendance CDN externe en prod.

### 4. Plus de timing magique

Remplacement de `setTimeout(() => marker.openPopup(), 400)` par un event Leaflet :

```js
function focusOnLieu(tenantId) {
    const marker = state.markers[tenantId];
    if (!marker) return;

    state.map.setView(marker.getLatLng(), 15, { animate: true });

    // Attendre la fin de l'animation cluster pour ouvrir le popup
    // / Wait for cluster animation end before opening popup
    state.markerCluster.once('animationend', () => marker.openPopup());
}
```

Si l'event n'est pas garanti dans tous les cas, fallback minimum 100ms (réduit) + check `marker.isPopupOpen()`.

### 5. i18n via `data-i18n-*` sur la racine

```django
<div id="explorer-root"
     data-current-tenant-uuid="{{ current_tenant_uuid|default:'' }}"
     data-i18n-empty="{% translate 'Aucun résultat trouvé.' %}"
     data-i18n-visit="{% translate 'Visiter le lieu' %}"
     data-i18n-lieu="{% translate 'Lieu' %}"
     data-i18n-event="{% translate 'Événement' %}"
     data-i18n-all="{% translate 'Tous' %}"
     data-i18n-current="{% translate 'Vous êtes ici' %}">
```

JS lit `config.i18n.empty`, `config.i18n.visit`, etc. depuis `dom.root.dataset`. Toutes les traductions Django prises en compte.

### 6. Garde-fous défensifs

- `try/catch` sur `JSON.parse` de `#explorer-data`. En cas d'erreur : log console + affiche état vide gracieux.
- Vérif présence DOM elements (`if (!dom.root || !dom.list) return;`).
- Skip silencieux des lieux avec coords invalides (`isNaN(lat) || isNaN(lng)`).
- `escapeHtml()` systématique sur les strings injectées dans innerHTML.

### 7. Header de fichier + commentaires bilingues FR/EN

```js
/**
 * EXPLORER — carte Leaflet + liste filtrée + toggle mobile.
 * / EXPLORER — Leaflet map + filtered list + mobile toggle.
 *
 * LOCALISATION : seo/static/seo/explorer.js
 * UTILISÉ PAR : public /explorer/ + tenant /federation/ (même code, même comportement).
 *
 * USAGE :
 *   1. Inclure leaflet.css + markercluster.css en <head>
 *   2. Inclure leaflet.js + markercluster.js + explorer.js en fin de <body>
 *   3. Rendre dans le template : { explorer-root, explorer-list, explorer-map,
 *      <script id="explorer-data" type="application/json"> }
 *
 * DATA FLOW :
 *   1. init() lit #explorer-data (JSON) + #explorer-root (data-i18n-*, data-current-tenant-uuid)
 *   2. bindControls() attache 1 listener delegated sur #explorer-list + 1 sur #explorer-pills
 *   3. applyFilters() filtre data → renderList() + updateMarkers()
 *   4. Click carte → focusOnLieu() : zoom + popup + accordéon
 *
 * STATE (encapsulé, jamais sur window) :
 *   - state.data : { lieux: [...], events: [...] }  (immutable après init)
 *   - state.filters : { text: '', category: 'all' }  (muable)
 *   - state.map, state.markers, state.markerCluster : objets Leaflet
 *
 * DEPENDANCES :
 *   - Leaflet 1.9.x  (vendoré dans /static/seo/vendor/leaflet/)
 *   - Leaflet.markercluster 1.5.x  (idem)
 *   - Bootstrap 5.3 icons (pour les <i class="bi-*">)
 *
 * TEARDOWN :
 *   destroy() expose un cleanup map + listeners pour swap HTMX/SPA futur.
 */
```

Chaque fonction longue (>20 lignes) a un mini-bloc bilingue avec FLUX. Chaque section délimitée par un séparateur visuel ASCII.

### Bonus : marker spécial pour le tenant courant

```js
const isCurrent = lieu.tenant_id === config.currentTenantUuid;
const pinClass = 'explorer-pin' + (isCurrent ? ' explorer-pin--current' : '');
const icon = L.divIcon({
    className: '',
    html: '<div class="' + pinClass + '" data-lieu-id="' + escapeHtml(lieu.tenant_id) + '">'
        + escapeHtml(lieu.name) + '</div>',
});
```

CSS associé :
```css
.explorer-pin--current {
    background: var(--bs-primary);
    color: #fff;
    box-shadow: 0 0 0 3px rgba(var(--bs-primary-rgb), 0.25);
}
```

Si `data-current-tenant-uuid` est vide (cas du public ROOT), aucun marker n'a la classe — comportement identique à aujourd'hui.

---

## Backend — vue & services

### `seo/services.py`

**Refactor** :
- `build_explorer_data()` → wrapper qui appelle `build_explorer_data_for_tenants(all_uuids)` où `all_uuids = [l['tenant_id'] for l in AGGREGATE_LIEUX]`. Comportement identique à aujourd'hui.
- **Nouvelle** `build_explorer_data_for_tenants(tenant_uuids: list[str]) -> dict` :
  - Lit `SEOCache.AGGREGATE_LIEUX` + `AGGREGATE_EVENTS` via `get_seo_cache()`
  - Filtre `lieux` sur `lieu['tenant_id'] in tenant_uuids`
  - Filtre `events` idem
  - Imbrique events sous chaque lieu (logique existante préservée)
  - Retourne `{lieux: [...], events: [...]}`

### `BaseBillet/views.py::FederationViewset.list()`

**Réécriture** (~20 lignes) :
```python
def list(self, request):
    config = Configuration.get_solo()
    federated_uuids = {
        str(fp.tenant.uuid)
        for fp in FederatedPlace.objects.select_related('tenant').all()
    }
    federated_uuids.add(str(connection.tenant.uuid))
    sorted_uuids = sorted(federated_uuids)
    explorer_data = build_explorer_data_for_tenants(sorted_uuids)

    template_context = get_context(request)
    template_context.update({
        'explorer_data': explorer_data,
        'current_tenant_uuid': str(connection.tenant.uuid),
        'page_title': _('Réseau local'),
    })

    template_path = get_skin_template(config, "views/federation/explorer.html")
    return render(request, template_path, context=template_context)
```

### `seo/views.py::explorer()` (public)

Inchangée fonctionnellement. Ajoute juste `current_tenant_uuid=''` au contexte (vide → pas de highlight, comportement actuel préservé).

---

## Frontend — widget partagé

### `seo/templates/seo/partials/explorer_widget.html` (nouveau)

Structure (~50 lignes) :
- Racine `<div id="explorer-root">` avec tous les `data-i18n-*` + `data-current-tenant-uuid`
- Toolbar : input search + pills + counter
- Container : `#explorer-list` + `#explorer-map` (avec spinner loading)
- `{{ explorer_data|json_script:"explorer-data" }}`
- FAB inclus dans le widget (position:fixed marche tant qu'aucun ancêtre n'a `transform`, et c'est le cas dans nos 2 wrappers)

### Wrappers

**`seo/templates/seo/explorer.html`** (public, simplifié) :
```django
{% extends "seo/base.html" %}
{% load static i18n %}

{% block extra_head %}
    <meta name="robots" content="noindex, nofollow">
    <link rel="stylesheet" href="{% static 'seo/vendor/leaflet/leaflet.css' %}">
    <link rel="stylesheet" href="{% static 'seo/vendor/leaflet/markercluster.css' %}">
    <link rel="stylesheet" href="{% static 'seo/explorer.css' %}">
{% endblock %}

{% block main_wrapper %}
    {% include "seo/partials/explorer_widget.html" %}
{% endblock %}

{% block extra_js %}
    <script src="{% static 'seo/vendor/leaflet/leaflet.js' %}"></script>
    <script src="{% static 'seo/vendor/leaflet/markercluster.js' %}"></script>
    <script src="{% static 'seo/explorer.js' %}"></script>
{% endblock %}
```

**`BaseBillet/templates/reunion/views/federation/explorer.html`** (tenant) :
```django
{% extends base_template %}
{% load static i18n %}

{% block extra_head %}
    <link rel="stylesheet" href="{% static 'seo/vendor/leaflet/leaflet.css' %}">
    <link rel="stylesheet" href="{% static 'seo/vendor/leaflet/markercluster.css' %}">
    <link rel="stylesheet" href="{% static 'seo/explorer.css' %}">
{% endblock %}

{% block main %}
    {% include "seo/partials/explorer_widget.html" %}
{% endblock %}

{% block extra_js %}
    <script src="{% static 'seo/vendor/leaflet/leaflet.js' %}"></script>
    <script src="{% static 'seo/vendor/leaflet/markercluster.js' %}"></script>
    <script src="{% static 'seo/explorer.js' %}"></script>
{% endblock %}
```

---

## CSS — cleanup

Dans `seo/static/seo/explorer.css`, retirer les classes mortes (héritées du clone V2, jamais utilisées en V1) :
- `.lieu-asset-badges`, `.lieu-asset-badge`, `.lieu-asset-badge--active`
- `.explorer-asset-legend*`
- `.explorer-pin--dimmed`
- `.explorer-card-icon.asset`, `.explorer-card-icon.membership`, `.explorer-card-icon.initiative`
- `.explorer-badge.asset`, `.explorer-badge.membership`, `.explorer-badge.initiative`
- `.explorer-card--asset`, `.explorer-card[data-type="asset"]*`
- `.explorer-card--active` (asset focus state)

Ajouter :
- `.explorer-pin--current` (cf. section bonus marker)

Estimation : -200 lignes de CSS morte.

---

## Suppression de code

À la fin du chantier :
- **Supprimer** `BaseBillet/templates/reunion/views/federation/list.html`
- Vérifier au préalable via `rg "federation/list" BaseBillet/ Administration/` qu'aucun `{% include %}` / `{% extends %}` / `reverse()` ne s'y réfère.
- Si rien ne pointe vers : suppression. Sinon, adapter d'abord.

---

## Tests de non-régression Chrome (CRITIQUE)

> ⚠️ Le code de la carte fonctionne déjà aujourd'hui sur `https://tibillet.localhost/explorer/`. On le refactore — donc **test manuel sur Chrome obligatoire** avant de considérer le chantier terminé. Liste exhaustive à valider :

### Public `/explorer/` (régression — doit marcher comme avant)

1. **Carte se charge** : tuiles CartoDB visibles, spinner disparaît
2. **Markers présents** : 5+ markers clusterés sur Villeurbanne
3. **Click marker** : popup s'ouvre avec titre + events + lien "Visiter le lieu"
4. **Click card lieu dans la liste** : carte zoome + popup ouvre + accordéon ouvre + scroll vers la card
5. **Click card event** : focus sur le lieu parent
6. **Filtre texte** : "tap" → liste se filtre + markers se filtrent
7. **Filtre pills** : "Lieux" → seuls les lieux affichés, "Événements" → seuls les events
8. **Accordéon lieu** : click → ouvre, click sur un autre lieu → ferme le premier
9. **Mobile (< 992px)** : FAB visible, bascule liste ↔ carte
10. **Mobile zoom** : click event → bascule en mode carte automatiquement
11. **Aucun marker `--current`** sur le public (pas de tenant courant)

### Tenant `/federation/` (nouveau — vérifier que ça marche)

1. **Navbar** : "Réseau local" visible si `module_federation=True` + FederatedPlace existe
2. **Navbar** : "Réseau local" caché sinon
3. **Page rendue** : skin du tenant (navbar tenant, footer tenant)
4. **Carte** : montre tenant courant + ses FederatedPlace, et **rien d'autre**
5. **Marker du tenant courant** : visuellement distinct (couleur primaire)
6. **Click marker tenant courant** : popup avec son nom + ses events
7. **Filtres** : même comportement que public
8. **État vide** : si pas de FederatedPlace, tenant courant seul, message OK
9. **Retour au tenant** : la navbar du tenant permet de revenir à `/event/`, `/memberships/`, etc.

### Console DevTools (les deux contextes)

10. **Aucune erreur JS** au chargement
11. **Aucune warning Leaflet** (sauf info benignes)
12. **Aucune fuite `window.*`** : taper `window.explorerData`, `window.map`, `window.markers` → tous `undefined`
13. **Réseau** : tous les assets Leaflet servis depuis `/static/seo/vendor/leaflet/`, **plus aucun appel à unpkg.com**

### Performance

14. **Premier paint < 2s** sur connexion locale
15. **Filtre texte** : pas de lag visible (debounce 300ms appliqué)

---

## Data flow (synthèse visuelle)

```
[ /explorer/ public ]                  [ /federation/ tenant ]
        │                                       │
        ▼                                       ▼
seo.views.explorer()              BaseBillet.views.FederationViewset.list()
        │                                       │
        │ all_uuids = tous lieux SEOCache       │ federated_uuids = FP + connection.tenant
        ▼                                       ▼
        └─────────────────┬─────────────────────┘
                          ▼
         seo.services.build_explorer_data_for_tenants(uuids)
                          │
                          ▼   (lit SEOCache via get_seo_cache)
                  {lieux, events filtrés}
                          │
                          ▼
                contexte Django + render(...)
                          │
                          ▼
   {% include "seo/partials/explorer_widget.html" %}
                          │
                          ▼
       Browser : Leaflet (vendor) + explorer.js (IIFE)
                          │
                          ▼
                Map + liste + filtres OK
```

---

## Fichiers touchés

| Type | Fichier | Action |
|---|---|---|
| **Vue** | `BaseBillet/views.py::FederationViewset.list` | Réécriture (~20 lignes) |
| **Service** | `seo/services.py` | Ajout `build_explorer_data_for_tenants()`, refactor `build_explorer_data()` en wrapper |
| **Vue public** | `seo/views.py::explorer()` | Ajout `current_tenant_uuid=''` au contexte |
| **Template widget** | `seo/templates/seo/partials/explorer_widget.html` | Création (~50 lignes) |
| **Template wrapper public** | `seo/templates/seo/explorer.html` | Réécriture simplifiée (~20 lignes, utilise le widget) |
| **Template wrapper tenant** | `BaseBillet/templates/reunion/views/federation/explorer.html` | Création (~20 lignes) |
| **Template à supprimer** | `BaseBillet/templates/reunion/views/federation/list.html` | Suppression après vérif |
| **JS** | `seo/static/seo/explorer.js` | Réécriture complète (IIFE + 7 chantiers de solidification) |
| **CSS** | `seo/static/seo/explorer.css` | Cleanup classes mortes (-200 lignes), ajout `.explorer-pin--current` |
| **Vendor** | `seo/static/seo/vendor/leaflet/` | Ajout : leaflet.{js,css}, markercluster.{js,css}, images/ |

---

## Décisions & adaptations (synthèse)

| Question | Décision | Justification |
|---|---|---|
| URL tenant | `/federation/` inchangée | Surface minimale, liens internes préservés |
| In-tenant vs redirect | In-tenant | UX continue, skin du tenant conservé |
| Périmètre data tenant | tenant courant + ses FederatedPlace | Sémantique "réseau local" respectée |
| Highlight tenant courant | Marker `--current` (couleur primaire) | Demandé par user |
| Source unique JS/CSS/widget/data | Oui, dans `seo/` | Demandé par user, évite drift |
| Templates par skin | Un wrapper reunion, fallback via `get_skin_template()` | Demandé par user |
| Tag filters FederatedPlace | Ignorés sur events | Simplification V1 |
| Tests | Hors scope de ce chantier (sauf non-régression Chrome manuelle) | À traiter dans chantier "Import tests V2" |
| AssetFedowPublic sur carte | Non | Aligné avec port SEO allégé |
| Footer "Le réseau local" | Inchangé | Mini-chantier UI séparé si besoin |
| Refactor explorer.js | Oui, 7 chantiers | Code prod-grade FALC pérenne |
| Vendor Leaflet | Oui, plus de CDN | Indépendance prod |
| Inline onclick | Supprimés (event delegation) | CSP-friendly, testable |
| i18n strings JS | Via `data-i18n-*` sur root | Django traduit tout |

---

## Hors scope (futures itérations possibles)

- Tag filtering sur events affichés
- Asset/monnaie locale sur la carte (porté en V1 si fedow_core arrive)
- Footer "Le réseau local" simplifié en lien unique vers `/federation/`
- Tests E2E Playwright (chantier "Import tests V2")
- Détection collision tenant_uuid manquant en SEOCache (refresh récent)

---

## Critères d'acceptation

1. `https://tibillet.localhost/explorer/` (public) marche exactement comme avant — **liste exhaustive Chrome 1-15 ci-dessus validée**
2. `https://lespass.tibillet.localhost/federation/` rend l'explorer avec tenant courant + FederatedPlace
3. L'entrée "Réseau local" dans la navbar reste contrôlée par `module_federation` + existence de FederatedPlace/AssetFedowPublic fédéré (inchangé)
4. L'ancien template `list.html` supprimé sans casser de référence (`rg` propre)
5. `manage.py check` passe sans erreur
6. Console DevTools propre dans les 2 contextes (aucune erreur JS, aucun `window.*` polluant, aucun appel CDN externe)
7. Code JS suit FALC : header complet, sections délimitées, commentaires bilingues FR/EN, noms verbeux, IIFE, event delegation, garde-fous
