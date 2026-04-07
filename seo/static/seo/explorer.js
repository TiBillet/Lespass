/**
 * Explorer — carte Leaflet + liste filtree + toggle mobile.
 * / Explorer — Leaflet map + filtered list + mobile toggle.
 *
 * SECTIONS :
 *   1. Etat global / Global state
 *   2. Initialisation / Initialization
 *   3. Filtrage / Filtering
 *   4. Rendu liste / List rendering
 *   5. Carte Leaflet / Leaflet map (Task 6)
 *   6. Cross-highlighting desktop (Task 6)
 *   7. Toggle mobile / Mobile toggle (Task 6)
 *
 * LOCALISATION: seo/static/seo/explorer.js
 */

// ============================================================
// SECTION 1 — Etat global / Global state
// ============================================================

var explorerData = null;
var activeFilters = {
    text: '',
    category: 'all'
};
var map = null;
var markers = {};
var markerClusterGroup = null;
var mapInitialized = false;

// ============================================================
// SECTION 2 — Initialisation / Initialization
// ============================================================

function init() {
    var dataElement = document.getElementById('explorer-data');
    if (!dataElement) {
        console.error('Element #explorer-data introuvable / #explorer-data element not found');
        return;
    }
    explorerData = JSON.parse(dataElement.textContent);

    bindSearch();
    bindPills();
    bindFAB();

    // Premier rendu / First render
    applyFilters();

    // Sur desktop, initialiser la carte immediatement
    // / On desktop, initialize the map immediately
    if (window.innerWidth >= 992) {
        initMap();
    }
}

