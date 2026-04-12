/**
 * Explorer — carte Leaflet + liste filtree + toggle mobile.
 * / Explorer — Leaflet map + filtered list + mobile toggle.
 *
 * LOCALISATION: seo/static/seo/explorer.js
 */

// ============================================================
// Etat global / Global state
// ============================================================

var explorerData = null;
var activeFilters = { text: '', category: 'all' };
var map = null;
var markers = {};
var markerClusterGroup = null;
var mapInitialized = false;
var currentView = 'list';

// UUID de l'asset actuellement en mode focus, ou null.
// / UUID of currently focused asset, or null.
var activeAssetUuid = null;

// Layer group Leaflet pour contenir les arcs/polygone du mode focus.
// Vide = clear facile via clearLayers().
// / Leaflet layer group for focus mode arcs/polygon. Empty = easy clear via clearLayers().
var assetLayerGroup = null;

// Icones compacts + libelles courts pour les badges monnaie sur les cards lieu.
// / Compact icons + short labels for asset badges on lieu cards.
var ASSET_BADGE_CONFIG = {
    TLF: { icon: '\u{1F4B0}', label: 'Monnaie locale' },
    TNF: { icon: '\u{1F381}', label: 'Cadeau' },
    TIM: { icon: '\u{23F0}', label: 'Temps' },
    FED: { icon: '\u{1F517}', label: 'Fédéré' },
    FID: { icon: '\u{2B50}', label: 'Fidélité' },
};

// Config des categories : icone, badge, label, builder des champs secondaires.
// / Category config: icon, badge, label, secondary fields builder.
var CATEGORIES = {
    event: {
        icon: '\u{1F3B6}',
        badge: 'Événement',
        className: 'event',
        meta: function(item) {
            var d = item.datetime ? formatShortDate(item.datetime) : '';
            return (d ? '\u{1F4C5} ' + d + ' · ' : '') + (item.lieu_name || '');
        },
    },
    membership: {
        icon: '\u{1F91D}',
        badge: 'Adhésion',
        className: 'membership',
        meta: function(item) { return '\u{1F3DB} ' + (item.lieu_name || ''); },
    },
    initiative: {
        icon: '\u{1F4A1}',
        badge: 'Initiative',
        className: 'initiative',
        meta: function(item) {
            var budget = item.budget_contributif ? ' · Budget contributif' : '';
            return '\u{1F3DB} ' + (item.lieu_name || '') + budget;
        },
    },
    asset: {
        icon: '\u{1FA99}',
        badge: 'Monnaie',
        className: 'asset',
        meta: function(item) {
            var labels = { TLF: 'Monnaie locale', TNF: 'Cadeau', TIM: 'Temps', FED: 'Fédéré', FID: 'Fidélité' };
            return labels[item.category] || item.category;
        },
    },
};

// ============================================================
// Helpers
// ============================================================

