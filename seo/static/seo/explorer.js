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
            all: 'Tous',
            current: 'Vous êtes ici',
            lieuSingular: 'lieu',
            lieuPlural: 'lieux',
            eventSingular: 'événement',
            eventPlural: 'événements',
            nextEvents: 'Prochains événements :',
            more: 'autre(s)',
            list: 'Liste',
            map: 'Carte',
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
        if (ds.i18nLieuSingular) config.i18n.lieuSingular = ds.i18nLieuSingular;
        if (ds.i18nLieuPlural) config.i18n.lieuPlural = ds.i18nLieuPlural;
        if (ds.i18nEventSingular) config.i18n.eventSingular = ds.i18nEventSingular;
        if (ds.i18nEventPlural) config.i18n.eventPlural = ds.i18nEventPlural;
        if (ds.i18nNextEvents) config.i18n.nextEvents = ds.i18nNextEvents;
        if (ds.i18nMore) config.i18n.more = ds.i18nMore;
        if (ds.i18nList) config.i18n.list = ds.i18nList;
        if (ds.i18nMap) config.i18n.map = ds.i18nMap;
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

        // Cards liste : 1 par tenant. Si pill='event', on ne garde que les
        // tenants qui ont au moins 1 event futur sur l'une de leurs PA.
        // / List cards: 1 per tenant. If pill='event', keep only tenants
        // that have at least 1 future event on one of their PAs.
        let tenantsVisibles = filterCategory(state.data.tenants, 'lieu');
        if (state.filters.category === 'event') {
            const tenantsAvecEvent = collectTenantsWithFutureEvents();
            tenantsVisibles = state.data.tenants.filter(function (t) {
                return tenantsAvecEvent[t.tenant_id] && matchesText(t);
            });
        }

        // Compteur events futurs visibles (sur les tenants visibles)
        // / Visible future events count
        const visibleTenantIds = {};
        for (let i = 0; i < tenantsVisibles.length; i++) {
            visibleTenantIds[tenantsVisibles[i].tenant_id] = true;
        }
        let eventsCount = 0;
        for (let j = 0; j < state.data.points.length; j++) {
            const pt = state.data.points[j];
            if (visibleTenantIds[pt.tenant_id]) {
                eventsCount += (pt.events_futurs_count_total || 0);
            }
        }

        renderList(tenantsVisibles, []);
        updateCounters(tenantsVisibles.length, eventsCount);

        if (state.mapInitialized) {
            updateMapMarkers(visibleTenantIds);
        }
    }

    function collectTenantsWithFutureEvents() {
        // Renvoie un dict {tenant_id: true} pour tenants ayant >=1 event futur
        // / Returns dict of tenant_ids that have >=1 future event
        const result = {};
        for (let i = 0; i < state.data.points.length; i++) {
            const pt = state.data.points[i];
            if ((pt.events_futurs_count_total || 0) > 0) {
                result[pt.tenant_id] = true;
            }
        }
        return result;
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
        const label = pluralize(events.length, config.i18n.eventSingular, config.i18n.eventPlural);
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

    function updateMapMarkers(visibleTenantIds) {
        // Garde tous les markers des tenants visibles, cache les autres.
        // visibleTenantIds = dict {tenant_id: true}.
        // / Keep markers for visible tenants, hide others.
        if (!state.mapInitialized) return;

        for (const paId in state.markers) {
            const marker = state.markers[paId];
            // Recupere tenant_id via icon data-tenant-id (mis dans addMarkers)
            // / Get tenant_id via icon data-tenant-id (set in addMarkers)
            const el = marker.getIcon().options.html;
            const matchTenantId = el && el.match(/data-tenant-id="([^"]*)"/);
            const tenantId = matchTenantId ? matchTenantId[1] : '';
            const keep = !!visibleTenantIds[tenantId];
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
