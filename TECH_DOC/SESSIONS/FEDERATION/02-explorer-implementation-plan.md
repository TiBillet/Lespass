# Explorer in-tenant + refactor JS prod — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre l'explorer SEO accessible depuis chaque tenant sur `/federation/`, en partageant 100% du code metier (JS, CSS, widget HTML, data builder) avec le public `/explorer/`, et profiter du chantier pour solidifier le JS pour la prod (IIFE, event delegation, vendor Leaflet, i18n, garde-fous).

**Architecture:** Source unique pour explorer.{js,css}, widget HTML partial, et `build_explorer_data_for_tenants()` parametre. Deux wrappers triviaux (15 lignes chacun) plug le widget dans `seo/base.html` (public) et `reunion/base.html` (tenant). Le JS est entierement encapsule dans une IIFE, ne pollue pas window, utilise event delegation. Leaflet vendore localement.

**Tech Stack:** Django 4.2 + django-tenants, Leaflet 1.9.4 + Leaflet.markercluster 1.5.3 (vendores), Bootstrap 5.3, SEOCache (deja en place).

**Spec source :** `TECH DOC/SESSIONS/FEDERATION/01-explorer-in-tenants-design.md`

**Note Git :** Sur ce projet le mainteneur gere tous les commits manuellement. Les "Commits" mentionnes a la fin des tasks sont des messages **suggeres** que Claude n'execute PAS — il les rapporte au mainteneur.

**Note Tests :** Pas de tests automatises dans ce chantier. La validation se fait par **non-regression Chrome manuelle** sur la liste exhaustive (cf. spec section "Tests de non-regression Chrome"). Les tests pytest/Playwright sont traites dans un chantier separe "Import tests V2".

---

## File Structure

| Fichier | Responsabilite |
|---|---|
| `seo/services.py` | Ajout `build_explorer_data_for_tenants(uuids)` parametree + wrapper retrocompat `build_explorer_data()` |
| `seo/views.py` | `explorer()` ajoute `current_tenant_uuid=''` au contexte |
| `BaseBillet/views.py` | Reecriture de `FederationViewset.list()` pour rendre le widget explorer |
| `seo/static/seo/vendor/leaflet/` | Vendor Leaflet 1.9.4 + markercluster 1.5.3 (binaires + CSS + images) |
| `seo/static/seo/explorer.js` | Reecriture IIFE + 7 chantiers de solidification |
| `seo/static/seo/explorer.css` | Cleanup -200 lignes CSS mort + ajout `.explorer-pin--current` |
| `seo/templates/seo/partials/explorer_widget.html` | **Creation** : widget HTML partage |
| `seo/templates/seo/explorer.html` | Reecriture simplifiee : extends `seo/base.html` + include widget |
| `BaseBillet/templates/reunion/views/federation/explorer.html` | **Creation** : extends `base_template` + include widget |
| `BaseBillet/templates/reunion/views/federation/list.html` | **Suppression** apres verif aucune reference |

---

## Task 1 : Refactor `build_explorer_data()` en wrapper