function escapeHtml(text) {
    if (!text) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

function pluralize(count, singular, plural) {
    return count + ' ' + (count > 1 ? plural : singular);
}

function formatShortDate(isoString) {
    return new Date(isoString).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
}

// ============================================================
// Initialisation / Initialization
// ============================================================

function init() {
    var dataElement = document.getElementById('explorer-data');
    if (!dataElement) return;
    explorerData = JSON.parse(dataElement.textContent);

    bindSearch();
    bindPills();
    bindFAB();
    applyFilters();

    if (window.innerWidth >= 992) initMap();
}

function bindSearch() {
    var input = document.getElementById('explorer-search');
    if (!input) return;

    var timer = null;
    input.addEventListener('input', function() {
        clearTimeout(timer);
        timer = setTimeout(function() {
            activeFilters.text = input.value.trim().toLowerCase();
            applyFilters();
        }, 300);
    });
}

function bindPills() {
    var pills = document.querySelectorAll('.explorer-pill');
    pills.forEach(function(pill) {
        pill.addEventListener('click', function() {
            pills.forEach(function(p) { p.classList.remove('active'); });
            pill.classList.add('active');
            activeFilters.category = pill.getAttribute('data-category');
            applyFilters();
        });
    });
}

function bindFAB() {
    var fab = document.getElementById('explorer-fab');
    if (!fab) return;
    fab.addEventListener('click', toggleView);
}

// ============================================================
// Filtrage / Filtering
// ============================================================

function matchesText(item) {
    if (!activeFilters.text) return true;
    var q = activeFilters.text;
    var fields = [item.name, item.locality, item.short_description, item.lieu_name];
    for (var i = 0; i < fields.length; i++) {
        if ((fields[i] || '').toLowerCase().indexOf(q) !== -1) return true;
    }
    return false;
}

function filterCategory(sourceArray, categoryName) {
    // Retourne [] si la categorie active ne correspond ni a 'all' ni a categoryName.
    // / Returns [] if active category matches neither 'all' nor categoryName.
    if (activeFilters.category !== 'all' && activeFilters.category !== categoryName) {
        return [];
    }
    return (sourceArray || []).filter(matchesText);
}

function applyFilters() {
    if (!explorerData) return;

    var lieux = filterCategory(explorerData.lieux, 'lieu');
    var events = filterCategory(explorerData.events, 'event');
    var memberships = filterCategory(explorerData.memberships, 'membership');
    var initiatives = filterCategory(explorerData.initiatives, 'initiative');
    var assets = filterCategory(explorerData.assets, 'asset');

    renderList(lieux, events, memberships, initiatives, assets);
    updateCounters(lieux.length, events.length, memberships.length, initiatives.length, assets.length);

    // Calcule les lieux a afficher sur la carte : union des lieux de toutes
    // les categories filtrees (events/memberships/initiatives rattachees a un lieu).
    // / Compute lieux to show on map: union of lieux from all filtered
    // categories (events/memberships/initiatives tied to a lieu).
    if (mapInitialized) {
        var lieuxSurCarte = collectLieuxFromResults(lieux, events, memberships, initiatives, assets);
        updateMapMarkers(lieuxSurCarte);
    }
}

/**
 * Agrege les lieux visibles sur la carte depuis les resultats filtres.
 * Chaque event/adhesion/initiative ajoute le lieu_id a l'ensemble.
 * / Aggregates lieux visible on map from filtered results.
 * Each event/membership/initiative adds its lieu_id to the set.
 */
function collectLieuxFromResults(lieux, events, memberships, initiatives, assets) {
    var lieuIdsVisibles = {};
    for (var i = 0; i < lieux.length; i++) lieuIdsVisibles[lieux[i].tenant_id] = true;
    for (var j = 0; j < events.length; j++) if (events[j].lieu_id) lieuIdsVisibles[events[j].lieu_id] = true;
    for (var k = 0; k < memberships.length; k++) if (memberships[k].lieu_id) lieuIdsVisibles[memberships[k].lieu_id] = true;
    for (var l = 0; l < initiatives.length; l++) if (initiatives[l].lieu_id) lieuIdsVisibles[initiatives[l].lieu_id] = true;

    // Pour les assets filtres, on inclut tous les lieux acceptants.
    // Ainsi, filtrer par "Monnaies" garde les marqueurs sur la carte.
    // / For filtered assets, include all accepting lieux.
    // So filtering by "Monnaies" keeps markers on the map.
    if (assets) {
        for (var a = 0; a < assets.length; a++) {
            var acceptingIds = assets[a].accepting_tenant_ids || [];
            for (var b = 0; b < acceptingIds.length; b++) {
                lieuIdsVisibles[acceptingIds[b]] = true;
            }
        }
    }

    // Retourne la liste complete des objets lieu dont l'id est visible.
    // / Returns the full list of lieu objects whose id is visible.
    var result = [];
    for (var m = 0; m < explorerData.lieux.length; m++) {
        if (lieuIdsVisibles[explorerData.lieux[m].tenant_id]) {
            result.push(explorerData.lieux[m]);
        }
    }
    return result;
}

function updateCounters(lieuxN, eventsN, membersN, initsN, assetsN) {
    var counter = document.getElementById('explorer-counter');
    if (!counter) return;

    var parts = [
        pluralize(lieuxN, 'lieu', 'lieux'),
        pluralize(eventsN, 'événement', 'événements'),
        pluralize(membersN, 'adhésion', 'adhésions'),
    ];
    if (initsN > 0) parts.push(pluralize(initsN, 'initiative', 'initiatives'));
    if (assetsN > 0) parts.push(pluralize(assetsN, 'monnaie', 'monnaies'));
    counter.textContent = parts.join(' · ');
}

// ============================================================
// Rendu liste / List rendering
// ============================================================

function renderList(lieux, events, memberships, initiatives, assets) {
    var container = document.getElementById('explorer-list');
    if (!container) return;

    var html = '';
    for (var i = 0; i < lieux.length; i++) html += buildLieuCard(lieux[i]);
    for (var j = 0; j < events.length; j++) html += buildFlatCard(events[j], 'event');
    for (var k = 0; k < memberships.length; k++) html += buildFlatCard(memberships[k], 'membership');
    for (var l = 0; l < initiatives.length; l++) html += buildFlatCard(initiatives[l], 'initiative');
    for (var m = 0; m < assets.length; m++) html += buildFlatCard(assets[m], 'asset');

    container.innerHTML = html || '<p class="text-muted text-center py-4">Aucun résultat trouvé.</p>';

    if (window.innerWidth >= 992) bindCardHoverEvents();
}

/**
 * Carte d'un lieu (cliquable, focus carte + accordeon events/adhesions/initiatives).
 * / Lieu card (clickable, map focus + events/memberships/initiatives accordion).
 */
function buildLieuCard(lieu) {
    var tenantId = escapeHtml(lieu.tenant_id);
    var domain = lieu.domain || '';
    var href = domain ? 'https://' + domain + '/' : '#';

    var logo = lieu.logo_url
        ? '<img src="' + escapeHtml(lieu.logo_url) + '" alt="" class="explorer-card-icon lieu" style="object-fit:contain;padding:4px;">'
        : '<div class="explorer-card-icon lieu">\u{1F3DB}</div>';

    var meta = lieu.locality
        ? '<div class="explorer-card-meta">\u{1F4CD} ' + escapeHtml(lieu.locality)
            + (lieu.country ? ', ' + escapeHtml(lieu.country) : '') + '</div>'
        : '';
    var desc = lieu.short_description
        ? '<div class="explorer-card-desc">' + escapeHtml(lieu.short_description) + '</div>'
        : '';

    return ''
        + '<div class="explorer-card explorer-card--lieu" data-lieu-id="' + tenantId + '" data-type="lieu">'
            + '<div class="explorer-card-focus" onclick="focusOnLieu(\'' + tenantId + '\')" role="button" tabindex="0" title="Voir sur la carte">'
                + logo
                + '<div class="explorer-card-body">'
                    + '<div class="explorer-card-header">'
                        + '<h3 class="explorer-card-title">' + escapeHtml(lieu.name) + '</h3>'
                        + '<span class="explorer-badge lieu">Lieu</span>'
                    + '</div>'
                    + meta
                    + desc
                    + buildLieuAssetBadges(lieu)
                + '</div>'
            + '</div>'
            + buildAccordion(lieu, domain)
            + '<div class="explorer-card-footer">'
                + '<a href="' + escapeHtml(href) + '" target="_blank" class="explorer-card-link">Visiter le lieu \u2192</a>'
            + '</div>'
        + '</div>';
}

/**
 * Construit la rangee de badges monnaies pour une card lieu.
 * Croise lieu.accepted_asset_ids avec explorerData.assets pour retrouver les donnees.
 * / Builds the asset badges row for a lieu card.
 * Cross-references lieu.accepted_asset_ids with explorerData.assets.
 */
function buildLieuAssetBadges(lieu) {
    var acceptedIds = lieu.accepted_asset_ids || [];
    if (acceptedIds.length === 0) return '';

    // Index rapide des assets par uuid / Quick asset lookup by uuid
    var assetsByUuid = {};
    for (var i = 0; i < explorerData.assets.length; i++) {
        assetsByUuid[explorerData.assets[i].uuid] = explorerData.assets[i];
    }

    var badges = '';
    for (var j = 0; j < acceptedIds.length; j++) {
        var asset = assetsByUuid[acceptedIds[j]];
        if (!asset) continue;
        var config = ASSET_BADGE_CONFIG[asset.category] || { icon: '\u{1F4B0}', label: asset.category };
        var uuidEscaped = escapeHtml(asset.uuid);
        badges += ''
            + '<button type="button" class="lieu-asset-badge" data-asset-uuid="' + uuidEscaped + '"'
            + ' onclick="handleAssetBadgeClick(event, \'' + uuidEscaped + '\')" title="' + escapeHtml(asset.name) + '">'
            + '<span class="lieu-asset-badge-icon">' + config.icon + '</span>'
            + '<span class="lieu-asset-badge-label">' + escapeHtml(config.label) + '</span>'
            + '</button>';
    }

    if (!badges) return '';
    return '<div class="lieu-asset-badges">' + badges + '</div>';
}

/**
 * Handler du clic sur un badge monnaie : empeche la propagation (pas de focus lieu)
 * et delegue a focusOnAsset (implementation en Phase 3).
 * / Asset badge click handler: stops propagation and delegates to focusOnAsset.
 */
function handleAssetBadgeClick(event, assetUuid) {
    event.stopPropagation();
    // focusOnAsset sera defini en Phase 3 (Task 6). En Phase 2, log simple.
    // / focusOnAsset will be defined in Phase 3 (Task 6). For Phase 2, simple log.
    if (typeof focusOnAsset === 'function') {
        focusOnAsset(assetUuid);
    } else {
        console.log('[asset badge] clicked (focus not yet implemented)', assetUuid);
    }
}

function buildAccordion(lieu, domain) {
    var events = lieu.events || [];
    var memberships = lieu.memberships || [];
    var initiatives = lieu.initiatives || [];
    var total = events.length + memberships.length + initiatives.length;
    if (total === 0) return '';

    var parts = [pluralize(events.length, 'événement', 'événements')];
    if (memberships.length > 0) parts.push(pluralize(memberships.length, 'adhésion', 'adhésions'));
    if (initiatives.length > 0) parts.push(pluralize(initiatives.length, 'initiative', 'initiatives'));

    var items = '';
    for (var i = 0; i < events.length; i++) {
        items += buildAccordionItem('\u{1F3B6}', events[i].name,
            events[i].datetime ? formatShortDate(events[i].datetime) : '',
            domain && events[i].slug ? 'https://' + domain + '/event/' + events[i].slug + '/' : '#');
    }
    for (var j = 0; j < memberships.length; j++) {
        items += buildAccordionItem('\u{1F91D}', memberships[j].name, '',
            domain ? 'https://' + domain + '/' : '#');
    }
    for (var k = 0; k < initiatives.length; k++) {
        items += buildAccordionItem('\u{1F4A1}', initiatives[k].name,
            initiatives[k].budget_contributif ? 'Budget contributif' : '',
            domain ? 'https://' + domain + '/crowds/' : '#');
    }

    return ''
        + '<div class="explorer-accordion">'
            + '<button class="explorer-accordion-toggle" onclick="toggleAccordion(event, this)" type="button">'
                + '<span>' + parts.join(' · ') + '</span>'
                + '<i class="bi bi-chevron-down explorer-accordion-chevron"></i>'
            + '</button>'
            + '<div class="explorer-accordion-panel">' + items + '</div>'
        + '</div>';
}

function buildAccordionItem(icon, name, date, href) {
    return ''
        + '<a class="explorer-accordion-item" href="' + escapeHtml(href) + '" target="_blank">'
            + '<span class="explorer-accordion-icon">' + icon + '</span>'
            + '<span class="explorer-accordion-name">' + escapeHtml(name) + '</span>'
            + (date ? '<span class="explorer-accordion-date">' + escapeHtml(date) + '</span>' : '')
        + '</a>';
}

/**
 * Carte "plate" (event, membership, initiative, asset).
 * Clic = focus carte sur le lieu parent, sauf pour les assets (globaux).
 * / Flat card (event, membership, initiative, asset).
 * Click = map focus on parent lieu, except assets (global).
 */
/**
 * Carte "plate" (event, membership, initiative, asset).
 * Clic = focus carte sur le lieu parent, sauf pour asset (focus carte sur la monnaie).
 * / Flat card (event, membership, initiative, asset).
 * Click = map focus on parent lieu, except for asset (map focus on the currency).
 */
function buildFlatCard(item, categoryName) {
    // Les assets ont leur propre builder (accordeon + focus carte)
    // / Assets have their own builder (accordion + map focus)
    if (categoryName === 'asset') {
        return buildAssetCard(item);
    }

    var cat = CATEGORIES[categoryName];
    var lieuId = escapeHtml(item.lieu_id || '');
    var desc = item.short_description
        ? '<div class="explorer-card-desc">' + escapeHtml(item.short_description) + '</div>'
        : '';

    var clickAttr = lieuId
        ? ' onclick="focusOnLieu(\'' + lieuId + '\')" role="button" tabindex="0"'
        : '';
    var lieuAttr = lieuId ? ' data-lieu-id="' + lieuId + '"' : '';

    return ''
        + '<div class="explorer-card"' + clickAttr + lieuAttr + ' data-type="' + categoryName + '">'
            + '<div class="explorer-card-icon ' + cat.className + '">' + cat.icon + '</div>'
            + '<div class="explorer-card-body">'
                + '<div class="explorer-card-header">'
                    + '<h3 class="explorer-card-title">' + escapeHtml(item.name) + '</h3>'
                    + '<span class="explorer-badge ' + cat.className + '">' + cat.badge + '</span>'
                + '</div>'
                + '<div class="explorer-card-meta">' + escapeHtml(cat.meta(item)) + '</div>'
                + desc
            + '</div>'
        + '</div>';
}

/**
 * Card monnaie : header cliquable (focus carte) + accordeon avec la liste
 * des lieux acceptants (cliquables pour zoomer sur chaque lieu).
 * / Asset card: clickable header (map focus) + accordion listing the accepting
 * lieux (each clickable to zoom on the lieu).
 */
function buildAssetCard(asset) {
    var cat = CATEGORIES.asset;
    var assetUuid = escapeHtml(asset.uuid || '');
    var badgeConfig = ASSET_BADGE_CONFIG[asset.category] || { icon: '\u{1F4B0}', label: asset.category };
    var assetIcon = badgeConfig.icon;

    // Meta simplifiee : catégorie + origine + compte
    // / Simplified meta: category + origin + count
    var metaParts = [escapeHtml(badgeConfig.label)];
    if (asset.tenant_origin_name) {
        metaParts.push('Origine : ' + escapeHtml(asset.tenant_origin_name));
    }
    if (asset.accepting_count > 1) {
        metaParts.push('Accepté par ' + asset.accepting_count + ' lieux');
    } else if (asset.accepting_count === 1) {
        metaParts.push('Local à 1 lieu');
    }
    var metaLine = metaParts.join(' · ');

    // Accordeon : liste des lieux acceptants (croise avec explorerData.lieux)
    // / Accordion: list of accepting lieux (cross-referenced with explorerData.lieux)
    var accordionHtml = buildAssetAccordion(asset);

    return ''
        + '<div class="explorer-card explorer-card--asset"'
        + ' data-asset-uuid="' + assetUuid + '" data-type="asset">'
            + '<div class="explorer-card-focus" onclick="focusOnAsset(\'' + assetUuid + '\')" role="button" tabindex="0" title="Voir sur la carte">'
                + '<div class="explorer-card-icon ' + cat.className + '">' + assetIcon + '</div>'
                + '<div class="explorer-card-body">'
                    + '<div class="explorer-card-header">'
                        + '<h3 class="explorer-card-title">' + escapeHtml(asset.name) + '</h3>'
                        + '<span class="explorer-badge ' + cat.className + '">' + cat.badge + '</span>'
                    + '</div>'
                    + '<div class="explorer-card-meta">' + metaLine + '</div>'
                + '</div>'
            + '</div>'
            + accordionHtml
        + '</div>';
}

/**
 * Accordeon des lieux acceptants pour une monnaie.
 * Masque si 0 ou 1 lieu (pas d'interet a lister).
 * / Accepting lieux accordion for an asset.
 * Hidden if 0 or 1 lieu (no point listing).
 */
function buildAssetAccordion(asset) {
    var acceptingIds = asset.accepting_tenant_ids || [];
    if (acceptingIds.length < 2) return '';

    // Index rapide des lieux connus par tenant_id
    // / Quick lookup of known lieux by tenant_id
    var lieuxByTenantId = {};
    for (var i = 0; i < explorerData.lieux.length; i++) {
        lieuxByTenantId[explorerData.lieux[i].tenant_id] = explorerData.lieux[i];
    }

    // Construire la liste des items (lieux connus seulement)
    // / Build items list (known lieux only)
    var items = '';
    var knownCount = 0;
    for (var j = 0; j < acceptingIds.length; j++) {
        var lieu = lieuxByTenantId[acceptingIds[j]];
        if (!lieu) continue;
        knownCount++;
        var lieuId = escapeHtml(lieu.tenant_id);
        items += ''
            + '<button type="button" class="explorer-accordion-item"'
            + ' onclick="focusOnLieu(\'' + lieuId + '\')">'
                + '<span class="explorer-accordion-icon">\u{1F3DB}</span>'
                + '<span class="explorer-accordion-name">' + escapeHtml(lieu.name) + '</span>'
            + '</button>';
    }

    if (knownCount === 0) return '';

    return ''
        + '<div class="explorer-accordion">'
            + '<button class="explorer-accordion-toggle" onclick="toggleAccordion(event, this)" type="button">'
                + '<span>' + knownCount + ' lieu' + (knownCount > 1 ? 'x' : '') + ' acceptant cette monnaie</span>'
                + '<i class="bi bi-chevron-down explorer-accordion-chevron"></i>'
            + '</button>'
            + '<div class="explorer-accordion-panel">' + items + '</div>'
        + '</div>';
}

// ============================================================
// Carte Leaflet / Leaflet map
// ============================================================

function initMap() {
    if (mapInitialized) return;
    if (!document.getElementById('explorer-map')) return;

    map = L.map('explorer-map', { zoomControl: true, scrollWheelZoom: true });

    // Tuiles CartoDB Voyager : pas de restriction referer (OSM bloque en localhost).
    // / CartoDB Voyager tiles: no referer restriction (OSM blocks on localhost).
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
        maxZoom: 19,
        subdomains: 'abcd',
    }).addTo(map);

    markerClusterGroup = L.markerClusterGroup();
    map.addLayer(markerClusterGroup);

    // Layer group dedie au mode focus asset (arcs, hull).
    // Ajoute apres markerClusterGroup pour passer AU-DESSUS des markers.
    // / Dedicated layer group for asset focus mode (arcs, hull).
    // Added after markerClusterGroup to render ABOVE markers.
    assetLayerGroup = L.layerGroup();
    map.addLayer(assetLayerGroup);

    addMarkers(explorerData.lieux);
    mapInitialized = true;

    // Re-applique les filtres pour synchroniser les marqueurs avec l'etat actuel.
    // Important sur mobile ou la carte est initialisee tardivement (au 1er toggle).
    // / Re-apply filters to sync markers with current state.
    // Important on mobile where the map is initialized lazily (on first toggle).
    applyFilters();
}

