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
        var lieuxSurCarte = collectLieuxFromResults(lieux, events, memberships, initiatives);
        updateMapMarkers(lieuxSurCarte);
        updateMapEmptyOverlay(lieuxSurCarte.length, assets.length);
    }
}

/**
 * Affiche un overlay sur la carte quand aucun lieu n'a de marqueur.
 * Explicite le cas "Monnaies" (globales, pas de geolocalisation).
 * / Shows map overlay when no lieu has a marker.
 * Makes the "Assets" case explicit (global, no geolocation).
 */
function updateMapEmptyOverlay(lieuxCount, assetsCount) {
    var mapEl = document.getElementById('explorer-map');
    if (!mapEl) return;

    var existing = mapEl.querySelector('.explorer-map-empty');
    if (lieuxCount > 0) {
        if (existing) existing.remove();
        return;
    }

    // Message different si on filtre uniquement les monnaies (assets globaux)
    // / Different message if filtering only currencies (global assets)
    var isAssetFilter = activeFilters.category === 'asset' && assetsCount > 0;
    var title = isAssetFilter ? 'Les monnaies sont globales' : 'Aucun résultat sur la carte';
    var message = isAssetFilter
        ? 'Les monnaies fédérées sont partagées par tout le réseau, elles n\'ont pas de lieu géolocalisé.'
        : 'Aucun lieu ne correspond à votre recherche. Essayez d\'élargir les filtres.';

    if (!existing) {
        existing = document.createElement('div');
        existing.className = 'explorer-map-empty';
        mapEl.appendChild(existing);
    }
    existing.innerHTML = '<strong>' + title + '</strong>' + message;
}

/**
 * Agrege les lieux visibles sur la carte depuis les resultats filtres.
 * Chaque event/adhesion/initiative ajoute le lieu_id a l'ensemble.
 * / Aggregates lieux visible on map from filtered results.
 * Each event/membership/initiative adds its lieu_id to the set.
 */
function collectLieuxFromResults(lieux, events, memberships, initiatives) {
    var lieuIdsVisibles = {};
    for (var i = 0; i < lieux.length; i++) lieuIdsVisibles[lieux[i].tenant_id] = true;
    for (var j = 0; j < events.length; j++) if (events[j].lieu_id) lieuIdsVisibles[events[j].lieu_id] = true;
    for (var k = 0; k < memberships.length; k++) if (memberships[k].lieu_id) lieuIdsVisibles[memberships[k].lieu_id] = true;
    for (var l = 0; l < initiatives.length; l++) if (initiatives[l].lieu_id) lieuIdsVisibles[initiatives[l].lieu_id] = true;

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
                + '</div>'
            + '</div>'
            + buildAccordion(lieu, domain)
            + '<div class="explorer-card-footer">'
                + '<a href="' + escapeHtml(href) + '" target="_blank" class="explorer-card-link">Visiter le lieu \u2192</a>'
            + '</div>'
        + '</div>';
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
function buildFlatCard(item, categoryName) {
    var cat = CATEGORIES[categoryName];
    var lieuId = escapeHtml(item.lieu_id || '');
    var focusable = categoryName !== 'asset' && lieuId;
    var desc = item.short_description
        ? '<div class="explorer-card-desc">' + escapeHtml(item.short_description) + '</div>'
        : '';

    var clickAttr = focusable
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

function closeAllAccordionsExcept(tenantId) {
    var allCards = document.querySelectorAll('.explorer-card--lieu');
    for (var i = 0; i < allCards.length; i++) {
        var card = allCards[i];
        if (card.getAttribute('data-lieu-id') === tenantId) continue;
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

    var card = button.closest('.explorer-card--lieu');
    if (!card) return;

    var panel = card.querySelector('.explorer-accordion-panel');
    var willOpen = !panel.classList.contains('open');

    // Ferme les autres accordeons avant d'ouvrir celui-ci.
    // / Close other accordions before opening this one.
    if (willOpen) {
        closeAllAccordionsExcept(card.getAttribute('data-lieu-id'));
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
document.addEventListener('DOMContentLoaded', init);