**Files:**
- Modify: `seo/services.py` (fonction `build_explorer_data` actuelle, lignes 558-685 environ — depend de l'etat actuel)

- [ ] **Step 1.1 : Lire le code actuel**

```bash
docker exec lespass_django cat /DjangoFiles/seo/services.py | grep -n "def build_explorer_data" 
```

Reperer la fonction `build_explorer_data()` qui lit `AGGREGATE_LIEUX` et `AGGREGATE_EVENTS` et imbrique les events sous les lieux.

- [ ] **Step 1.2 : Renommer la fonction existante en `build_explorer_data_for_tenants` et l'adapter pour filtrer sur une liste d'UUIDs**

Edit `seo/services.py` — remplacer la def actuelle par :

```python
def build_explorer_data_for_tenants(tenant_uuids):
    """
    Construit les donnees structurees pour la page explorer (carte + liste),
    en filtrant sur la liste d'UUIDs fournie.
    / Build structured data for the explorer page (map + list),
    filtering on the provided UUID list.

    Parametres / Parameters:
        tenant_uuids: list[str] — UUIDs des tenants a inclure.
                                  Si vide, retourne {"lieux": [], "events": []}.

    Retourne / Returns: dict avec cles lieux, events
    """
    from seo.models import SEOCache
    from seo.views_common import get_seo_cache

    if not tenant_uuids:
        return {"lieux": [], "events": []}

    # Convertir en set pour lookup O(1) / Convert to set for O(1) lookup
    uuids_set = set(tenant_uuids)

    # Lire les 2 agregats depuis le cache L1/L2
    # / Read the 2 aggregates from L1/L2 cache
    lieux_data = get_seo_cache(SEOCache.AGGREGATE_LIEUX) or {}
    events_data = get_seo_cache(SEOCache.AGGREGATE_EVENTS) or {}

    raw_lieux = lieux_data.get("lieux", [])
    raw_events = events_data.get("events", [])

    # Filtrer + indexer les lieux par tenant_id, en excluant ceux sans coords GPS
    # / Filter + index lieux by tenant_id, excluding those without GPS coords
    lieux_by_tenant = {}
    for lieu in raw_lieux:
        if lieu["tenant_id"] not in uuids_set:
            continue
        if lieu.get("latitude") is None or lieu.get("longitude") is None:
            continue
        lieu_copy = dict(lieu)
        lieu_copy["events"] = []
        lieux_by_tenant[lieu["tenant_id"]] = lieu_copy

    # Construire la liste plate d'events avec infos du lieu parent
    # / Build flat event list with parent lieu info
    flat_events = []
    for event in raw_events:
        tenant_id = event.get("tenant_id")
        if tenant_id not in uuids_set:
            continue
        lieu = lieux_by_tenant.get(tenant_id)
        if lieu is None:
            continue
        event_copy = dict(event)
        event_copy["lieu_id"] = tenant_id
        event_copy["lieu_name"] = lieu.get("name", "")
        event_copy["lieu_domain"] = lieu.get("domain", "")
        flat_events.append(event_copy)
        # Imbriquer sous le lieu parent / Nest under parent lieu
        lieu["events"].append(event)

    return {
        "lieux": list(lieux_by_tenant.values()),
        "events": flat_events,
    }


def build_explorer_data():
    """
    Compatibilite retro : appelle build_explorer_data_for_tenants() avec
    l'ensemble des tenant_ids presents dans AGGREGATE_LIEUX.
    Comportement identique a la version d'avant le refactor.
    / Backward compat: calls build_explorer_data_for_tenants() with all
    tenant_ids from AGGREGATE_LIEUX. Identical behavior to pre-refactor.
    """
    from seo.models import SEOCache
    from seo.views_common import get_seo_cache

    lieux_data = get_seo_cache(SEOCache.AGGREGATE_LIEUX) or {}
    all_uuids = [lieu["tenant_id"] for lieu in lieux_data.get("lieux", [])]
    return build_explorer_data_for_tenants(all_uuids)
```

- [ ] **Step 1.3 : Verifier syntaxe**

```bash
docker exec lespass_django poetry run python -c "import ast; ast.parse(open('/DjangoFiles/seo/services.py').read()); print('OK')"
```

Expected output: `OK`

- [ ] **Step 1.4 : Verifier manage.py check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected output: `System check identified no issues (0 silenced).`

- [ ] **Step 1.5 : Verifier que le SEO public marche toujours**

```bash
curl -sk -o /dev/null -w "HTTP %{http_code}  bytes=%{size_download}\n" https://tibillet.localhost/explorer/
```

Expected: `HTTP 200  bytes>20000`

- [ ] **Step 1.6 : Suggested commit**

```
refactor(seo): paramétrer build_explorer_data en build_explorer_data_for_tenants

Permet de réutiliser la même fonction côté tenant /federation/ avec un filtre
sur les UUIDs fédérés. build_explorer_data() reste un wrapper rétrocompatible.
```

---

## Task 2 : Ajouter `current_tenant_uuid=''` dans `seo.views.explorer()`

**Files:**
- Modify: `seo/views.py` (fonction `explorer`)

- [ ] **Step 2.1 : Editer la vue explorer**

Dans `seo/views.py`, trouver la fonction `explorer(request)` et ajouter une cle dans le contexte. Le contexte actuel ressemble a :

```python
context = {
    "explorer_data": explorer_data,
    "page_title": "Explorer - TiBillet",
    "page_description": (...),
}
```

Ajouter `current_tenant_uuid: ""` (chaine vide => pas de highlight) :

```python
context = {
    "explorer_data": explorer_data,
    "current_tenant_uuid": "",  # public ROOT : pas de tenant courant a highlighter
    "page_title": "Explorer - TiBillet",
    "page_description": (...),
}
```

- [ ] **Step 2.2 : Verifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected output: `System check identified no issues (0 silenced).`

---

## Task 3 : Vendor Leaflet 1.9.4 + Leaflet.markercluster 1.5.3

**Files:**
- Create: `seo/static/seo/vendor/leaflet/leaflet.js`
- Create: `seo/static/seo/vendor/leaflet/leaflet.css`
- Create: `seo/static/seo/vendor/leaflet/markercluster.js`
- Create: `seo/static/seo/vendor/leaflet/MarkerCluster.css`
- Create: `seo/static/seo/vendor/leaflet/MarkerCluster.Default.css`
- Create: `seo/static/seo/vendor/leaflet/images/{marker-icon,marker-icon-2x,marker-shadow,layers,layers-2x}.png`

- [ ] **Step 3.1 : Creer l'arborescence**

```bash
mkdir -p /home/jonas/TiBillet/dev/Lespass/seo/static/seo/vendor/leaflet/images
```

- [ ] **Step 3.2 : Telecharger Leaflet core**

```bash
cd /home/jonas/TiBillet/dev/Lespass/seo/static/seo/vendor/leaflet
curl -L -o leaflet.js https://unpkg.com/leaflet@1.9.4/dist/leaflet.js
curl -L -o leaflet.css https://unpkg.com/leaflet@1.9.4/dist/leaflet.css
ls -la
```

Expected: leaflet.js (~150KB), leaflet.css (~14KB).

- [ ] **Step 3.3 : Telecharger Leaflet.markercluster**

```bash
cd /home/jonas/TiBillet/dev/Lespass/seo/static/seo/vendor/leaflet
curl -L -o markercluster.js https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js
curl -L -o MarkerCluster.css https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css
curl -L -o MarkerCluster.Default.css https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css
```

- [ ] **Step 3.4 : Telecharger les images Leaflet**

```bash
cd /home/jonas/TiBillet/dev/Lespass/seo/static/seo/vendor/leaflet/images
for img in marker-icon.png marker-icon-2x.png marker-shadow.png layers.png layers-2x.png; do
  curl -L -o "$img" "https://unpkg.com/leaflet@1.9.4/dist/images/$img"
done
ls -la
```

Expected: 5 PNG files.

- [ ] **Step 3.5 : Verifier integrite**

```bash
file /home/jonas/TiBillet/dev/Lespass/seo/static/seo/vendor/leaflet/*.{js,css}
file /home/jonas/TiBillet/dev/Lespass/seo/static/seo/vendor/leaflet/images/*.png
```

Expected: tous les fichiers sont du bon type (JS = ASCII text, CSS = ASCII text, PNG = PNG image).

- [ ] **Step 3.6 : Suggested commit**

```
chore(seo): vendor Leaflet 1.9.4 + markercluster 1.5.3

Plus de dépendance CDN externe en prod. Versions figées dans
seo/static/seo/vendor/leaflet/. Total ~250 KB (gzip ~80 KB).
```

---

## Task 4 : Reecriture explorer.js (IIFE + 7 chantiers de solidification)

**Files:**
- Modify: `seo/static/seo/explorer.js` (replacement complet)

- [ ] **Step 4.1 : Ecrire le nouveau JS**

Replacer integralement `seo/static/seo/explorer.js` par le code ci-dessous :

```js
/**
 * EXPLORER — carte Leaflet + liste filtrée + toggle mobile.
 * / EXPLORER — Leaflet map + filtered list + mobile toggle.
 *
 * LOCALISATION : seo/static/seo/explorer.js
 * UTILISÉ PAR : public /explorer/ + tenant /federation/ (même code, même comportement).
 *
 * USAGE :
 *   1. Inclure leaflet.css + MarkerCluster.css + MarkerCluster.Default.css en <head>
 *   2. Inclure leaflet.js + markercluster.js + explorer.js en fin de <body>
 *   3. Rendre dans le template : #explorer-root (avec data-*), #explorer-list,
 *      #explorer-map, <script id="explorer-data" type="application/json">
 *
 * DATA FLOW :
 *   1. init() lit #explorer-data (JSON) + #explorer-root (data-i18n-*, data-current-tenant-uuid)
 *   2. bindControls() attache 1 listener delegated sur #explorer-list + 1 sur #explorer-pills
 *   3. applyFilters() filtre data → renderList() + updateMarkers()
 *   4. Click carte/liste → focusOnLieu() : zoom + popup + accordéon
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
(function () {
    'use strict';

    // ============================================================
    // CONFIG — lu depuis #explorer-root data-*
    // / CONFIG — read from #explorer-root data-*
    // ============================================================
    const config = {
        currentTenantUuid: '',
        i18n: {
            empty: 'Aucun résultat trouvé.',
            visit: 'Visiter le lieu',
            lieu: 'Lieu',
            event: 'Événement',
            all: 'Tous',
            current: 'Vous êtes ici',
            noEvents: 'Pas d\'événement à venir',
        },
    };

    // ============================================================
    // STATE — encapsulé, jamais sur window
    // / STATE — encapsulated, never on window
    // ============================================================
    const state = {
        data: null,
        filters: { text: '', category: 'all' },
        map: null,
        markers: {},
        markerCluster: null,
        currentView: 'list',
        mapInitialized: false,
    };

    // ============================================================
    // DOM — references mises en cache au init
    // / DOM — references cached at init
    // ============================================================
    const dom = {
        root: null,
        list: null,
        map: null,
        mapLoading: null,
        search: null,
        pills: null,
        counter: null,
        fab: null,
    };

    // ============================================================
    // HELPERS
    // ============================================================

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }

    function pluralize(count, singular, plural) {
        return count + ' ' + (count > 1 ? plural : singular);
    }

    function formatShortDate(isoString) {
        if (!isoString) return '';
        try {
            return new Date(isoString).toLocaleDateString('fr-FR', {
                day: 'numeric', month: 'short',
            });
        } catch (e) {
            return '';
        }
    }

    function readConfigFromDom() {
        if (!dom.root) return;
        const ds = dom.root.dataset;
        config.currentTenantUuid = ds.currentTenantUuid || '';
        // Surcharge i18n depuis data-i18n-* / Override i18n from data-i18n-*
        if (ds.i18nEmpty) config.i18n.empty = ds.i18nEmpty;
        if (ds.i18nVisit) config.i18n.visit = ds.i18nVisit;
        if (ds.i18nLieu) config.i18n.lieu = ds.i18nLieu;
        if (ds.i18nEvent) config.i18n.event = ds.i18nEvent;
        if (ds.i18nAll) config.i18n.all = ds.i18nAll;
        if (ds.i18nCurrent) config.i18n.current = ds.i18nCurrent;
        if (ds.i18nNoEvents) config.i18n.noEvents = ds.i18nNoEvents;
    }

    // ============================================================
    // INIT — point d'entree principal
    // / INIT — main entry point
    // ============================================================

    function init() {
        // Cacher les references DOM critiques / Cache critical DOM refs
        dom.root = document.getElementById('explorer-root');
        dom.list = document.getElementById('explorer-list');
        dom.map = document.getElementById('explorer-map');
        dom.mapLoading = document.getElementById('explorer-map-loading');
        dom.search = document.getElementById('explorer-search');
        dom.pills = document.getElementById('explorer-pills');
        dom.counter = document.getElementById('explorer-counter');
        dom.fab = document.getElementById('explorer-fab');

        // Garde-fou : si les elements essentiels manquent, abandonner
        // / Guard: if essential elements are missing, abort
        if (!dom.root || !dom.list || !dom.map) {
            console.warn('explorer: required DOM elements missing, aborting init');
            return;
        }

        readConfigFromDom();
        state.data = loadData();
        if (!state.data) {
            renderEmptyState();
            return;
        }

        bindControls();
        applyFilters();

        if (window.innerWidth >= 992) {
            initMap();
        } else {
            // Mobile : la carte est initialisee au 1er toggle vers "Carte"
            // / Mobile: map initialized on first toggle to "Carte"
            hideMapLoadingSpinner();
        }
    }

    function destroy() {
        // Cleanup map + listeners pour swap HTMX/SPA futur
        // / Cleanup map + listeners for HTMX/SPA swap (future-proof)
        if (state.map) {
            state.map.remove();
            state.map = null;
        }
        state.markers = {};
        state.markerCluster = null;
        state.mapInitialized = false;
    }

    // ============================================================
    // DATA — chargement + filtrage
    // / DATA — loading + filtering
    // ============================================================

    function loadData() {
        const el = document.getElementById('explorer-data');
        if (!el) {
            console.warn('explorer: #explorer-data element missing');
            return null;
        }
        try {
            return JSON.parse(el.textContent);
        } catch (e) {
            console.error('explorer: invalid JSON in #explorer-data', e);
            return null;
        }
    }

    function matchesText(item) {
        if (!state.filters.text) return true;
        const q = state.filters.text;
        const fields = [item.name, item.locality, item.short_description, item.lieu_name];
        for (let i = 0; i < fields.length; i++) {
            if ((fields[i] || '').toLowerCase().indexOf(q) !== -1) return true;
        }
        return false;
    }

    function filterCategory(sourceArray, categoryName) {
        if (state.filters.category !== 'all' && state.filters.category !== categoryName) {
            return [];
        }
        return (sourceArray || []).filter(matchesText);
    }

    function applyFilters() {
        if (!state.data) return;

        const lieux = filterCategory(state.data.lieux, 'lieu');
        const events = filterCategory(state.data.events, 'event');

        renderList(lieux, events);
        updateCounters(lieux.length, events.length);

        if (state.mapInitialized) {
            const lieuxOnMap = collectLieuxFromResults(lieux, events);
            updateMapMarkers(lieuxOnMap);
        }
    }

    function collectLieuxFromResults(lieux, events) {
        const visibleIds = {};
        for (let i = 0; i < lieux.length; i++) visibleIds[lieux[i].tenant_id] = true;
        for (let j = 0; j < events.length; j++) {
            if (events[j].lieu_id) visibleIds[events[j].lieu_id] = true;
        }
        const result = [];
        for (let k = 0; k < state.data.lieux.length; k++) {
            if (visibleIds[state.data.lieux[k].tenant_id]) {
                result.push(state.data.lieux[k]);
            }
        }
        return result;
    }

    function updateCounters(lieuxN, eventsN) {
        if (!dom.counter) return;
        const parts = [
            pluralize(lieuxN, 'lieu', 'lieux'),
            pluralize(eventsN, 'événement', 'événements'),
        ];
        dom.counter.textContent = parts.join(' · ');
    }

    // ============================================================
    // CONTROLLERS — bind inputs + event delegation
    // / CONTROLLERS — input bindings + event delegation
    // ============================================================

    function bindControls() {
        bindSearch();
        bindPills();
        bindFAB();
        bindListDelegation();
    }

    function bindSearch() {
        if (!dom.search) return;
        const initialValue = dom.search.value.trim().toLowerCase();
        if (initialValue) state.filters.text = initialValue;

        let timer = null;
        dom.search.addEventListener('input', function () {
            clearTimeout(timer);
            timer = setTimeout(function () {
                state.filters.text = dom.search.value.trim().toLowerCase();
                applyFilters();
            }, 300);
        });
    }

    function bindPills() {
        if (!dom.pills) return;
        dom.pills.addEventListener('click', function (ev) {
            const pill = ev.target.closest('.explorer-pill');
            if (!pill) return;
            const allPills = dom.pills.querySelectorAll('.explorer-pill');
            allPills.forEach(function (p) { p.classList.remove('active'); });
            pill.classList.add('active');
            state.filters.category = pill.getAttribute('data-category') || 'all';
            applyFilters();
        });
    }

    function bindFAB() {
        if (!dom.fab) return;
        dom.fab.addEventListener('click', toggleView);
    }

    /**
     * Event delegation sur #explorer-list : un seul listener gere
     * tous les clicks sur cards lieu, cards event, toggles d'accordeon.
     * / Event delegation on #explorer-list: a single listener handles
     * all clicks on lieu cards, event cards, accordion toggles.
     */
    function bindListDelegation() {
        dom.list.addEventListener('click', function (ev) {
            // Toggle accordeon (a tester en premier — plus specifique)
            // / Accordion toggle (check first — more specific)
            const toggle = ev.target.closest('.explorer-accordion-toggle');
            if (toggle) {
                ev.stopPropagation();
                handleAccordionToggle(toggle);
                return;
            }
            // Click sur une card avec data-lieu-id : focus carte
            // / Click on a card with data-lieu-id: focus map
            const card = ev.target.closest('[data-lieu-id]');
            if (card) {
                const lieuId = card.getAttribute('data-lieu-id');
                if (lieuId) focusOnLieu(lieuId);
            }
        });

        // Hover desktop : highlight pin sur carte
        // / Desktop hover: highlight pin on map
        if (window.innerWidth >= 992) {
            dom.list.addEventListener('mouseover', function (ev) {
                const card = ev.target.closest('[data-lieu-id]');
                if (card) highlightPinClass(card.getAttribute('data-lieu-id'), true);
            });
            dom.list.addEventListener('mouseout', function (ev) {
                const card = ev.target.closest('[data-lieu-id]');
                if (card) highlightPinClass(card.getAttribute('data-lieu-id'), false);
            });
        }
    }

    // ============================================================
    // RENDER LIST — DOM cards (templating cote JS, encapsule)
    // / RENDER LIST — DOM cards (JS templating, encapsulated)
    // ============================================================

    function renderList(lieux, events) {
        if (!dom.list) return;
        let html = '';
        for (let i = 0; i < lieux.length; i++) html += buildLieuCard(lieux[i]);
        for (let j = 0; j < events.length; j++) html += buildEventCard(events[j]);
        dom.list.innerHTML = html || ('<p class="text-muted text-center py-4">' + escapeHtml(config.i18n.empty) + '</p>');
    }

    function buildLieuCard(lieu) {
        const tenantId = escapeHtml(lieu.tenant_id);
        const domain = lieu.domain || '';
        const href = domain ? 'https://' + domain + '/' : '#';
        const isCurrent = lieu.tenant_id === config.currentTenantUuid;

        const logo = lieu.logo_url
            ? '<img src="' + escapeHtml(lieu.logo_url) + '" alt="" class="explorer-card-icon lieu" style="object-fit:contain;padding:4px;">'
            : '<div class="explorer-card-icon lieu">\u{1F3DB}</div>';

        const meta = lieu.locality
            ? '<div class="explorer-card-meta">\u{1F4CD} ' + escapeHtml(lieu.locality)
                + (lieu.country ? ', ' + escapeHtml(lieu.country) : '') + '</div>'
            : '';
        const desc = lieu.short_description
            ? '<div class="explorer-card-desc">' + escapeHtml(lieu.short_description) + '</div>'
            : '';
        const currentBadge = isCurrent
            ? ' <span class="explorer-badge explorer-badge--current">' + escapeHtml(config.i18n.current) + '</span>'
            : '';

        return ''
            + '<div class="explorer-card explorer-card--lieu' + (isCurrent ? ' explorer-card--current' : '') + '"'
            + ' data-lieu-id="' + tenantId + '" data-type="lieu"'
            + ' data-testid="explorer-card-lieu-' + tenantId + '">'
                + '<div class="explorer-card-focus" role="button" tabindex="0">'
                    + logo
                    + '<div class="explorer-card-body">'
                        + '<div class="explorer-card-header">'
                            + '<h3 class="explorer-card-title">' + escapeHtml(lieu.name) + '</h3>'
                            + '<span class="explorer-badge lieu">' + escapeHtml(config.i18n.lieu) + '</span>'
                            + currentBadge
                        + '</div>'
                        + meta
                        + desc
                    + '</div>'
                + '</div>'
                + buildLieuAccordion(lieu, domain)
                + '<div class="explorer-card-footer">'
                    + '<a href="' + escapeHtml(href) + '" target="_blank" rel="noopener" class="explorer-card-link">'
                    + escapeHtml(config.i18n.visit) + ' →</a>'
                + '</div>'
            + '</div>';
    }

    function buildLieuAccordion(lieu, domain) {
        const events = lieu.events || [];
        if (events.length === 0) return '';
        const label = pluralize(events.length, 'événement', 'événements');
        let items = '';
        for (let i = 0; i < events.length; i++) {
            const ev = events[i];
            const evHref = domain && ev.slug ? 'https://' + domain + '/event/' + ev.slug + '/' : '#';
            items += ''
                + '<a class="explorer-accordion-item" href="' + escapeHtml(evHref) + '" target="_blank" rel="noopener">'
                    + '<span class="explorer-accordion-icon">\u{1F3B6}</span>'
                    + '<span class="explorer-accordion-name">' + escapeHtml(ev.name) + '</span>'
                    + (ev.datetime ? '<span class="explorer-accordion-date">' + escapeHtml(formatShortDate(ev.datetime)) + '</span>' : '')
                + '</a>';
        }
        return ''
            + '<div class="explorer-accordion">'
                + '<button class="explorer-accordion-toggle" type="button">'
                    + '<span>' + escapeHtml(label) + '</span>'
                    + '<i class="bi bi-chevron-down explorer-accordion-chevron" aria-hidden="true"></i>'
                + '</button>'
                + '<div class="explorer-accordion-panel"><div class="explorer-accordion-panel-inner">' + items + '</div></div>'
            + '</div>';
    }

    function buildEventCard(event) {
        const lieuId = escapeHtml(event.lieu_id || '');
        const datePart = event.datetime ? '\u{1F4C5} ' + escapeHtml(formatShortDate(event.datetime)) + ' · ' : '';
        const metaText = datePart + escapeHtml(event.lieu_name || '');
        const desc = event.short_description
            ? '<div class="explorer-card-desc">' + escapeHtml(event.short_description) + '</div>'
            : '';
        const lieuAttr = lieuId ? ' data-lieu-id="' + lieuId + '"' : '';

        return ''
            + '<div class="explorer-card"' + lieuAttr + ' data-type="event"'
            + ' data-testid="explorer-card-event">'
                + '<div class="explorer-card-icon event">\u{1F3B6}</div>'
                + '<div class="explorer-card-body">'
                    + '<div class="explorer-card-header">'
                        + '<h3 class="explorer-card-title">' + escapeHtml(event.name) + '</h3>'
                        + '<span class="explorer-badge event">' + escapeHtml(config.i18n.event) + '</span>'
                    + '</div>'
                    + '<div class="explorer-card-meta">' + metaText + '</div>'
                    + desc
                + '</div>'
            + '</div>';
    }

    function renderEmptyState() {
        if (!dom.list) return;
        dom.list.innerHTML = '<p class="text-muted text-center py-4">' + escapeHtml(config.i18n.empty) + '</p>';
        hideMapLoadingSpinner();
    }

    // ============================================================
    // RENDER MAP — Leaflet integration
    // / RENDER MAP — Leaflet integration
    // ============================================================

    function initMap() {
        if (state.mapInitialized) return;
        if (!dom.map) return;
        if (typeof L === 'undefined') {
            console.warn('explorer: Leaflet not loaded, skipping map init');
            hideMapLoadingSpinner();
            return;
        }

        state.map = L.map('explorer-map', { zoomControl: true, scrollWheelZoom: true });

        // CartoDB Voyager : pas de restriction referer (OSM bloque localhost)
        // / CartoDB Voyager: no referer restriction (OSM blocks localhost)
        L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
            maxZoom: 19,
            subdomains: 'abcd',
        }).addTo(state.map);

        state.markerCluster = L.markerClusterGroup();
        state.map.addLayer(state.markerCluster);

        addMarkers(state.data.lieux);
        state.mapInitialized = true;

        applyFilters();
        hideMapLoadingSpinner();
    }

    function hideMapLoadingSpinner() {
        if (!dom.mapLoading) return;
        dom.mapLoading.classList.add('explorer-map-loading--fading');
        setTimeout(function () {
            if (dom.mapLoading && dom.mapLoading.parentElement) {
                dom.mapLoading.parentElement.removeChild(dom.mapLoading);
            }
        }, 250);
    }

    function addMarkers(lieux) {
        if (!state.map || !state.markerCluster) return;
        state.markerCluster.clearLayers();
        state.markers = {};
        const bounds = [];

        for (let i = 0; i < lieux.length; i++) {
            const lieu = lieux[i];
            const lat = parseFloat(lieu.latitude);
            const lng = parseFloat(lieu.longitude);
            if (isNaN(lat) || isNaN(lng)) continue;

            const isCurrent = lieu.tenant_id === config.currentTenantUuid;
            const pinClass = 'explorer-pin' + (isCurrent ? ' explorer-pin--current' : '');
            const icon = L.divIcon({
                className: '',
                html: '<div class="' + pinClass + '" data-lieu-id="' + escapeHtml(lieu.tenant_id) + '">'
                    + escapeHtml(lieu.name) + '</div>',
                iconSize: null,
                iconAnchor: [0, 0],
            });

            const marker = L.marker([lat, lng], { icon: icon });
            marker.bindPopup(buildPopupContent(lieu), { maxWidth: 280 });

            // Closure pour capturer tenant_id
            // / Closure to capture tenant_id
            (function (tenantId) {
                marker.on('click', function () { scrollToCard(tenantId); });
            })(lieu.tenant_id);

            state.markers[lieu.tenant_id] = marker;
            state.markerCluster.addLayer(marker);
            bounds.push([lat, lng]);
        }

        if (bounds.length > 0) state.map.fitBounds(bounds, { padding: [20, 20] });
        else state.map.setView([46.603354, 1.888334], 6);
    }

    function buildPopupContent(lieu) {
        const href = lieu.domain ? 'https://' + lieu.domain + '/' : '#';
        let html = '<div class="explorer-popup">'
            + '<h4 class="explorer-popup-title">' + escapeHtml(lieu.name) + '</h4>';
        if (lieu.short_description) {
            html += '<p class="explorer-popup-desc">' + escapeHtml(lieu.short_description) + '</p>';
        }
        if (lieu.locality) {
            html += '<p class="explorer-popup-stats">\u{1F4CD} ' + escapeHtml(lieu.locality)
                + (lieu.country ? ', ' + escapeHtml(lieu.country) : '') + '</p>';
        }
        const events = lieu.events || [];
        if (events.length > 0) {
            html += '<div class="explorer-popup-events"><strong>Prochains événements :</strong><ul style="margin:4px 0;padding-left:16px;">';
            const n = Math.min(events.length, 3);
            for (let i = 0; i < n; i++) {
                const ev = events[i];
                html += '<li>' + escapeHtml(ev.name)
                    + (ev.datetime ? ' — ' + escapeHtml(formatShortDate(ev.datetime)) : '') + '</li>';
            }
            html += '</ul>';
            if (events.length > 3) {
                html += '<span style="font-size:11px;color:#999;">+ ' + (events.length - 3) + ' autre(s)</span>';
            }
            html += '</div>';
        }
        html += '<a class="explorer-popup-link" href="' + escapeHtml(href) + '" target="_blank" rel="noopener">'
            + escapeHtml(config.i18n.visit) + ' →</a></div>';
        return html;
    }

    function updateMapMarkers(filteredLieux) {
        if (!state.mapInitialized) return;
        const keep = {};
        for (let i = 0; i < filteredLieux.length; i++) keep[filteredLieux[i].tenant_id] = true;

        for (const tenantId in state.markers) {
            const marker = state.markers[tenantId];
            const isVisible = state.markerCluster.hasLayer(marker);
            if (keep[tenantId] && !isVisible) state.markerCluster.addLayer(marker);
            else if (!keep[tenantId] && isVisible) state.markerCluster.removeLayer(marker);
        }
    }

    // ============================================================
    // FOCUS LIEU — zoom + popup + accordeon + highlight
    // / FOCUS LIEU — zoom + popup + accordion + highlight
    // ============================================================

    function focusOnLieu(tenantId) {
        if (window.innerWidth < 992 && state.currentView === 'list') toggleView();
        if (!state.mapInitialized) initMap();
        const marker = state.markers[tenantId];
        if (!marker) return;

        state.map.setView(marker.getLatLng(), 15, { animate: true });

        // Utiliser l'event animationend du cluster si possible, sinon fallback timing reduit
        // / Use cluster animationend event if available, otherwise reduced timing fallback
        if (state.markerCluster && typeof state.markerCluster.once === 'function') {
            let fallback = setTimeout(function () { marker.openPopup(); }, 500);
            state.markerCluster.once('animationend', function () {
                clearTimeout(fallback);
                marker.openPopup();
            });
        } else {
            setTimeout(function () { marker.openPopup(); }, 200);
        }

        highlightPin(tenantId);

        if (window.innerWidth >= 992) {
            openLieuAccordion(tenantId);
        }
    }

    function highlightPin(tenantId) {
        const pin = document.querySelector('.explorer-pin[data-lieu-id="' + cssEscape(tenantId) + '"]');
        if (!pin) return;
        pin.classList.add('selected');
        setTimeout(function () { pin.classList.remove('selected'); }, 3000);
    }

    function highlightPinClass(tenantId, isOn) {
        const pin = document.querySelector('.explorer-pin[data-lieu-id="' + cssEscape(tenantId) + '"]');
        if (pin) pin.classList.toggle('selected', isOn);
    }

    function cssEscape(value) {
        // Echappement pour attribute selectors — CSS.escape n'est pas universel
        // / Escape for attribute selectors — CSS.escape isn't universal
        return String(value).replace(/(["\\])/g, '\\$1');
    }

    function openLieuAccordion(tenantId) {
        const card = document.querySelector('.explorer-card--lieu[data-lieu-id="' + cssEscape(tenantId) + '"]');
        if (!card) return;
        const panel = card.querySelector('.explorer-accordion-panel');
        const wasOpen = panel && panel.classList.contains('open');
        closeAllAccordionsExcept(tenantId);
        if (panel) setAccordionState(card, !wasOpen);
        card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function closeAllAccordionsExcept(cardId) {
        const allCards = document.querySelectorAll('.explorer-card--lieu');
        for (let i = 0; i < allCards.length; i++) {
            const card = allCards[i];
            if (card.getAttribute('data-lieu-id') === cardId) continue;
            setAccordionState(card, false);
        }
    }

    function setAccordionState(card, shouldBeOpen) {
        const panel = card.querySelector('.explorer-accordion-panel');
        const chevron = card.querySelector('.explorer-accordion-chevron');
        if (!panel) return;
        panel.classList.toggle('open', shouldBeOpen);
        if (chevron) chevron.style.transform = shouldBeOpen ? 'rotate(180deg)' : '';
    }

    function handleAccordionToggle(button) {
        const card = button.closest('.explorer-card--lieu');
        if (!card) return;
        const panel = card.querySelector('.explorer-accordion-panel');
        const willOpen = !panel.classList.contains('open');
        if (willOpen) {
            closeAllAccordionsExcept(card.getAttribute('data-lieu-id'));
        }
        setAccordionState(card, willOpen);
    }

    function scrollToCard(tenantId) {
        const card = document.querySelector('.explorer-card[data-lieu-id="' + cssEscape(tenantId) + '"][data-type="lieu"]');
        if (!card) return;
        card.scrollIntoView({ behavior: 'smooth', block: 'center' });
        card.setAttribute('data-highlighted', 'true');
        setTimeout(function () { card.removeAttribute('data-highlighted'); }, 2000);
    }

    // ============================================================
    // TOGGLE VIEW MOBILE
    // ============================================================

    function toggleView() {
        const container = document.querySelector('.explorer-container');
        if (!container || !dom.fab) return;
        const label = dom.fab.querySelector('.explorer-fab-label');

        if (state.currentView === 'list') {
            container.classList.add('explorer-view-map');
            document.body.classList.add('explorer-map-active');
            if (label) label.textContent = 'Liste';
            state.currentView = 'map';
            window.scrollTo({ top: 0, behavior: 'instant' });
            if (!state.mapInitialized) initMap();
            else state.map.invalidateSize();
        } else {
            container.classList.remove('explorer-view-map');
            document.body.classList.remove('explorer-map-active');
            if (label) label.textContent = 'Carte';
            state.currentView = 'list';
        }
    }

    // ============================================================
    // ENTRY POINT
    // ============================================================
    document.addEventListener('DOMContentLoaded', init);
})();
```

- [ ] **Step 4.2 : Verifier qu'aucun `window.*` n'est expose**

Ouvrir Chrome devtools console sur `https://tibillet.localhost/explorer/` apres refresh, taper :

```js
typeof window.explorerData; // 'undefined'
typeof window.map;           // 'undefined'
typeof window.markers;       // 'undefined'
typeof window.activeFilters; // 'undefined'
typeof window.focusOnLieu;   // 'undefined'
```

Expected: tous `'undefined'`.

- [ ] **Step 4.3 : Suggested commit**

```
refactor(seo/explorer.js): IIFE + event delegation + i18n + garde-fous

- Zéro pollution window (tout encapsulé)
- Event delegation, plus de inline onclick
- Garde-fous JSON.parse + DOM
- i18n via data-i18n-* sur #explorer-root
- Marker spécial pour le tenant courant (data-current-tenant-uuid)
- destroy() exposé pour futur cleanup HTMX/SPA
```

---

## Task 5 : CSS cleanup + ajout `.explorer-pin--current`

**Files:**
- Modify: `seo/static/seo/explorer.css`

- [ ] **Step 5.1 : Lire le CSS actuel pour identifier les classes mortes**

```bash
grep -nE "lieu-asset-badge|explorer-asset-legend|explorer-pin--dimmed|explorer-card-icon\.(asset|membership|initiative)|explorer-badge\.(asset|membership|initiative)|explorer-card--asset|explorer-card\[data-type=.asset.\]|explorer-card--active" /home/jonas/TiBillet/dev/Lespass/seo/static/seo/explorer.css
```

Cela liste les debuts de regles a supprimer.

- [ ] **Step 5.2 : Supprimer les blocs morts via Edit (un par un)**

Identifier visuellement chaque bloc (regle CSS complete) et supprimer. Liste exhaustive des selecteurs morts :

- `.lieu-asset-badges`, `.lieu-asset-badge`, `.lieu-asset-badge:hover`, `.lieu-asset-badge--active`, `.lieu-asset-badge-icon`, `.lieu-asset-badge-label`
- `.explorer-asset-legend`, `.explorer-asset-legend[hidden]`, `.explorer-asset-legend-content`, `.explorer-asset-legend-title`, `.explorer-asset-legend-icon`, `.explorer-asset-legend-meta`, `.explorer-asset-legend-close`, `.explorer-asset-legend-close:hover` + media query a 991px du legend
- `.explorer-pin--dimmed`
- `.explorer-card-icon.asset`, `.explorer-card-icon.membership`, `.explorer-card-icon.initiative`
- `.explorer-badge.asset`, `.explorer-badge.membership`, `.explorer-badge.initiative`
- `.explorer-card--asset`, `.explorer-card[data-type="asset"]:hover::after`, `.explorer-card[data-type="event"]:hover::after`, `.explorer-card[data-type="membership"]:hover::after`, `.explorer-card[data-type="initiative"]:hover::after`, `.explorer-card[data-type="event"]`, `.explorer-card[data-type="membership"]`, `.explorer-card[data-type="initiative"]` (les variantes asset/membership/initiative seulement, garder event !)
- `.explorer-card--active` (asset focus state)

**Attention** : garder les hover::after sur `event` (toujours utilise). Ne supprimer que ce qui touche `asset`, `membership`, `initiative`.

- [ ] **Step 5.3 : Ajouter les regles pour le marker courant**

Ajouter en fin de section "5. Marqueurs carte Leaflet (DivIcon)" :

```css
/* Pin du tenant courant : couleur primaire + halo discret. */
/* Permet de reperer "vous etes ici" sur la carte d'un explorer in-tenant. */
/* / Current tenant pin: primary color + discrete halo. */
/* Highlights "you are here" on the map of an in-tenant explorer. */
.explorer-pin--current {
    background: var(--bs-primary, #0d6efd);
    color: #fff;
    box-shadow: 0 0 0 3px rgba(13, 110, 253, 0.25), 0 2px 6px rgba(0, 0, 0, 0.2);
}

.explorer-pin--current.selected {
    background: var(--bs-primary, #0d6efd);
    color: #fff;
    transform: scale(1.1);
}
```

Et ajouter dans la section badges :

```css
/* Badge "Vous etes ici" affiche sur la card du tenant courant. */
/* / "You are here" badge shown on the current tenant's card. */
.explorer-badge--current {
    background: var(--bs-primary, #0d6efd);
    color: #fff;
    margin-left: 4px;
}

.explorer-card--current {
    border-color: var(--bs-primary, #0d6efd) !important;
}
```

- [ ] **Step 5.4 : Verifier qu'aucune regle morte ne reste**

```bash
grep -nE "lieu-asset-badge|explorer-asset-legend|explorer-pin--dimmed" /home/jonas/TiBillet/dev/Lespass/seo/static/seo/explorer.css
```

Expected: aucune sortie.

- [ ] **Step 5.5 : Suggested commit**

```
chore(seo/explorer.css): cleanup -200 lignes mort + .explorer-pin--current

- Suppression des classes héritées du clone V2 jamais utilisées en V1 :
  badges assets, focus monnaie legend, pin dimmed, icon/badge asset/membership/initiative
- Ajout .explorer-pin--current et .explorer-badge--current pour le marker
  du tenant courant sur l'explorer in-tenant
```

---

## Task 6 : Creer le widget partial `explorer_widget.html`

**Files:**
- Create: `seo/templates/seo/partials/explorer_widget.html`

- [ ] **Step 6.1 : Creer le dossier partials**

```bash
mkdir -p /home/jonas/TiBillet/dev/Lespass/seo/templates/seo/partials
```

- [ ] **Step 6.2 : Ecrire le widget**

Fichier `seo/templates/seo/partials/explorer_widget.html` :

```django
{% load static i18n %}

{# Widget Explorer — utilise dans 2 contextes : /explorer/ (public ROOT) et /federation/ (tenant). #}
{# Source unique du HTML : si tu changes ce fichier, les 2 vues evoluent ensemble. #}
{# / Explorer widget — used in 2 contexts: /explorer/ (public ROOT) and /federation/ (tenant). #}
{# Single HTML source: changing this file affects both views simultaneously. #}
{#                                                                                                #}
{# Variables de contexte attendues :                                                              #}
{#   - explorer_data : dict {lieux: [...], events: [...]} retourne par                            #}
{#     seo.services.build_explorer_data_for_tenants()                                             #}
{#   - current_tenant_uuid : str — UUID du tenant courant, ou "" sur le public                    #}
{# / Expected context variables:                                                                  #}
{#   - explorer_data: dict {lieux: [...], events: [...]} from                                     #}
{#     seo.services.build_explorer_data_for_tenants()                                             #}
{#   - current_tenant_uuid: str — current tenant UUID, or "" on public                            #}

<main id="explorer-root"
      class="explorer-root"
      data-current-tenant-uuid="{{ current_tenant_uuid|default:'' }}"
      data-i18n-empty="{% translate 'Aucun résultat trouvé.' %}"
      data-i18n-visit="{% translate 'Visiter le lieu' %}"
      data-i18n-lieu="{% translate 'Lieu' %}"
      data-i18n-event="{% translate 'Événement' %}"
      data-i18n-all="{% translate 'Tous' %}"
      data-i18n-current="{% translate 'Vous êtes ici' %}"
      data-i18n-no-events="{% translate 'Pas d\'événement à venir' %}">

    {# Barre de recherche + pills / Search bar + category pills #}
    <div class="explorer-toolbar">
        <div class="explorer-search-row">
            {# name="q" + value pre-rempli : la navbar globale peut soumettre vers /explorer/?q=... #}
            {# / name="q" + pre-filled value: the global navbar can submit to /explorer/?q=... #}
            <input type="search"
                   class="explorer-search"
                   id="explorer-search"
                   name="q"
                   value="{{ request.GET.q|default:'' }}"
                   placeholder="{% translate 'Rechercher un lieu ou un événement...' %}"
                   aria-label="{% translate 'Rechercher' %}">
            <div class="explorer-pills" id="explorer-pills" role="tablist">
                <button class="explorer-pill active" type="button" data-category="all" role="tab"
                        data-testid="explorer-pill-all">{% translate "Tous" %}</button>
                <button class="explorer-pill" type="button" data-category="lieu" role="tab"
                        data-testid="explorer-pill-lieu">{% translate "Lieux" %}</button>
                <button class="explorer-pill" type="button" data-category="event" role="tab"
                        data-testid="explorer-pill-event">{% translate "Événements" %}</button>
            </div>
        </div>
        <div class="explorer-counter" id="explorer-counter" aria-live="polite"></div>
    </div>

    {# Split view : liste + carte / Split view: list + map #}
    <div class="explorer-container">
        <div class="explorer-list"
             id="explorer-list"
             aria-live="polite"
             data-testid="explorer-list"></div>

        <div class="explorer-map" id="explorer-map" data-testid="explorer-map">
            <div class="explorer-map-loading"
                 id="explorer-map-loading"
                 role="status"
                 aria-live="polite">
                <div class="explorer-map-loading-spinner" aria-hidden="true"></div>
                <span class="visually-hidden">{% translate "Chargement de la carte…" %}</span>
            </div>
        </div>
    </div>

    {# Donnees JSON pour le JS / JSON data for JS #}
    {{ explorer_data|json_script:"explorer-data" }}

    {# FAB toggle mobile (carte/liste) — direct enfant de #explorer-root mais position:fixed reste viewport-relative #}
    {# / FAB mobile toggle (map/list) — direct child of #explorer-root but position:fixed stays viewport-relative #}
    <button class="explorer-fab"
            id="explorer-fab"
            type="button"
            aria-label="{% translate 'Basculer carte/liste' %}"
            data-testid="explorer-fab">
        &#128506; <span class="explorer-fab-label">{% translate "Carte" %}</span>
    </button>

</main>
```

- [ ] **Step 6.3 : Verifier qu'il n'y a pas d'ancetre avec `transform`**

Le FAB utilise `position: fixed` et le commentaire dit "stays viewport-relative". Verifier que `seo/base.html` et `reunion/base.html` n'ont pas de `transform` sur des conteneurs parents (avant le `<main>` ou body). Si oui, le FAB perd sa fixation au viewport. C'est une connaissance documentee dans le commentaire CSS du V2.

```bash
grep -nE "transform:" /home/jonas/TiBillet/dev/Lespass/BaseBillet/templates/reunion/base.html /home/jonas/TiBillet/dev/Lespass/seo/templates/seo/base.html
```

Si une regle `transform:` apparait sur un selecteur parent (`html`, `body`, conteneur), on devra remonter le FAB en `body_extras` dans les wrappers au lieu du widget. **Si la sortie est vide ou ne touche que des spans/buttons internes : OK, FAB reste dans le widget.**

---

## Task 7 : Reecrire `seo/templates/seo/explorer.html` (wrapper public)

**Files:**
- Modify: `seo/templates/seo/explorer.html` (replacement complet)

- [ ] **Step 7.1 : Remplacer le contenu**

```django
{% extends "seo/base.html" %}
{% load static i18n %}

{% block extra_head %}
    {# Pas d'indexation : outil interactif, pas une page SEO #}
    {# / No indexing: interactive tool, not a SEO page #}
    <meta name="robots" content="noindex, nofollow">

    {# Leaflet vendore (plus de CDN externe) / Vendored Leaflet (no external CDN) #}
    <link rel="stylesheet" href="{% static 'seo/vendor/leaflet/leaflet.css' %}">
    <link rel="stylesheet" href="{% static 'seo/vendor/leaflet/MarkerCluster.css' %}">
    <link rel="stylesheet" href="{% static 'seo/vendor/leaflet/MarkerCluster.Default.css' %}">

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

- [ ] **Step 7.2 : Verifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
curl -sk -o /tmp/explorer.html -w "HTTP %{http_code} bytes=%{size_download}\n" https://tibillet.localhost/explorer/
grep -c "explorer-root" /tmp/explorer.html
grep -c "vendor/leaflet" /tmp/explorer.html
```

Expected : HTTP 200, byte > 10000, "explorer-root" >= 1, "vendor/leaflet" >= 3.

---

## Task 8 : Creer le wrapper tenant pour `/federation/`

**Files:**
- Create: `BaseBillet/templates/reunion/views/federation/explorer.html`

- [ ] **Step 8.1 : Verifier que les blocks `extra_head` / `extra_js` / `main` existent dans `reunion/base.html`**

```bash
grep -nE "block extra_head|block extra_js|block main" /home/jonas/TiBillet/dev/Lespass/BaseBillet/templates/reunion/base.html
```

Si l'un des 3 blocks manque, il faudra l'ajouter au `base.html` (mini-edit, hors scope strict mais necessaire). Si tous presents : OK.

- [ ] **Step 8.2 : Ecrire le wrapper**

Fichier `BaseBillet/templates/reunion/views/federation/explorer.html` :

```django
{% extends base_template %}
{% load static i18n %}

{# Wrapper tenant : plug le widget explorer dans le skin du tenant. #}
{# Source du widget : seo/templates/seo/partials/explorer_widget.html #}
{# / Tenant wrapper: plugs the explorer widget into the tenant's skin. #}
{# Widget source: seo/templates/seo/partials/explorer_widget.html #}

{% block title %}{% translate 'Réseau local' %}{% endblock %}
{% block meta_description %}{{ config.short_description|striptags|default:config.organisation }} - {% translate 'Réseau local' %}{% endblock %}

{% block extra_head %}
    {# Leaflet vendore (meme source que le public /explorer/) #}
    {# / Vendored Leaflet (same source as public /explorer/) #}
    <link rel="stylesheet" href="{% static 'seo/vendor/leaflet/leaflet.css' %}">
    <link rel="stylesheet" href="{% static 'seo/vendor/leaflet/MarkerCluster.css' %}">
    <link rel="stylesheet" href="{% static 'seo/vendor/leaflet/MarkerCluster.Default.css' %}">
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

- [ ] **Step 8.3 : Verifier**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: `System check identified no issues (0 silenced).`

---

## Task 9 : Reecrire `FederationViewset.list()` pour rendre le widget

**Files:**
- Modify: `BaseBillet/views.py` (methode `FederationViewset.list`)

- [ ] **Step 9.1 : Localiser la methode existante**

```bash
grep -nE "class FederationViewset|def list" /home/jonas/TiBillet/dev/Lespass/BaseBillet/views.py | head -20
```

- [ ] **Step 9.2 : Verifier les imports presents en tete de `BaseBillet/views.py`**

S'assurer que ces imports existent (sinon ajouter en tete) :
- `from django.db import connection`
- `from django.shortcuts import render`
- `from django.utils.translation import gettext_lazy as _`
- `from BaseBillet.models import FederatedPlace, Configuration` (deja la normalement)

- [ ] **Step 9.3 : Reecrire la methode list**

Reperer la methode `list` actuelle de `FederationViewset` et la remplacer par :

```python
    def list(self, request):
        """
        Affiche l'explorer (carte + liste) restreint au tenant courant
        et a ses lieux federes via FederatedPlace.
        / Renders the explorer (map + list) restricted to the current tenant
        and its federated places via FederatedPlace.

        LOCALISATION : BaseBillet/views.py — FederationViewset.list

        Reprend la meme source de donnees que le public /explorer/
        (SEOCache via build_explorer_data_for_tenants) en filtrant
        sur les UUIDs des FederatedPlace + le tenant courant.

        Reuses the same data source as the public /explorer/
        (SEOCache via build_explorer_data_for_tenants) by filtering
        on FederatedPlace UUIDs + the current tenant.
        """
        from seo.services import build_explorer_data_for_tenants

        config = Configuration.get_solo()

        # Construire l'ensemble des UUIDs : federes + tenant courant
        # / Build the UUID set: federated + current tenant
        federated_uuids = {
            str(fp.tenant.uuid)
            for fp in FederatedPlace.objects.select_related('tenant').all()
        }
        current_uuid = str(connection.tenant.uuid)
        federated_uuids.add(current_uuid)

        # Trier pour un ordre stable d'une requete a l'autre
        # / Sort for a stable order across requests
        sorted_uuids = sorted(federated_uuids)
        explorer_data = build_explorer_data_for_tenants(sorted_uuids)

        # Contexte standard du skin + variables specifiques a l'explorer
        # / Standard skin context + explorer-specific variables
        template_context = get_context(request)
        template_context.update({
            'explorer_data': explorer_data,
            'current_tenant_uuid': current_uuid,
            'page_title': _('Réseau local'),
        })

        template_path = get_skin_template(config, "views/federation/explorer.html")
        return render(request, template_path, context=template_context)
```

- [ ] **Step 9.4 : Verifier syntaxe + check Django**

```bash
docker exec lespass_django poetry run python -c "import ast; ast.parse(open('/DjangoFiles/BaseBillet/views.py').read()); print('OK')"
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Both expected: OK / `System check identified no issues (0 silenced).`

- [ ] **Step 9.5 : Tester l'URL en HTTP**

```bash
curl -sk -o /tmp/federation.html -w "HTTP %{http_code} bytes=%{size_download}\n" https://lespass.tibillet.localhost/federation/
grep -c "explorer-root" /tmp/federation.html
grep -c "data-current-tenant-uuid" /tmp/federation.html
```

Expected: HTTP 200, "explorer-root" = 1, "data-current-tenant-uuid" = 1 (avec un UUID non vide).

- [ ] **Step 9.6 : Suggested commit**

```
feat(federation): explorer in-tenant a /federation/ via widget partage

FederationViewset.list rend maintenant le widget seo/explorer_widget.html
avec un perimetre filtre sur FederatedPlace + tenant courant.
Highlight visuel du tenant courant via data-current-tenant-uuid.
```

---

## Task 10 : Supprimer l'ancien template `federation/list.html`

**Files:**
- Delete: `BaseBillet/templates/reunion/views/federation/list.html`

- [ ] **Step 10.1 : Verifier aucune reference**

```bash
docker exec lespass_django bash -c 'cd /DjangoFiles && grep -rn "federation/list" --include="*.py" --include="*.html" 2>/dev/null'
```

Si la sortie ne contient **que** la ligne du fichier lui-meme (path qui finit par `federation/list.html`), on peut supprimer. Si une autre reference apparait (`{% include %}`, `{% extends %}`, etc.) il faut adapter d'abord.

- [ ] **Step 10.2 : Supprimer si propre**

```bash
rm /home/jonas/TiBillet/dev/Lespass/BaseBillet/templates/reunion/views/federation/list.html
ls /home/jonas/TiBillet/dev/Lespass/BaseBillet/templates/reunion/views/federation/
```

Expected: ne reste que `explorer.html` (et eventuellement d'autres sous-fichiers existants comme partials).

- [ ] **Step 10.3 : Verifier check final**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

Expected: `System check identified no issues (0 silenced).`

---

## Task 11 : Tests de non-regression Chrome (CRITIQUE — manuel)

**Files:** aucun (validation manuelle)

> ⚠️ Ce sont des tests **manuels** dans Chrome. A faire AVANT de considerer le chantier fini.

- [ ] **Step 11.1 : Hard-refresh `https://tibillet.localhost/explorer/`**

Ctrl+Shift+R. Verifier :
- Hero + cards explorer charges
- Liste de cards a gauche (5 lieux, 20 events filtrables)
- Carte a droite avec tuiles CartoDB + 5 markers clusters sur Villeurbanne
- Spinner disparait apres init

- [ ] **Step 11.2 : Interactions sur `/explorer/` public**

Tester sequentiellement :
1. Click marker → popup avec nom + events
2. Click card lieu → carte zoome + popup ouvre + accordeon ouvre + scroll vers card
3. Click card event → focus lieu parent
4. Filtre texte ("bal") → liste + markers filtres
5. Pills "Lieux" → seuls les lieux visibles
6. Pills "Événements" → seuls les events
7. Accordeon : ouverture/fermeture single (un seul ouvert a la fois)
8. **Aucun marker `--current`** (couleur par defaut, pas de halo bleu primaire)

- [ ] **Step 11.3 : DevTools sur `/explorer/`**

Console :
```js
typeof window.explorerData; // 'undefined'
typeof window.map;           // 'undefined'
typeof window.markers;       // 'undefined'
typeof window.focusOnLieu;   // 'undefined'
```

Tous = `'undefined'`.

Onglet Network → tous les `leaflet*`, `markercluster*`, `explorer.js`, `explorer.css` sont **chez nous** (`/static/seo/vendor/leaflet/...` ou `/static/seo/...`). **Aucun appel a `unpkg.com`**.

- [ ] **Step 11.4 : Hard-refresh `https://lespass.tibillet.localhost/federation/`**

Verifier :
- Page rendue avec le skin reunion (navbar tenant, footer tenant)
- Toolbar + pills + carte presents
- Marker du tenant courant : couleur primaire (bleu Bootstrap) + halo
- Badge "Vous êtes ici" sur la card du tenant courant dans la liste
- Autres markers = lieux federes (couleur normale blanche)
- Le tenant courant apparait dans la liste avec sa classe `explorer-card--current`

- [ ] **Step 11.5 : Interactions sur `/federation/` tenant**

Memes interactions que step 11.2, mais sur le sous-ensemble fédéré.

- [ ] **Step 11.6 : Visibilite navbar**

Aller dans l'admin tenant, basculer `module_federation` sur False (via dashboard groupware), recharger une page tenant → entree "Réseau local" doit disparaitre de la navbar.

Re-basculer sur True → entree reapparait.

Si on supprime toutes les `FederatedPlace` (admin) → entree disparait (meme avec `module_federation=True`).

- [ ] **Step 11.7 : Etat vide**

Sur un tenant avec **0 FederatedPlace** (apres avoir supprime toutes les FederatedPlace) :
- Acceder a `/federation/` directement (URL tapee, meme si l'entree navbar est cachee)
- Verifier que la page rend avec uniquement le tenant courant sur la carte
- Aucune erreur JS console

- [ ] **Step 11.8 : Console DevTools propre dans les 2 contextes**

Public ET tenant :
- Aucune erreur (cercle rouge)
- Aucune warning non-benigne (Leaflet emet quelques warnings d'init mineurs, OK)

- [ ] **Step 11.9 : Mobile responsive**

Ouvrir DevTools → mode mobile (375px largeur, iPhone) :
- FAB visible (bouton "Carte" en bas)
- Click FAB → bascule vers mode carte plein ecran
- Re-click → revient mode liste
- Toolbar (pills) cachee en mode carte

---

## Task 12 : Documentation chantier + CHANGELOG

**Files:**
- Create: `TECH DOC/SESSIONS/FEDERATION/03-explorer-federation-CHANGELOG.md` (resume des changements)
- Modify: `CHANGELOG.md` (entry court reference au chantier)

- [ ] **Step 12.1 : Ecrire la note de chantier**

Fichier `TECH DOC/SESSIONS/FEDERATION/03-explorer-federation-CHANGELOG.md` :

```markdown
# Chantier Federation #01 — Explorer in-tenant + refactor JS prod

**Date :** 2026-05-13
**Spec :** `01-explorer-in-tenants-design.md`
**Plan :** `02-explorer-implementation-plan.md`
**Statut :** Terminé

## Resume

- `/federation/` sur chaque tenant rend maintenant l'explorer (carte + liste) avec uniquement le tenant courant + ses FederatedPlace
- Le code de la carte (JS, CSS, widget HTML, builder data) est en **source unique** dans `seo/` — utilise a la fois par /explorer/ public et /federation/ tenant
- Le JS a ete entierement refactore : IIFE (zero pollution `window`), event delegation, i18n via `data-i18n-*`, garde-fous defensifs, Leaflet vendore (plus de CDN unpkg.com)
- Marker spécial pour le tenant courant ("Vous êtes ici")

## Fichiers crees

- `seo/static/seo/vendor/leaflet/` (Leaflet 1.9.4 + markercluster 1.5.3 vendores)
- `seo/templates/seo/partials/explorer_widget.html`
- `BaseBillet/templates/reunion/views/federation/explorer.html`

## Fichiers modifies

- `seo/services.py` : refactor `build_explorer_data` en wrapper, ajout `build_explorer_data_for_tenants`
- `seo/views.py` : `explorer()` ajoute `current_tenant_uuid=''`
- `seo/static/seo/explorer.js` : reecriture complete (IIFE + 7 chantiers)
- `seo/static/seo/explorer.css` : -200 lignes mort + ajout `.explorer-pin--current`
- `seo/templates/seo/explorer.html` : simplifie, utilise le widget
- `BaseBillet/views.py` : `FederationViewset.list` reecrit

## Fichier supprime

- `BaseBillet/templates/reunion/views/federation/list.html`

## Tests

Validation manuelle Chrome (cf. spec section "Tests de non-regression Chrome").
Tests pytest/Playwright reportes au chantier "Import tests V2".
```

- [ ] **Step 12.2 : Entree CHANGELOG**

Ajouter en haut de `CHANGELOG.md`, juste sous le titre principal :

```markdown
## Chantier FEDERATION #01 — Explorer in-tenant + refactor JS prod / In-tenant explorer + production-grade JS refactor

**Date :** 2026-05-13
**Migration :** Non
**Contributeurs / Contributors :** JonasFW13 (Jonas)

**FR :** `/federation/` (Réseau local) sur chaque tenant rend maintenant l'explorer
(carte Leaflet + filtres) avec uniquement le tenant courant + ses FederatedPlace.
Le code de la carte est consolidé en source unique dans `seo/` (JS + CSS + widget +
data builder), partagé avec le public `/explorer/`. Le JS a été refactoré pour la
prod : IIFE encapsulé, event delegation, i18n via `data-i18n-*`, garde-fous,
Leaflet vendoré (plus de CDN externe).

**EN :** `/federation/` (Local network) on each tenant now renders the explorer
(Leaflet map + filters) limited to the current tenant + its FederatedPlace.
Map code is consolidated as a single source under `seo/` (JS + CSS + widget +
data builder), shared with the public `/explorer/`. The JS has been refactored
for production: encapsulated IIFE, event delegation, i18n via `data-i18n-*`,
defensive guards, vendored Leaflet (no external CDN anymore).

**Fichiers :** voir `TECH DOC/SESSIONS/FEDERATION/03-explorer-federation-CHANGELOG.md`

---

```

- [ ] **Step 12.3 : Suggested commit**

```
docs(federation): chantier #01 — explorer in-tenant + refactor JS prod

CHANGELOG + note de chantier dans TECH DOC/SESSIONS/FEDERATION/
```

---

## Self-Review

**1. Couverture spec** : Chaque section du spec est tracee dans le plan :

| Spec section | Task(s) |
|---|---|
| Architecture source-unique | Task 6 (widget), Task 7+8 (wrappers), Task 4 (JS), Task 5 (CSS) |
| URL & visibilite tenant | Task 9 (vue) |
| Donnees tenant (current + federated) | Task 9 |
| 1. IIFE | Task 4 |
| 2. Event delegation | Task 4 |
| 3. Vendor Leaflet | Task 3 |
| 4. Plus de timing magique | Task 4 (animationend + fallback) |
| 5. i18n via data-* | Task 4 + Task 6 |
| 6. Garde-fous defensifs | Task 4 |
| 7. Header + commentaires | Task 4 |
| Bonus marker tenant courant | Task 4 (JS) + Task 5 (CSS) |
| Backend services refactor | Task 1 |
| Backend seo/views.py | Task 2 |
| Backend FederationViewset | Task 9 |
| Widget partial | Task 6 |
| Wrapper public | Task 7 |
| Wrapper tenant | Task 8 |
| CSS cleanup | Task 5 |
| Suppression list.html | Task 10 |
| Non-regression Chrome | Task 11 |
| Doc + CHANGELOG | Task 12 |

**2. Placeholders** : aucun "TBD", "TODO", "fill in", "etc.". Chaque Step contient le code ou la commande exacte.

**3. Coherence types** : `build_explorer_data_for_tenants(tenant_uuids)` retourne `{lieux, events}` (Task 1) — meme structure utilisee dans le JS `state.data` (Task 4). `current_tenant_uuid` est `str` partout (vide ou UUID). `state.markers` est un dict `{tenant_id: marker}` coherent entre `addMarkers`, `focusOnLieu`, `updateMapMarkers`.

Plan pret pour execution.