function addMarkers(lieux) {
    if (!map || !markerClusterGroup) return;
    markerClusterGroup.clearLayers();
    markers = {};
    var bounds = [];

    for (var i = 0; i < lieux.length; i++) {
        var lieu = lieux[i];
        var lat = parseFloat(lieu.latitude);
        var lng = parseFloat(lieu.longitude);
        if (isNaN(lat) || isNaN(lng)) continue;

        var icon = L.divIcon({
            className: '',
            html: '<div class="explorer-pin" data-lieu-id="' + escapeHtml(lieu.tenant_id) + '">'
                + escapeHtml(lieu.name) + '</div>',
            iconSize: null,
            iconAnchor: [0, 0],
        });

        var marker = L.marker([lat, lng], { icon: icon });
        marker.bindPopup(buildPopupContent(lieu), { maxWidth: 280 });

        // Closure pour capturer tenant_id / Closure to capture tenant_id
        (function(tenantId) {
            marker.on('click', function() { scrollToCard(tenantId); });
        })(lieu.tenant_id);

        markers[lieu.tenant_id] = marker;
        markerClusterGroup.addLayer(marker);
        bounds.push([lat, lng]);
    }

    if (bounds.length > 0) map.fitBounds(bounds, { padding: [20, 20] });
    else map.setView([46.603354, 1.888334], 6);
}