function bindSearch() {
    var searchInput = document.getElementById('explorer-search');
    if (!searchInput) return;

    var debounceTimer = null;
    searchInput.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function() {
            activeFilters.text = searchInput.value.trim().toLowerCase();
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

// ============================================================
// SECTION 3 — Filtrage / Filtering
// ============================================================

function applyFilters() {
    if (!explorerData) return;

    var filteredLieux = [];
    var filteredEvents = [];
    var filteredMemberships = [];

    if (activeFilters.category === 'all' || activeFilters.category === 'lieu') {
        for (var i = 0; i < explorerData.lieux.length; i++) {
            var lieu = explorerData.lieux[i];
            if (matchesText(lieu)) {
                filteredLieux.push(lieu);
            }
        }
    }

    if (activeFilters.category === 'all' || activeFilters.category === 'event') {
        for (var j = 0; j < explorerData.events.length; j++) {
            var event = explorerData.events[j];
            if (matchesText(event)) {
                filteredEvents.push(event);
            }
        }
    }

    if (activeFilters.category === 'all' || activeFilters.category === 'membership') {
        for (var k = 0; k < explorerData.memberships.length; k++) {
            var membership = explorerData.memberships[k];
            if (matchesText(membership)) {
                filteredMemberships.push(membership);
            }
        }
    }

    renderList(filteredLieux, filteredEvents, filteredMemberships);
    updateCounters(filteredLieux.length, filteredEvents.length, filteredMemberships.length);

    if (mapInitialized) {
        updateMapMarkers(filteredLieux);
    }
}

function matchesText(item) {
    if (!activeFilters.text) return true;

    var query = activeFilters.text;
    var name = (item.name || '').toLowerCase();
    var locality = (item.locality || '').toLowerCase();
    var description = (item.short_description || '').toLowerCase();
    var lieuName = (item.lieu_name || '').toLowerCase();

    return name.indexOf(query) !== -1
        || locality.indexOf(query) !== -1
        || description.indexOf(query) !== -1
        || lieuName.indexOf(query) !== -1;
}

function updateCounters(lieuxCount, eventsCount, membershipsCount) {
    var counter = document.getElementById('explorer-counter');
    if (!counter) return;

    var parts = [];
    parts.push(lieuxCount + ' lieu' + (lieuxCount > 1 ? 'x' : ''));
    parts.push(eventsCount + ' événement' + (eventsCount > 1 ? 's' : ''));
    parts.push(membershipsCount + ' adhésion' + (membershipsCount > 1 ? 's' : ''));
    counter.textContent = parts.join(' · ');
}

// ============================================================
// SECTION 4 — Rendu liste / List rendering
// ============================================================

function renderList(lieux, events, memberships) {
    var listContainer = document.getElementById('explorer-list');
    if (!listContainer) return;

    var html = '';

    for (var i = 0; i < lieux.length; i++) {
        html += buildLieuCard(lieux[i]);
    }
    for (var j = 0; j < events.length; j++) {
        html += buildEventCard(events[j]);
    }
    for (var k = 0; k < memberships.length; k++) {
        html += buildMembershipCard(memberships[k]);
    }

    if (!html) {
        html = '<p class="text-muted text-center py-4">Aucun résultat trouvé.</p>';
    }

    listContainer.innerHTML = html;

    if (window.innerWidth >= 992) {
        bindCardHoverEvents();
    }
}

function buildLieuCard(lieu) {
    var domain = lieu.domain || '';
    var href = domain ? 'https://' + domain + '/' : '#';
    var logoHtml = '';
    if (lieu.logo_url) {
        logoHtml = '<img src="' + escapeHtml(lieu.logo_url) + '" alt="" class="explorer-card-icon lieu" style="object-fit:contain;padding:4px;">';
    } else {
        logoHtml = '<div class="explorer-card-icon lieu">&#127963;</div>';
    }

    return '<a class="explorer-card" href="' + escapeHtml(href) + '" target="_blank"'
        + ' data-lieu-id="' + escapeHtml(lieu.tenant_id) + '"'
        + ' data-type="lieu">'
        + logoHtml
        + '<div class="explorer-card-body">'
        + '<div class="explorer-card-header">'
        + '<h3 class="explorer-card-title">' + escapeHtml(lieu.name) + '</h3>'
        + '<span class="explorer-badge lieu">Lieu</span>'
        + '</div>'
        + (lieu.locality ? '<div class="explorer-card-meta">&#128205; ' + escapeHtml(lieu.locality)
            + (lieu.country ? ', ' + escapeHtml(lieu.country) : '') + '</div>' : '')
        + (lieu.short_description ? '<div class="explorer-card-desc">' + escapeHtml(lieu.short_description) + '</div>' : '')
        + '<div class="explorer-card-stats">'
        + (lieu.events ? lieu.events.length : 0) + ' événement' + ((lieu.events && lieu.events.length > 1) ? 's' : '')
        + ' · '
        + (lieu.memberships ? lieu.memberships.length : 0) + ' adhésion' + ((lieu.memberships && lieu.memberships.length > 1) ? 's' : '')
        + '</div>'
        + '</div>'
        + '</a>';
}

function buildEventCard(event) {
    var domain = event.lieu_domain || '';
    var slug = event.slug || '';
    var href = domain && slug ? 'https://' + domain + '/event/' + slug + '/' : '#';
    var dateStr = '';
    if (event.datetime) {
        var d = new Date(event.datetime);
        dateStr = d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
    }

    return '<a class="explorer-card" href="' + escapeHtml(href) + '" target="_blank"'
        + ' data-lieu-id="' + escapeHtml(event.lieu_id || '') + '"'
        + ' data-type="event">'
        + '<div class="explorer-card-icon event">&#127926;</div>'
        + '<div class="explorer-card-body">'
        + '<div class="explorer-card-header">'
        + '<h3 class="explorer-card-title">' + escapeHtml(event.name) + '</h3>'
        + '<span class="explorer-badge event">Événement</span>'
        + '</div>'
        + '<div class="explorer-card-meta">'
        + (dateStr ? '&#128197; ' + dateStr + ' · ' : '')
        + escapeHtml(event.lieu_name || '')
        + '</div>'
        + (event.short_description ? '<div class="explorer-card-desc">' + escapeHtml(event.short_description) + '</div>' : '')
        + '</div>'
        + '</a>';
}

function buildMembershipCard(membership) {
    var domain = membership.lieu_domain || '';
    var href = domain ? 'https://' + domain + '/' : '#';

    return '<a class="explorer-card" href="' + escapeHtml(href) + '" target="_blank"'
        + ' data-lieu-id="' + escapeHtml(membership.lieu_id || '') + '"'
        + ' data-type="membership">'
        + '<div class="explorer-card-icon membership">&#129309;</div>'
        + '<div class="explorer-card-body">'
        + '<div class="explorer-card-header">'
        + '<h3 class="explorer-card-title">' + escapeHtml(membership.name) + '</h3>'
        + '<span class="explorer-badge membership">Adhésion</span>'
        + '</div>'
        + '<div class="explorer-card-meta">&#127963; ' + escapeHtml(membership.lieu_name || '') + '</div>'
        + (membership.short_description ? '<div class="explorer-card-desc">' + escapeHtml(membership.short_description) + '</div>' : '')
        + '</div>'
        + '</a>';
}

function escapeHtml(text) {
    if (!text) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

// ============================================================
// SECTION 5 — Carte Leaflet / Leaflet map
// ============================================================

function initMap() {
    if (mapInitialized) return;

    var mapContainer = document.getElementById('explorer-map');
    if (!mapContainer) return;

    map = L.map('explorer-map', {
        zoomControl: true,
        scrollWheelZoom: true,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19,
    }).addTo(map);

    markerClusterGroup = L.markerClusterGroup();
    map.addLayer(markerClusterGroup);

    addMarkers(explorerData.lieux);

    mapInitialized = true;
}

function addMarkers(lieux) {
    if (!map || !markerClusterGroup) return;

    markerClusterGroup.clearLayers();
    markers = {};

    var bounds = [];

    for (var i = 0; i < lieux.length; i++) {
        var lieu = lieux[i];
        if (lieu.latitude === null || lieu.longitude === null) continue;

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

        var popupContent = buildPopupContent(lieu);
        marker.bindPopup(popupContent, { maxWidth: 280 });

        markers[lieu.tenant_id] = marker;

        (function(tenantId) {
            marker.on('click', function() {
                onMarkerClick(tenantId);
            });
        })(lieu.tenant_id);

        markerClusterGroup.addLayer(marker);
        bounds.push([lat, lng]);
    }

    if (bounds.length > 0) {
        map.fitBounds(bounds, { padding: [20, 20] });
    } else {
        map.setView([46.603354, 1.888334], 6);
    }
}

function buildPopupContent(lieu) {
    var domain = lieu.domain || '';
    var href = domain ? 'https://' + domain + '/' : '#';

    var html = '<div class="explorer-popup">';
    html += '<h4 class="explorer-popup-title">' + escapeHtml(lieu.name) + '</h4>';

    if (lieu.short_description) {
        html += '<p class="explorer-popup-desc">' + escapeHtml(lieu.short_description) + '</p>';
    }

    if (lieu.locality) {
        html += '<p class="explorer-popup-stats">&#128205; ' + escapeHtml(lieu.locality);
        if (lieu.country) html += ', ' + escapeHtml(lieu.country);
        html += '</p>';
    }

    var events = lieu.events || [];
    if (events.length > 0) {
        html += '<div class="explorer-popup-events">';
        html += '<strong>Prochains événements :</strong><ul style="margin:4px 0;padding-left:16px;">';
        var maxEvents = Math.min(events.length, 3);
        for (var i = 0; i < maxEvents; i++) {
            var ev = events[i];
            var dateStr = '';
            if (ev.datetime) {
                var d = new Date(ev.datetime);
                dateStr = d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
            }
            html += '<li>' + escapeHtml(ev.name);
            if (dateStr) html += ' — ' + dateStr;
            html += '</li>';
        }
        html += '</ul>';
        if (events.length > 3) {
            html += '<span style="font-size:11px;color:#999;">+ ' + (events.length - 3) + ' autre(s)</span>';
        }
        html += '</div>';
    }

    var memberships = lieu.memberships || [];
    if (memberships.length > 0) {
        html += '<div class="explorer-popup-events">';
        html += '<strong>Adhésions :</strong><ul style="margin:4px 0;padding-left:16px;">';
        var maxMemberships = Math.min(memberships.length, 2);
        for (var j = 0; j < maxMemberships; j++) {
            html += '<li>' + escapeHtml(memberships[j].name) + '</li>';
        }
        html += '</ul>';
        if (memberships.length > 2) {
            html += '<span style="font-size:11px;color:#999;">+ ' + (memberships.length - 2) + ' autre(s)</span>';
        }
        html += '</div>';
    }

    html += '<a class="explorer-popup-link" href="' + escapeHtml(href) + '" target="_blank">Visiter le lieu &rarr;</a>';
    html += '</div>';

    return html;
}

function updateMapMarkers(filteredLieux) {
    if (!mapInitialized) return;

    var filteredIds = {};
    for (var i = 0; i < filteredLieux.length; i++) {
        filteredIds[filteredLieux[i].tenant_id] = true;
    }

    for (var tenantId in markers) {
        var marker = markers[tenantId];
        if (filteredIds[tenantId]) {
            if (!markerClusterGroup.hasLayer(marker)) {
                markerClusterGroup.addLayer(marker);
            }
        } else {
            if (markerClusterGroup.hasLayer(marker)) {
                markerClusterGroup.removeLayer(marker);
            }
        }
    }
}

// ============================================================
// SECTION 6 — Cross-highlighting desktop
// ============================================================

function bindCardHoverEvents() {
    var cards = document.querySelectorAll('.explorer-card[data-lieu-id]');
    cards.forEach(function(card) {
        var lieuId = card.getAttribute('data-lieu-id');
        if (!lieuId) return;

        card.addEventListener('mouseenter', function() {
            onCardHover(lieuId);
        });
        card.addEventListener('mouseleave', function() {
            onCardLeave(lieuId);
        });
    });
}

function onCardHover(lieuId) {
    var pinEl = document.querySelector('.explorer-pin[data-lieu-id="' + lieuId + '"]');
    if (pinEl) {
        pinEl.classList.add('selected');
    }
}

function onCardLeave(lieuId) {
    var pinEl = document.querySelector('.explorer-pin[data-lieu-id="' + lieuId + '"]');
    if (pinEl) {
        pinEl.classList.remove('selected');
    }
}

function onMarkerClick(lieuId) {
    scrollToCard(lieuId);
}

function scrollToCard(lieuId) {
    var card = document.querySelector('.explorer-card[data-lieu-id="' + lieuId + '"][data-type="lieu"]');
    if (!card) return;

    card.scrollIntoView({ behavior: 'smooth', block: 'center' });

    card.setAttribute('data-highlighted', 'true');
    setTimeout(function() {
        card.removeAttribute('data-highlighted');
    }, 2000);
}

// ============================================================
// SECTION 7 — Toggle mobile / Mobile toggle
// ============================================================

var currentView = 'list';

function bindFAB() {
    var fab = document.getElementById('explorer-fab');
    if (!fab) return;

    fab.addEventListener('click', function() {
        toggleView();
    });
}

function toggleView() {
    var container = document.querySelector('.explorer-container');
    var fab = document.getElementById('explorer-fab');
    if (!container || !fab) return;

    if (currentView === 'list') {
        container.classList.add('explorer-view-map');
        fab.innerHTML = '&#9776; Liste';
        currentView = 'map';

        if (!mapInitialized) {
            initMap();
        } else {
            map.invalidateSize();
        }
    } else {
        container.classList.remove('explorer-view-map');
        fab.innerHTML = '&#128506; Carte';
        currentView = 'list';
    }
}

// ============================================================
// Point d'entree / Entry point
// ============================================================

document.addEventListener('DOMContentLoaded', init);
