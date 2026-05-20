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
 *   - state.data : { points: [...], tenants: [...] }  (immutable après init)
 *     points  = 1 entry per PostalAddress active (markers carte)
 *     tenants = 1 entry per alive tenant (cards liste)
 *   - state.filters : { text: '', category: 'all' }  (muable)
 *   - state.map, state.markers (indexes par pa_id), state.markerCluster
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
            current: 'Vous êtes ici',
            lieuSingular: 'lieu',
            lieuPlural: 'lieux',
            eventSingular: 'événement',
            eventPlural: 'événements',
            nextEvents: 'Prochains événements :',
            more: 'autre(s)',
            list: 'Liste',
            map: 'Carte',
            clearTag: 'Effacer le filtre',
            tagEmpty: 'Aucun événement « {tag} » dans la zone visible.',
            moreTags: '+ {count} tags',
        },
    };

    // ============================================================
    // STATE — encapsulé, jamais sur window
    // / STATE — encapsulated, never on window
    // ============================================================
    const state = {
        data: null,
        filters: { text: '', view: 'lieu', tag: null },
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
        tags: null,   // conteneur chips tags / tag chips container
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
        if (ds.i18nCurrent) config.i18n.current = ds.i18nCurrent;
        if (ds.i18nLieuSingular) config.i18n.lieuSingular = ds.i18nLieuSingular;
        if (ds.i18nLieuPlural) config.i18n.lieuPlural = ds.i18nLieuPlural;
        if (ds.i18nEventSingular) config.i18n.eventSingular = ds.i18nEventSingular;
        if (ds.i18nEventPlural) config.i18n.eventPlural = ds.i18nEventPlural;
        if (ds.i18nNextEvents) config.i18n.nextEvents = ds.i18nNextEvents;
        if (ds.i18nMore) config.i18n.more = ds.i18nMore;
        if (ds.i18nList) config.i18n.list = ds.i18nList;
        if (ds.i18nMap) config.i18n.map = ds.i18nMap;
        if (ds.i18nClearTag) config.i18n.clearTag = ds.i18nClearTag;
        if (ds.i18nTagEmpty) config.i18n.tagEmpty = ds.i18nTagEmpty;
        if (ds.i18nMoreTags) config.i18n.moreTags = ds.i18nMoreTags;
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
        dom.tags = document.getElementById('explorer-tags');

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

        bootFromURL();   // pré-remplit state.filters depuis l'URL / pre-fills state.filters from URL

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

    // ============================================================
    // FILTERS — helpers PA-level + event-level
    // / FILTERS — PA-level + event-level helpers
    // ============================================================

    function paMatchesText(point) {
        // Match sur nom PA, nom du tenant, OU nom d'au moins 1 event futur.
        // / Match on PA name, tenant name, OR at least 1 future event name.
        if (!state.filters.text) return true;
        const q = state.filters.text;
        const champs = [
            point.pa_name,
            point.tenant_organisation,
            point.address_display,
        ];
        for (let i = 0; i < champs.length; i++) {
            if ((champs[i] || '').toLowerCase().indexOf(q) !== -1) return true;
        }
        const events = point.events_futurs || [];
        for (let j = 0; j < events.length; j++) {
            if ((events[j].name || '').toLowerCase().indexOf(q) !== -1) return true;
        }
        return false;
    }

    function paMatchesTag(point) {
        // Si pas de tag actif, tout passe. Sinon, au moins 1 event de la PA
        // doit porter le tag.
        // / If no active tag, pass. Otherwise, at least 1 event must carry it.
        if (!state.filters.tag) return true;
        const events = point.events_futurs || [];
        for (let i = 0; i < events.length; i++) {
            const tags = events[i].tags || [];
            for (let j = 0; j < tags.length; j++) {
                if (tags[j].slug === state.filters.tag) return true;
            }
        }
        return false;
    }

    function filterPAsByTextAndTag(points) {
        const result = [];
        for (let i = 0; i < points.length; i++) {
            const point = points[i];
            if (paMatchesText(point) && paMatchesTag(point)) {
                result.push(point);
            }
        }
        return result;
    }

    function collectVisibleEvents(paVisibles) {
        // Aplatit les events futurs de toutes les PA visibles.
        // Si tag actif, ne garde que les events qui portent ce tag.
        // Si text actif, ne garde que les events dont le nom matche (ou la PA matche).
        // / Flatten future events of all visible PAs.
        // Filter by tag and text accordingly.
        const events = [];
        const q = state.filters.text;
        const tagSlug = state.filters.tag;
        for (let i = 0; i < paVisibles.length; i++) {
            const point = paVisibles[i];
            const evList = point.events_futurs || [];
            for (let j = 0; j < evList.length; j++) {
                const ev = evList[j];
                if (tagSlug) {
                    const tags = ev.tags || [];
                    let porteTag = false;
                    for (let k = 0; k < tags.length; k++) {
                        if (tags[k].slug === tagSlug) { porteTag = true; break; }
                    }
                    if (!porteTag) continue;
                }
                if (q) {
                    // Conserver si nom d'event matche OU nom de PA/tenant matche
                    // (la PA est déjà filtrée, mais on filtre encore en mode event).
                    const evMatch = (ev.name || '').toLowerCase().indexOf(q) !== -1;
                    const paMatch = paMatchesText(point);
                    if (!evMatch && !paMatch) continue;
                }
                events.push({
                    uuid: ev.uuid,
                    name: ev.name,
                    datetime_iso: ev.datetime_iso,
                    slug: ev.slug,
                    tags: ev.tags || [],
                    pa_id: point.pa_id,
                    pa_name: point.pa_name,
                    address_display: point.address_display,
                    tenant_id: point.tenant_id,
                    tenant_organisation: point.tenant_organisation,
                    tenant_domain: point.tenant_domain,
                    tenant_logo_url: point.tenant_logo_url,
                });
            }
        }
        events.sort(function (a, b) {
            return (a.datetime_iso || '').localeCompare(b.datetime_iso || '');
        });
        return events;
    }

    function buildLieuCardsFromPAs(paVisibles) {
        // Regroupe les PA visibles par tenant_id. Renvoie liste de "lieu cards"
        // au meme format que state.data.tenants, mais enrichi avec eventsAggregated.
        // / Group visible PAs by tenant_id. Returns "lieu cards" matching
        // state.data.tenants format, enriched with eventsAggregated.
        const parTenant = {};
        for (let i = 0; i < paVisibles.length; i++) {
            const point = paVisibles[i];
            const tid = point.tenant_id;
            if (!parTenant[tid]) parTenant[tid] = { pas: [], events: [] };
            parTenant[tid].pas.push(point);
            const evList = point.events_futurs || [];
            for (let j = 0; j < evList.length; j++) {
                parTenant[tid].events.push(evList[j]);
            }
        }
        // Index des tenants depuis state.data.tenants pour récupérer infos tenant-level
        // / Tenant index from state.data.tenants for tenant-level info
        const tenantsById = {};
        for (let k = 0; k < (state.data.tenants || []).length; k++) {
            const t = state.data.tenants[k];
            tenantsById[t.tenant_id] = t;
        }
        const cards = [];
        for (const tid in parTenant) {
            const t = tenantsById[tid];
            if (!t) continue;
            // Tri events agrégés par date asc, dédoublonné par uuid
            // / Sort aggregated events asc, dedup by uuid
            const seen = {};
            const eventsUniques = [];
            for (let m = 0; m < parTenant[tid].events.length; m++) {
                const ev = parTenant[tid].events[m];
                if (!seen[ev.uuid]) {
                    seen[ev.uuid] = true;
                    eventsUniques.push(ev);
                }
            }
            eventsUniques.sort(function (a, b) {
                return (a.datetime_iso || '').localeCompare(b.datetime_iso || '');
            });
            cards.push({
                tenant_id: t.tenant_id,
                name: t.name,
                domain: t.domain,
                slug: t.slug || '',
                short_description: t.short_description,
                locality: t.locality,
                country: t.country,
                logo_url: t.logo_url,
                events: eventsUniques,
            });
        }
        return cards;
    }

    function applyFilters() {
        if (!state.data) return;

        // 1. Filtre les PA selon text + tag (independamment du mode view).
        // / Filter PAs by text + tag (independent of view mode).
        const paVisibles = filterPAsByTextAndTag(state.data.points || []);

        // 2. Construit la liste affichee selon le mode pill.
        // / Build displayed list according to pill mode.
        let lieuxCards = [];
        let eventCards = [];
        if (state.filters.view === 'lieu') {
            lieuxCards = buildLieuCardsFromPAs(paVisibles);
        } else {
            eventCards = collectVisibleEvents(paVisibles);
        }

        renderList(lieuxCards, eventCards);
        updateCounters(lieuxCards.length, eventCards.length || countEventsInPAs(paVisibles));

        // 3. Markers visibles = PA visibles. Dict pa_id -> true pour update map.
        // / Visible markers = visible PAs. Dict pa_id -> true for map update.
        const visiblePaIds = {};
        for (let i = 0; i < paVisibles.length; i++) {
            visiblePaIds[paVisibles[i].pa_id] = true;
        }
        if (state.mapInitialized) {
            updateMapMarkersByPA(visiblePaIds);
        }

        // 4. Recalculer les chips (Task 8 ajoutera updateChips).
        // / Recompute chips (Task 8 will add updateChips).
        if (typeof updateChips === 'function') {
            updateChips(paVisibles);
        }

        // 5. Synchroniser l'URL (Task 9 ajoutera syncURL).
        // / Sync URL (Task 9 will add syncURL).
        if (typeof syncURL === 'function') {
            syncURL();
        }
    }

    function countEventsInPAs(paVisibles) {
        let n = 0;
        for (let i = 0; i < paVisibles.length; i++) {
            n += ((paVisibles[i].events_futurs || []).length);
        }
        return n;
    }

    function updateCounters(lieuxN, eventsN) {
        if (!dom.counter) return;
        const parts = [
            pluralize(lieuxN, config.i18n.lieuSingular, config.i18n.lieuPlural),
            pluralize(eventsN, config.i18n.eventSingular, config.i18n.eventPlural),
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
        bindTagChips();
    }

    function bindSearch() {
        if (!dom.search) return;
        // Priorité au state (déjà rempli par bootFromURL), sinon valeur du DOM.
        // / state takes priority (filled by bootFromURL), otherwise DOM value.
        if (state.filters.text) {
            dom.search.value = state.filters.text;
        } else {
            const initialValue = dom.search.value.trim().toLowerCase();
            if (initialValue) state.filters.text = initialValue;
        }

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
        // Synchroniser la pill active avec state.filters.view (depuis URL).
        // / Sync active pill with state.filters.view (from URL).
        const allPills = dom.pills.querySelectorAll('.explorer-pill');
        for (let i = 0; i < allPills.length; i++) {
            allPills[i].classList.toggle(
                'active',
                allPills[i].getAttribute('data-category') === state.filters.view
            );
        }
        dom.pills.addEventListener('click', function (ev) {
            const pill = ev.target.closest('.explorer-pill');
            if (!pill) return;
            const allPills = dom.pills.querySelectorAll('.explorer-pill');
            allPills.forEach(function (p) { p.classList.remove('active'); });
            pill.classList.add('active');
            state.filters.view = pill.getAttribute('data-category') || 'lieu';
            applyFilters();
        });
    }

    function bindFAB() {
        if (!dom.fab) return;
        dom.fab.addEventListener('click', toggleView);
    }

    function bindTagChips() {
        if (!dom.tags) return;
        dom.tags.addEventListener('click', function (ev) {
            const moreBtn = ev.target.closest('.explorer-tag-chip-more');
            if (moreBtn) {
                const rest = dom.tags.querySelector('.explorer-tag-chip-rest');
                if (rest) {
                    const willOpen = rest.hidden;
                    rest.hidden = !willOpen;
                    moreBtn.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
                }
                return;
            }
            const chip = ev.target.closest('.explorer-tag-chip');
            if (!chip) return;
            const clickedSlug = chip.getAttribute('data-tag-slug');
            // Toggle exclusif : si déjà actif -> désactiver, sinon -> activer (et désactiver les autres).
            // / Exclusive toggle: if active -> deactivate, otherwise activate (and deactivate others).
            if (state.filters.tag === clickedSlug) {
                state.filters.tag = null;
            } else {
                state.filters.tag = clickedSlug;
            }
            applyFilters();
        });
    }

    /**
     * Event delegation sur #explorer-list : un seul listener gere
     * tous les clicks sur cards lieu, cards event, toggles d'accordeon.
     * / Event delegation on #explorer-list: a single listener handles
     * all clicks on lieu cards, event cards, accordion toggles.
     */
    function bindListDelegation() {
        dom.list.addEventListener('click', function (ev) {
            // Bouton "Effacer le filtre tag" (empty state)
            // / "Clear tag filter" button (empty state)
            const clearBtn = ev.target.closest('#explorer-clear-tag');
            if (clearBtn) {
                state.filters.tag = null;
                applyFilters();
                return;
            }
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
        if (!html) {
            html = buildEmptyStateHtml();
        }
        dom.list.innerHTML = html;
    }

    function buildEmptyStateHtml() {
        // Si tag actif et 0 résultat : message + lien "Effacer le filtre".
        // / If tag is active and 0 results: message + "Clear filter" link.
        if (state.filters.tag) {
            const activeTagName = findTagNameBySlug(state.filters.tag) || state.filters.tag;
            const msg = config.i18n.tagEmpty.replace('{tag}', activeTagName);
            return '<div class="explorer-empty-state" data-testid="explorer-empty-state">'
                + '<p class="text-muted text-center py-3">' + escapeHtml(msg) + '</p>'
                + '<p class="text-center">'
                + '<button type="button" class="btn btn-link"'
                + ' id="explorer-clear-tag" data-testid="explorer-clear-tag">'
                + escapeHtml(config.i18n.clearTag) + '</button></p></div>';
        }
        return '<p class="text-muted text-center py-4">' + escapeHtml(config.i18n.empty) + '</p>';
    }

    function findTagNameBySlug(slug) {
        // Cherche dans les events de state.data.points.
        // / Search in events of state.data.points.
        for (let i = 0; i < (state.data.points || []).length; i++) {
            const evs = state.data.points[i].events_futurs || [];
            for (let j = 0; j < evs.length; j++) {
                const tags = evs[j].tags || [];
                for (let k = 0; k < tags.length; k++) {
                    if (tags[k].slug === slug) return tags[k].name;
                }
            }
        }
        return null;
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
        // Source : lieu.events injecté par buildLieuCardsFromPAs (Task 6).
        // Forme : [{uuid, name, datetime_iso, slug, tags}, ...]
        // / Source: lieu.events injected by buildLieuCardsFromPAs (Task 6).
        const events = lieu.events || [];
        if (events.length === 0) return '';
        const label = pluralize(events.length, config.i18n.eventSingular, config.i18n.eventPlural);
        let items = '';
        for (let i = 0; i < events.length; i++) {
            const ev = events[i];
            const evHref = domain && ev.slug ? 'https://' + domain + '/event/' + ev.slug + '/' : '#';
            const dateLabel = ev.datetime_iso ? formatShortDate(ev.datetime_iso) : '';
            items += ''
                + '<a class="explorer-accordion-item" href="' + escapeHtml(evHref) + '" target="_blank" rel="noopener">'
                    + '<span class="explorer-accordion-icon">\u{1F3B6}</span>'
                    + '<span class="explorer-accordion-name">' + escapeHtml(ev.name) + '</span>'
                    + (dateLabel ? '<span class="explorer-accordion-date">' + escapeHtml(dateLabel) + '</span>' : '')
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
        const tenantId = escapeHtml(event.tenant_id || '');
        const evUrl = (event.tenant_domain && event.slug)
            ? 'https://' + event.tenant_domain + '/event/' + event.slug + '/'
            : '#';
        const datePart = event.datetime_iso
            ? '\u{1F4C5} ' + escapeHtml(formatShortDate(event.datetime_iso))
            : '';
        const lieuPart = event.pa_name ? ' · \u{1F4CD} ' + escapeHtml(event.pa_name) : '';
        const tenantPart = event.tenant_organisation
            ? ' — ' + escapeHtml(event.tenant_organisation)
            : '';
        const metaText = datePart + lieuPart + tenantPart;

        // Tags inline : max 3 affichés.
        // / Inline tags: max 3 displayed.
        let tagsHtml = '';
        const tags = (event.tags || []).slice(0, 3);
        if (tags.length > 0) {
            tagsHtml = '<div class="explorer-card-tags">';
            for (let i = 0; i < tags.length; i++) {
                const t = tags[i];
                tagsHtml += '<span class="explorer-card-tag" style="background-color:'
                    + escapeHtml(t.color || '#0dcaf0') + '">'
                    + escapeHtml(t.name || t.slug) + '</span>';
            }
            tagsHtml += '</div>';
        }

        return ''
            + '<div class="explorer-card explorer-card--event"'
            + ' data-event-uuid="' + escapeHtml(event.uuid || '') + '"'
            + ' data-tenant-id="' + tenantId + '"'
            + ' data-type="event"'
            + ' data-testid="explorer-card-event">'
                + '<div class="explorer-card-icon event">\u{1F3B6}</div>'
                + '<div class="explorer-card-body">'
                    + '<div class="explorer-card-header">'
                        + '<h3 class="explorer-card-title">'
                            + '<a href="' + escapeHtml(evUrl) + '" target="_blank" rel="noopener">'
                            + escapeHtml(event.name) + '</a></h3>'
                        + '<span class="explorer-badge event">' + escapeHtml(config.i18n.event) + '</span>'
                    + '</div>'
                    + '<div class="explorer-card-meta">' + metaText + '</div>'
                    + tagsHtml
                + '</div>'
            + '</div>';
    }

    function renderEmptyState() {
        if (!dom.list) return;
        dom.list.innerHTML = '<p class="text-muted text-center py-4">' + escapeHtml(config.i18n.empty) + '</p>';
        hideMapLoadingSpinner();
    }

    // ============================================================
    // TAG CHIPS — top 10 par fréquence parmi events visibles
    // / TAG CHIPS — top 10 by frequency among visible events
    // ============================================================

    function computeVisibleTagsTop10(paVisibles) {
        // Agrege les tags des events visibles (mode lieu : events de toutes les PA
        // visibles ; mode event : meme chose, le filtre tag s'applique ailleurs).
        // Ne tient pas compte de state.filters.tag (sinon on cacherait le chip actif).
        // / Aggregate tags of visible events. Ignores state.filters.tag (otherwise
        // the active chip would disappear).
        const compteur = {};   // slug -> {slug, name, color, count}
        for (let i = 0; i < paVisibles.length; i++) {
            const evList = paVisibles[i].events_futurs || [];
            for (let j = 0; j < evList.length; j++) {
                const tags = evList[j].tags || [];
                for (let k = 0; k < tags.length; k++) {
                    const t = tags[k];
                    if (!compteur[t.slug]) {
                        compteur[t.slug] = {
                            slug: t.slug, name: t.name, color: t.color, count: 0,
                        };
                    }
                    compteur[t.slug].count += 1;
                }
            }
        }
        const liste = Object.keys(compteur).map(function (k) { return compteur[k]; });
        liste.sort(function (a, b) {
            if (b.count !== a.count) return b.count - a.count;
            return a.name.localeCompare(b.name);
        });
        return {
            top: liste.slice(0, 10),
            rest: liste.slice(10),
        };
    }

    function updateChips(paVisibles) {
        if (!dom.tags) return;
        const grouped = computeVisibleTagsTop10(paVisibles);
        const activeSlug = state.filters.tag;

        // Cache le conteneur si aucun tag a afficher
        // / Hide container if no tag to display
        if (grouped.top.length === 0 && grouped.rest.length === 0) {
            dom.tags.innerHTML = '';
            dom.tags.hidden = true;
            return;
        }
        dom.tags.hidden = false;

        let html = '';
        for (let i = 0; i < grouped.top.length; i++) {
            const t = grouped.top[i];
            html += buildChipHtml(t, t.slug === activeSlug);
        }
        if (grouped.rest.length > 0) {
            const moreLabel = config.i18n.moreTags.replace('{count}', grouped.rest.length);
            html += '<button type="button" class="explorer-tag-chip-more"'
                + ' data-testid="explorer-tag-chip-more"'
                + ' aria-haspopup="true" aria-expanded="false">'
                + escapeHtml(moreLabel) + '</button>'
                + '<div class="explorer-tag-chip-rest" hidden>';
            for (let j = 0; j < grouped.rest.length; j++) {
                html += buildChipHtml(grouped.rest[j], grouped.rest[j].slug === activeSlug);
            }
            html += '</div>';
        }
        dom.tags.innerHTML = html;
    }

    function buildChipHtml(tag, isActive) {
        // Chip bouton : fond = tag.color, état actif = bordure + check.
        // / Chip button: background = tag.color, active state = border + check.
        const cls = 'explorer-tag-chip' + (isActive ? ' explorer-tag-chip--active' : '');
        const check = isActive
            ? '<i class="bi bi-check2" aria-hidden="true"></i> '
            : '';
        return '<button type="button" class="' + cls + '"'
            + ' data-tag-slug="' + escapeHtml(tag.slug) + '"'
            + ' data-testid="explorer-tag-chip-' + escapeHtml(tag.slug) + '"'
            + ' style="--chip-color:' + escapeHtml(tag.color || '#0dcaf0') + '"'
            + ' aria-pressed="' + (isActive ? 'true' : 'false') + '">'
            + check + escapeHtml(tag.name || tag.slug) + '</button>';
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

        addMarkers(state.data.points);
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

    function addMarkers(points) {
        // 1 marker par point (= 1 par PostalAddress active).
        // Indexes state.markers par pa_id (clé unique). state.markersByTenant
        // garde une vue inverse pour focusOnLieu(tenantId).
        // / 1 marker per point (= 1 per active PostalAddress).
        // state.markers indexed by pa_id; state.markersByTenant for reverse lookup.
        if (!state.map || !state.markerCluster) return;
        state.markerCluster.clearLayers();
        state.markers = {};
        state.markersByTenant = {};
        const bounds = [];

        for (let i = 0; i < points.length; i++) {
            const point = points[i];
            const lat = parseFloat(point.latitude);
            const lng = parseFloat(point.longitude);
            if (isNaN(lat) || isNaN(lng)) continue;

            const isCurrent = point.tenant_id === config.currentTenantUuid;
            const pinClass = 'explorer-pin' + (isCurrent ? ' explorer-pin--current' : '');
            // Label du pin = nom de l'adresse (pa_name). Fallback nom du tenant.
            // / Pin label = PA name. Fallback to tenant name.
            const labelTexte = point.pa_name || point.tenant_organisation || '';
            const icon = L.divIcon({
                className: '',
                html: '<div class="' + pinClass + '" data-pa-id="' + escapeHtml(String(point.pa_id))
                    + '" data-tenant-id="' + escapeHtml(point.tenant_id || '') + '">'
                    + escapeHtml(labelTexte) + '</div>',
                iconSize: null,
                iconAnchor: [0, 0],
            });

            const marker = L.marker([lat, lng], { icon: icon, title: labelTexte });
            marker.bindPopup(buildPopupContent(point), { maxWidth: 320 });

            (function (tenantId) {
                marker.on('click', function () { scrollToCard(tenantId); });
            })(point.tenant_id);

            state.markers[point.pa_id] = marker;
            // Reverse lookup tenant_id -> [pa_id...] pour focusOnLieu()
            if (!state.markersByTenant[point.tenant_id]) {
                state.markersByTenant[point.tenant_id] = [];
            }
            state.markersByTenant[point.tenant_id].push(point.pa_id);
            // Priorite : si is_main_address, on l'utilise comme premier ancre
            // / Priority: main_address goes first in the lookup list
            if (point.is_main_address) {
                state.markersByTenant[point.tenant_id].unshift(point.pa_id);
            }

            state.markerCluster.addLayer(marker);
            bounds.push([lat, lng]);
        }

        if (bounds.length > 0) state.map.fitBounds(bounds, { padding: [20, 20] });
        else state.map.setView([46.603354, 1.888334], 6);
    }

    function buildPopupContent(point) {
        // Popup riche : nom PA + adresse + tenant + events futurs (top 5).
        // / Rich popup: PA name + address + tenant + future events (top 5).
        const tenantHref = point.tenant_domain ? 'https://' + point.tenant_domain + '/' : '#';
        let html = '<div class="explorer-popup">'
            + '<h4 class="explorer-popup-title">' + escapeHtml(point.pa_name) + '</h4>';
        if (point.address_display) {
            html += '<p class="explorer-popup-address">' + escapeHtml(point.address_display) + '</p>';
        }
        // Lien tenant (avec logo si dispo)
        // / Tenant link (with logo if available)
        if (point.tenant_domain) {
            const logoImg = point.tenant_logo_url
                ? '<img src="' + escapeHtml(point.tenant_logo_url) + '" alt="" class="explorer-popup-logo">'
                : '';
            html += '<p class="explorer-popup-tenant">' + logoImg
                + '<a href="' + escapeHtml(tenantHref) + '" target="_blank" rel="noopener">'
                + escapeHtml(point.tenant_organisation || '') + ' ↗</a></p>';
        }
        // Events futurs (top 5)
        // / Future events (top 5)
        const events = point.events_futurs || [];
        const totalEvents = point.events_futurs_count_total || events.length;
        if (events.length > 0) {
            html += '<div class="explorer-popup-events"><strong>'
                + escapeHtml(config.i18n.nextEvents) + ' (' + totalEvents + ')</strong>'
                + '<ul class="explorer-popup-events-list">';
            for (let i = 0; i < events.length; i++) {
                const ev = events[i];
                const evUrl = (point.tenant_domain && ev.slug)
                    ? 'https://' + point.tenant_domain + '/event/' + ev.slug + '/'
                    : tenantHref;
                html += '<li><a href="' + escapeHtml(evUrl) + '" target="_blank" rel="noopener">'
                    + escapeHtml(ev.name)
                    + (ev.datetime_iso ? ' — ' + escapeHtml(formatShortDate(ev.datetime_iso)) : '')
                    + '</a></li>';
            }
            html += '</ul>';
            if (totalEvents > events.length) {
                html += '<span class="explorer-popup-events-more">+ '
                    + (totalEvents - events.length) + ' ' + escapeHtml(config.i18n.more) + '</span>';
            }
            html += '</div>';
        }
        html += '<a class="explorer-popup-link" href="' + escapeHtml(tenantHref) + '" target="_blank" rel="noopener">'
            + escapeHtml(config.i18n.visit) + ' →</a></div>';
        return html;
    }

    function updateMapMarkersByPA(visiblePaIds) {
        // Garde les markers des PA visibles, cache les autres.
        // visiblePaIds = dict {pa_id: true}.
        // / Keep visible PA markers, hide others.
        if (!state.mapInitialized) return;

        for (const paId in state.markers) {
            const marker = state.markers[paId];
            const keep = !!visiblePaIds[paId];
            const isVisible = state.markerCluster.hasLayer(marker);
            if (keep && !isVisible) state.markerCluster.addLayer(marker);
            else if (!keep && isVisible) state.markerCluster.removeLayer(marker);
        }
    }

    // ============================================================
    // FOCUS LIEU — zoom + popup + accordeon + highlight
    // / FOCUS LIEU — zoom + popup + accordion + highlight
    // ============================================================

    function focusOnLieu(tenantId) {
        if (window.innerWidth < 992 && state.currentView === 'list') toggleView();
        if (!state.mapInitialized) initMap();
        // 1 tenant peut avoir N markers (N PA). On prend le premier de la liste
        // inversee (qui place is_main_address en tete, cf. addMarkers).
        // / 1 tenant may have N markers (N PAs). Take the first from the reverse
        // lookup list (which places is_main_address first, cf. addMarkers).
        const paIds = (state.markersByTenant && state.markersByTenant[tenantId]) || [];
        if (paIds.length === 0) return;
        const marker = state.markers[paIds[0]];
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
        // CSS.escape() est dispo dans tous les navigateurs modernes (Chrome 46+,
        // Firefox 31+, Safari 10+) et gere correctement TOUS les caracteres CSS
        // dangereux. Fallback minimal pour les vieux navigateurs (échappe juste
        // " et \ — suffisant pour des UUIDs).
        // / CSS.escape() is available in all modern browsers (Chrome 46+,
        // Firefox 31+, Safari 10+) and handles ALL CSS-dangerous characters
        // correctly. Minimal fallback for legacy browsers (escapes only " and \
        // — sufficient for UUIDs).
        if (window.CSS && typeof window.CSS.escape === 'function') {
            return window.CSS.escape(String(value));
        }
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
            if (label) label.textContent = config.i18n.list;
            state.currentView = 'map';
            window.scrollTo({ top: 0, behavior: 'instant' });
            if (!state.mapInitialized) initMap();
            else state.map.invalidateSize();
        } else {
            container.classList.remove('explorer-view-map');
            document.body.classList.remove('explorer-map-active');
            if (label) label.textContent = config.i18n.map;
            state.currentView = 'list';
        }
    }

    // ============================================================
    // URL STATE — sync filters <-> URL via history.replaceState
    // / URL STATE — sync filters <-> URL via history.replaceState
    // ============================================================

    let urlSyncTimer = null;

    function syncURL() {
        // Debounce 300ms pour eviter les rafales lors de la saisie texte.
        // / Debounce 300ms to avoid bursts during text input.
        clearTimeout(urlSyncTimer);
        urlSyncTimer = setTimeout(function () {
            const params = new URLSearchParams();
            if (state.filters.view && state.filters.view !== 'lieu') {
                params.set('v', state.filters.view);
            }
            if (state.filters.text) {
                params.set('q', state.filters.text);
            }
            if (state.filters.tag) {
                params.set('tag', state.filters.tag);
            }
            const qs = params.toString();
            const newUrl = window.location.pathname + (qs ? ('?' + qs) : '');
            try {
                window.history.replaceState({}, '', newUrl);
            } catch (err) {
                // Silently fail si l'historique est restreint (file://, etc.)
                // / Silent fail if history is restricted.
            }
        }, 300);
    }

    function bootFromURL() {
        // Lit les params URL au chargement et pré-sélectionne state.filters.
        // / Read URL params at load, pre-select state.filters.
        try {
            const params = new URLSearchParams(window.location.search);
            const v = params.get('v');
            if (v === 'event' || v === 'lieu') {
                state.filters.view = v;
            }
            const q = params.get('q');
            if (q) {
                state.filters.text = q.toLowerCase();
            }
            const tag = params.get('tag');
            if (tag) {
                // On valide plus tard : si aucun event ne porte ce tag, applyFilters
                // affichera l'empty state — pas de plantage.
                // / Validate later: if no event carries it, applyFilters shows empty state.
                state.filters.tag = tag;
            }
        } catch (err) {
            console.warn('explorer: cannot parse URL params', err);
        }
    }

    // ============================================================
    // ENTRY POINT
    // ============================================================
    //
    // On veut lancer init() dans 2 contextes differents :
    //
    // 1. Chargement complet de la page (F5, navigation directe) :
    //    explorer.js est execute pendant le parse du HTML, le DOM
    //    n'est pas encore pret. On attend l'evenement DOMContentLoaded.
    //
    // 2. Navigation interne via HTMX (la navbar fait hx-target="body"
    //    + hx-swap="innerHTML") : explorer.js est reinjecte dans la
    //    page deja chargee. DOMContentLoaded a deja ete declenche au
    //    chargement initial et ne se redeclenchera plus. Il faut donc
    //    appeler init() immediatement.
    //
    // document.readyState distingue les 2 cas :
    //   - 'loading' : on est dans le cas 1, on attend l'evenement
    //   - 'interactive' ou 'complete' : on est dans le cas 2, on lance direct
    //
    // / Run init() in two contexts:
    // / 1. Full page load (F5, direct navigation): DOM not yet ready,
    // /    wait for DOMContentLoaded.
    // / 2. HTMX navigation (navbar uses hx-target="body" + innerHTML
    // /    swap): script is reinjected after DOMContentLoaded already
    // /    fired, so it would never trigger again. Call init() now.
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