function buildPopupContent(lieu) {
    var href = lieu.domain ? 'https://' + lieu.domain + '/' : '#';
    var html = '<div class="explorer-popup">'
        + '<h4 class="explorer-popup-title">' + escapeHtml(lieu.name) + '</h4>';

    if (lieu.short_description) {
        html += '<p class="explorer-popup-desc">' + escapeHtml(lieu.short_description) + '</p>';
    }
    if (lieu.locality) {
        html += '<p class="explorer-popup-stats">\u{1F4CD} ' + escapeHtml(lieu.locality)
            + (lieu.country ? ', ' + escapeHtml(lieu.country) : '') + '</p>';
    }

    html += buildPopupList(lieu.events, 'Prochains événements', 3, function(ev) {
        return escapeHtml(ev.name) + (ev.datetime ? ' — ' + formatShortDate(ev.datetime) : '');
    });
    html += buildPopupList(lieu.memberships, 'Adhésions', 2, function(mb) {
        return escapeHtml(mb.name);
    });

    html += '<a class="explorer-popup-link" href="' + escapeHtml(href) + '" target="_blank">Visiter le lieu \u2192</a>'
        + '</div>';
    return html;
}

function buildPopupList(items, title, max, formatter) {
    items = items || [];
    if (items.length === 0) return '';

    var html = '<div class="explorer-popup-events"><strong>' + title + ' :</strong>'
        + '<ul style="margin:4px 0;padding-left:16px;">';
    var n = Math.min(items.length, max);
    for (var i = 0; i < n; i++) html += '<li>' + formatter(items[i]) + '</li>';
    html += '</ul>';
    if (items.length > max) {
        html += '<span style="font-size:11px;color:#999;">+ ' + (items.length - max) + ' autre(s)</span>';
    }
    return html + '</div>';
}

function updateMapMarkers(filteredLieux) {
    if (!mapInitialized) return;
    var keep = {};
    for (var i = 0; i < filteredLieux.length; i++) keep[filteredLieux[i].tenant_id] = true;

    for (var tenantId in markers) {
        var marker = markers[tenantId];
        var isVisible = markerClusterGroup.hasLayer(marker);
        if (keep[tenantId] && !isVisible) markerClusterGroup.addLayer(marker);
        else if (!keep[tenantId] && isVisible) markerClusterGroup.removeLayer(marker);
    }
}

// ============================================================
// Focus carte + accordeon + cross-highlighting
// ============================================================

/**
 * Focus la carte sur un lieu : zoom + popup + highlight + accordeon (desktop).
 * / Focus the map on a lieu: zoom + popup + highlight + accordion (desktop).
 */
function focusOnLieu(tenantId) {
    // Bascule en mode carte sur mobile si on est en mode liste.
    // / Switch to map view on mobile if currently in list mode.
    if (window.innerWidth < 992 && currentView === 'list') toggleView();

    if (!mapInitialized) initMap();
    var marker = markers[tenantId];
    if (!marker) return;

    map.setView(marker.getLatLng(), 15, { animate: true });
    // Attendre la desagregation du cluster / Wait for cluster unspiderfy
    setTimeout(function() { marker.openPopup(); }, 400);

    highlightPin(tenantId);

    // Desktop : auto-ouvre l'accordeon du lieu et scrolle la liste vers lui.
    // / Desktop: auto-open the lieu's accordion and scroll list to it.
    if (window.innerWidth >= 992) {
        openLieuAccordion(tenantId);
    }
}

function highlightPin(tenantId) {
    var pin = document.querySelector('.explorer-pin[data-lieu-id="' + tenantId + '"]');
    if (!pin) return;
    pin.classList.add('selected');
    setTimeout(function() { pin.classList.remove('selected'); }, 3000);
}

/**
 * Comportement "single accordion" : un seul accordeon ouvert a la fois.
 * - Clic sur un lieu dont l'accordeon est ferme : ferme les autres, ouvre celui-ci.
 * - Clic sur le meme lieu dont l'accordeon est ouvert : le ferme (toggle).
 * / "Single accordion" behavior: only one accordion open at a time.
 * - Click on a lieu with closed accordion: close others, open this one.
 * - Click on the same lieu with open accordion: close it (toggle).
 */
function openLieuAccordion(tenantId) {
    var card = document.querySelector('.explorer-card--lieu[data-lieu-id="' + tenantId + '"]');
    if (!card) return;

    var panel = card.querySelector('.explorer-accordion-panel');
    var wasOpen = panel && panel.classList.contains('open');

    // Ferme tous les autres accordeons ouverts.
    // / Close all other open accordions.
    closeAllAccordionsExcept(tenantId);

    if (panel) {
        setAccordionState(card, !wasOpen);
    }
    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function closeAllAccordionsExcept(cardIdentifier) {
    // Ferme les accordeons des cards lieu ET des cards asset, sauf celle ciblee.
    // / Closes accordions on both lieu and asset cards, except the targeted one.
    var allCards = document.querySelectorAll('.explorer-card--lieu, .explorer-card--asset');
    for (var i = 0; i < allCards.length; i++) {
        var card = allCards[i];
        var tenantId = card.getAttribute('data-lieu-id');
        var assetUuid = card.getAttribute('data-asset-uuid');
        if (tenantId === cardIdentifier || assetUuid === cardIdentifier) continue;
        setAccordionState(card, false);
    }
}

function setAccordionState(card, shouldBeOpen) {
    var panel = card.querySelector('.explorer-accordion-panel');
    var chevron = card.querySelector('.explorer-accordion-chevron');
    if (!panel) return;

    panel.classList.toggle('open', shouldBeOpen);
    panel.style.maxHeight = shouldBeOpen ? panel.scrollHeight + 'px' : null;
    if (chevron) chevron.style.transform = shouldBeOpen ? 'rotate(180deg)' : '';
}

function toggleAccordion(event, button) {
    // Empeche le declenchement du focus carte de la card parente.
    // / Prevents parent card's map focus from triggering.
    event.stopPropagation();

    // Supporte les cards lieu ET asset. / Supports both lieu and asset cards.
    var card = button.closest('.explorer-card--lieu, .explorer-card--asset');
    if (!card) return;

    var panel = card.querySelector('.explorer-accordion-panel');
    var willOpen = !panel.classList.contains('open');

    // Ferme les autres accordeons avant d'ouvrir celui-ci.
    // L'identifiant est soit data-lieu-id (card lieu) soit data-asset-uuid (card asset).
    // / Close other accordions before opening this one.
    // Identifier is either data-lieu-id (lieu card) or data-asset-uuid (asset card).
    if (willOpen) {
        var cardId = card.getAttribute('data-lieu-id') || card.getAttribute('data-asset-uuid');
        closeAllAccordionsExcept(cardId);
    }
    setAccordionState(card, willOpen);
}

function bindCardHoverEvents() {
    document.querySelectorAll('.explorer-card[data-lieu-id]').forEach(function(card) {
        var id = card.getAttribute('data-lieu-id');
        card.addEventListener('mouseenter', function() { highlightPinClass(id, true); });
        card.addEventListener('mouseleave', function() { highlightPinClass(id, false); });
    });
}

function highlightPinClass(tenantId, isOn) {
    var pin = document.querySelector('.explorer-pin[data-lieu-id="' + tenantId + '"]');
    if (pin) pin.classList.toggle('selected', isOn);
}

function scrollToCard(tenantId) {
    var card = document.querySelector('.explorer-card[data-lieu-id="' + tenantId + '"][data-type="lieu"]');
    if (!card) return;
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    card.setAttribute('data-highlighted', 'true');
    setTimeout(function() { card.removeAttribute('data-highlighted'); }, 2000);
}

// ============================================================
// Toggle mobile / Mobile toggle
// ============================================================

function toggleView() {
    var container = document.querySelector('.explorer-container');
    var fab = document.getElementById('explorer-fab');
    var label = fab ? fab.querySelector('.explorer-fab-label') : null;
    if (!container || !fab) return;

    if (currentView === 'list') {
        container.classList.add('explorer-view-map');
        // Classe sur body pour masquer le footer en CSS (pas atteignable
        // depuis .explorer-view-map car footer est hors du container).
        // / Class on body to hide footer via CSS (footer is outside the container).
        document.body.classList.add('explorer-map-active');
        if (label) label.textContent = 'Liste';
        currentView = 'map';

        // Scroll en haut de la page pour voir la carte en entier.
        // / Scroll to top of page to see the full map.
        window.scrollTo({ top: 0, behavior: 'instant' });

        if (!mapInitialized) initMap();
        else map.invalidateSize();
    } else {
        container.classList.remove('explorer-view-map');
        document.body.classList.remove('explorer-map-active');
        if (label) label.textContent = 'Carte';
        currentView = 'list';
    }
}

// ============================================================
// Mode focus asset / Asset focus mode
// ============================================================

/**
 * Active le mode focus sur une monnaie : highlight des lieux acceptants,
 * dim des autres, dessin des liaisons (arcs ou polygone) sur la carte.
 * Si l'asset est deja actif, on desactive (toggle).
 * / Activate asset focus: highlight accepting lieux, dim others, draw links
 * (arcs or polygon) on map. If asset already active, deactivate (toggle).
 */
function focusOnAsset(assetUuid) {
    // Toggle : si meme asset clique 2 fois, on sort du mode focus.
    // / Toggle: same asset clicked twice exits focus mode.
    if (activeAssetUuid === assetUuid) {
        clearAssetFocus();
        return;
    }

    var asset = findAssetByUuid(assetUuid);
    if (!asset) return;

    // Init carte si pas encore fait / Init map if not done yet
    if (!mapInitialized) initMap();

    // Sur mobile, basculer en vue carte / On mobile, switch to map view
    if (window.innerWidth < 992 && currentView === 'list') toggleView();

    activeAssetUuid = assetUuid;
    applyDimming(asset.accepting_tenant_ids || []);
    drawAssetLinks(asset);
    renderAssetLegend(asset);
    refreshAssetBadgeActiveState();
    refreshMapMarkersForFocus(asset);
}

function clearAssetFocus() {
    activeAssetUuid = null;
    applyDimming(null);
    if (assetLayerGroup) assetLayerGroup.clearLayers();
    renderAssetLegend(null);
    refreshAssetBadgeActiveState();
    // Remettre les marqueurs a l'etat "applique filtres" / Reapply filters to markers
    applyFilters();
}

function findAssetByUuid(uuid) {
    if (!explorerData || !explorerData.assets) return null;
    for (var i = 0; i < explorerData.assets.length; i++) {
        if (explorerData.assets[i].uuid === uuid) return explorerData.assets[i];
    }
    return null;
}

/**
 * Applique la classe CSS dimmed aux marqueurs non acceptants.
 * Si acceptingIds est null, retire le dimming partout.
 * / Apply dimmed CSS class to non-accepting markers.
 * If acceptingIds is null, remove dimming everywhere.
 */
function applyDimming(acceptingIds) {
    var pinElements = document.querySelectorAll('.explorer-pin');
    if (!acceptingIds) {
        pinElements.forEach(function(el) { el.classList.remove('explorer-pin--dimmed'); });
        return;
    }
    var acceptingSet = {};
    for (var i = 0; i < acceptingIds.length; i++) acceptingSet[acceptingIds[i]] = true;
    pinElements.forEach(function(el) {
        var id = el.getAttribute('data-lieu-id');
        if (acceptingSet[id]) el.classList.remove('explorer-pin--dimmed');
        else el.classList.add('explorer-pin--dimmed');
    });
}

/**
 * Restaure les marqueurs sur la carte en mode focus : tous les lieux
 * (acceptants + dimmed) doivent rester visibles pour lire les liaisons.
 * / Refresh map markers in focus mode: all lieux (accepting + dimmed)
 * remain visible to read the connections.
 */
function refreshMapMarkersForFocus(asset) {
    if (!mapInitialized) return;
    // En mode focus, on affiche TOUS les lieux (pour que le dimming
    // ait du sens et que les connexions soient lisibles).
    // / In focus mode, we show ALL lieux (so dimming makes sense
    // and connections are readable).
    updateMapMarkers(explorerData.lieux);
    // Fit bounds sur les lieux acceptants uniquement pour zoomer dessus.
    // / Fit bounds on accepting lieux only to zoom on them.
    var acceptingLatLngs = [];
    for (var i = 0; i < asset.accepting_tenant_ids.length; i++) {
        var marker = markers[asset.accepting_tenant_ids[i]];
        if (marker) acceptingLatLngs.push(marker.getLatLng());
    }
    if (acceptingLatLngs.length > 0) {
        map.fitBounds(L.latLngBounds(acceptingLatLngs), { padding: [40, 40], maxZoom: 14 });
    }
}

/**
 * Met a jour la classe active sur les badges monnaie des cards lieu.
 * / Update active class on asset badges of lieu cards.
 */
/**
 * Met a jour la classe active sur les badges monnaie des cards lieu
 * ET sur les cards monnaie de la liste plate.
 * / Update active class on asset badges of lieu cards
 * AND on asset cards in the flat list.
 */
function refreshAssetBadgeActiveState() {
    // Badges monnaie sur les cards lieu / Asset badges on lieu cards
    document.querySelectorAll('.lieu-asset-badge').forEach(function(badge) {
        var badgeUuid = badge.getAttribute('data-asset-uuid');
        badge.classList.toggle('lieu-asset-badge--active', badgeUuid === activeAssetUuid);
    });
    // Cards monnaie dans la liste / Asset cards in the list
    document.querySelectorAll('.explorer-card[data-asset-uuid]').forEach(function(card) {
        var cardUuid = card.getAttribute('data-asset-uuid');
        card.classList.toggle('explorer-card--active', cardUuid === activeAssetUuid);
    });
}

/**
 * Convex hull via algorithme de Graham scan (implementation simple).
 * / Convex hull via Graham scan algorithm (simple implementation).
 *
 * Retourne les points du hull dans l'ordre (pour tracer un polygone).
 * / Returns hull points in order (for polygon drawing).
 *
 * Entree : tableau de [lat, lng] / Input: array of [lat, lng]
 */
function computeConvexHull(points) {
    if (points.length < 3) return points.slice();

    // Trier par lng puis lat pour avoir un ordre deterministe.
    // / Sort by lng then lat for deterministic order.
    var sorted = points.slice().sort(function(a, b) {
        return a[1] - b[1] || a[0] - b[0];
    });

    // Cross product pour tester le sens du virage (anti-horaire > 0).
    // / Cross product to test turn direction (counter-clockwise > 0).
    function cross(o, a, b) {
        return (a[1] - o[1]) * (b[0] - o[0]) - (a[0] - o[0]) * (b[1] - o[1]);
    }

    // Lower hull
    var lower = [];
    for (var i = 0; i < sorted.length; i++) {
        while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], sorted[i]) <= 0) {
            lower.pop();
        }
        lower.push(sorted[i]);
    }

    // Upper hull
    var upper = [];
    for (var j = sorted.length - 1; j >= 0; j--) {
        while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], sorted[j]) <= 0) {
            upper.pop();
        }
        upper.push(sorted[j]);
    }

    // Concatener sans les doublons en bout / Concat without end duplicates
    lower.pop();
    upper.pop();
    return lower.concat(upper);
}

/**
 * Dessine un polygone translucide englobant les lieux acceptants (style B).
 * Utilise pour les assets federes primaires (TiBillet, category FED).
 * Si 2 points seulement, trace une ligne. Si 1 point, rien.
 * / Draws a translucent polygon around accepting lieux (style B).
 * Used for primary federated assets (TiBillet, category FED).
 * 2 points → polyline. 1 point → nothing.
 */
function drawHull(latLngs) {
    if (!assetLayerGroup || latLngs.length < 2) return;

    // 2 points : polyline epaisse / 2 points: thick polyline
    if (latLngs.length === 2) {
        L.polyline(latLngs, {
            color: '#259d49',
            weight: 3,
            opacity: 0.7,
        }).addTo(assetLayerGroup);
        return;
    }

    // 3+ points : convex hull polygon
    var pointsAsArray = latLngs.map(function(ll) { return [ll.lat, ll.lng]; });
    var hull = computeConvexHull(pointsAsArray);

    L.polygon(hull, {
        color: '#259d49',
        weight: 1.5,
        fillColor: '#259d49',
        fillOpacity: 0.22,
        opacity: 0.7,
    }).addTo(assetLayerGroup);
}

/**
 * Dessine des arcs courbes depuis le lieu origine vers chaque lieu acceptant (style C).
 * Implementation : L.polyline avec points d'une courbe de Bezier quadratique
 * discretisee (pas de plugin externe).
 * / Draws curved arcs from origin lieu to each accepting lieu (style C).
 * Uses L.polyline with points from a discretized quadratic Bezier curve (no plugin).
 *
 * @param {string} originId - tenant_id du lieu origine
 * @param {string[]} acceptingIds - tous les tenant_id acceptant (origine incluse, sera filtree)
 */
function drawArcs(originId, acceptingIds) {
    if (!assetLayerGroup) return;
    var originMarker = markers[originId];
    if (!originMarker) return;

    var originLatLng = originMarker.getLatLng();

    for (var i = 0; i < acceptingIds.length; i++) {
        var targetId = acceptingIds[i];
        if (targetId === originId) continue;  // skip origine
        var targetMarker = markers[targetId];
        if (!targetMarker) continue;

        var targetLatLng = targetMarker.getLatLng();
        var arcPoints = bezierArcPoints(originLatLng, targetLatLng, 20);

        L.polyline(arcPoints, {
            color: '#259d49',
            weight: 2,
            opacity: 0.7,
        }).addTo(assetLayerGroup);
    }
}

/**
 * Calcule les points d'une courbe de Bezier quadratique entre deux points.
 * Le point de controle est au milieu, decale orthogonalement vers le "haut"
 * (ici en latitude) de 0.3 * distance.
 * / Computes points of a quadratic Bezier curve between two points.
 * Control point is at midpoint, offset orthogonally "upward" (latitude)
 * by 0.3 * distance.
 *
 * @param {L.LatLng} start
 * @param {L.LatLng} end
 * @param {number} segments - nombre de segments de la discretisation
 * @returns {L.LatLng[]} tableau de points sur la courbe (format [lat, lng])
 */
function bezierArcPoints(start, end, segments) {
    var midLat = (start.lat + end.lat) / 2;
    var midLng = (start.lng + end.lng) / 2;
    var dLat = end.lat - start.lat;
    var dLng = end.lng - start.lng;

    // Vecteur orthogonal (rotation 90 deg) pour decaler le point de controle vers le "haut".
    // / Orthogonal vector (90 deg rotation) to offset control point "upward".
    var offsetLat = -dLng * 0.3;
    var offsetLng = dLat * 0.3;

    var ctrlLat = midLat + offsetLat;
    var ctrlLng = midLng + offsetLng;

    var points = [];
    for (var i = 0; i <= segments; i++) {
        var t = i / segments;
        // Bezier quadratique : B(t) = (1-t)^2 * P0 + 2(1-t)t * P1 + t^2 * P2
        var it = 1 - t;
        var lat = it * it * start.lat + 2 * it * t * ctrlLat + t * t * end.lat;
        var lng = it * it * start.lng + 2 * it * t * ctrlLng + t * t * end.lng;
        points.push([lat, lng]);
    }
    return points;
}

/**
 * Dispatcher selon la nature de l'asset :
 * - Federation primaire (is_federation_primary) : polygone hull (drawHull)
 * - Asset federe partiellement avec origine : arcs (drawArcs) — Task 8
 * - Asset local (1 seul lieu) : pas de ligne
 * / Dispatcher based on asset nature:
 * - Primary federation: hull polygon (drawHull)
 * - Partially federated with origin: arcs (drawArcs) — Task 8
 * - Local asset (1 lieu): no line
 */
function drawAssetLinks(asset) {
    if (!assetLayerGroup) return;
    assetLayerGroup.clearLayers();

    var acceptingIds = asset.accepting_tenant_ids || [];
    if (acceptingIds.length < 2) return;

    // Coordonnees des lieux acceptants via les marqueurs Leaflet deja crees.
    // / Accepting lieux coordinates via existing Leaflet markers.
    var latLngs = [];
    for (var i = 0; i < acceptingIds.length; i++) {
        var marker = markers[acceptingIds[i]];
        if (marker) latLngs.push(marker.getLatLng());
    }
    if (latLngs.length < 2) return;

    if (asset.is_federation_primary) {
        drawHull(latLngs);
    } else if (asset.tenant_origin_id) {
        // drawArcs sera implemente a la Task 8. En attendant, fallback hull.
        // / drawArcs implemented in Task 8. Meanwhile, fallback to hull.
        if (typeof drawArcs === 'function') {
            drawArcs(asset.tenant_origin_id, acceptingIds);
        } else {
            drawHull(latLngs);
        }
    } else {
        drawHull(latLngs);
    }
}
/**
 * Affiche ou masque la legende contextuelle de l'asset actif.
 * Si asset est null, masque la legende.
 * / Shows or hides the active asset's contextual legend.
 * If asset is null, hides the legend.
 */
function renderAssetLegend(asset) {
    var legend = document.getElementById('explorer-asset-legend');
    if (!legend) return;

    if (!asset) {
        legend.hidden = true;
        return;
    }

    var config = ASSET_BADGE_CONFIG[asset.category] || { icon: '\u{1F4B0}', label: asset.category };
    var content = legend.querySelector('.explorer-asset-legend-content');

    var origineStr = asset.tenant_origin_name
        ? '<span class="explorer-asset-legend-origin">Origine : ' + escapeHtml(asset.tenant_origin_name) + '</span>'
        : '';
    var countStr = asset.accepting_count > 1
        ? '<span class="explorer-asset-legend-count">Partagée avec ' + (asset.accepting_count - 1) + ' autre(s) lieu(x)</span>'
        : '<span class="explorer-asset-legend-count">Utilisée localement</span>';

    content.innerHTML = ''
        + '<div class="explorer-asset-legend-title">'
            + '<span class="explorer-asset-legend-icon">' + config.icon + '</span>'
            + '<strong>' + escapeHtml(asset.name) + '</strong>'
        + '</div>'
        + '<div class="explorer-asset-legend-meta">'
            + '<span class="explorer-asset-legend-category">' + escapeHtml(config.label) + '</span>'
            + origineStr
            + countStr
        + '</div>';

    legend.hidden = false;
}

// ============================================================
document.addEventListener('DOMContentLoaded', init);
