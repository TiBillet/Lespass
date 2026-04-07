# Explorer Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create an interactive `/explorer/` page on the ROOT site with a Leaflet map + synchronized filtered list of venues, events and memberships.

**Architecture:** The explorer reads from the existing SEOCache (public schema). A new helper `build_explorer_data()` nests events/memberships under their parent venue. Data is injected as inline JSON via `json_script`. A single vanilla JS file handles map, list, filtering, cross-highlighting (desktop) and toggle (mobile).

**Tech Stack:** Django template, Leaflet 1.9 + OSM tiles (CDN), leaflet.markercluster (CDN), vanilla JS, Bootstrap 5 CSS.

**Spec:** `TECH DOC/SESSIONS/ROOT_VIEW/2026-04-07-explorer-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `seo/services.py` | Modify | Add latitude/longitude to `build_tenant_config_data()`, add `build_explorer_data()` |
| `seo/tasks.py` | Modify | Add latitude/longitude to `aggregate_lieux` dict |
| `seo/views.py` | Modify | Add `explorer()` view |
| `seo/urls.py` | Modify | Add `/explorer/` route |
| `seo/templates/seo/explorer.html` | Create | Full-width template with search bar, split view, FAB, json_script |
| `seo/templates/seo/base.html` | Modify | Add "Explorer" link in navbar |
| `seo/static/seo/explorer.css` | Create | Layout split/mobile, cards, pins, FAB |
| `seo/static/seo/explorer.js` | Create | Map + list + filters + toggle + cross-highlighting |
| `tests/pytest/test_explorer.py` | Create | Tests for view, services, data structure |

---

## Task 1: Enrich SEOCache with GPS coordinates

**Files:**
- Modify: `seo/services.py:248-334` (`build_tenant_config_data()`)
- Modify: `seo/tasks.py:181-197` (aggregate_lieux dict)
- Test: `tests/pytest/test_explorer.py`

- [ ] **Step 1: Write failing test for GPS in build_tenant_config_data**

Create `tests/pytest/test_explorer.py`:

```python
import pytest
from django.test import Client as DjangoTestClient
from Customers.models import Client


@pytest.mark.django_db
class TestExplorerServices:
    """Tests pour les services explorer / Tests for explorer services"""

    def test_build_tenant_config_data_includes_gps(self):
        """build_tenant_config_data retourne latitude/longitude
        / build_tenant_config_data returns latitude/longitude"""
        from seo.services import build_tenant_config_data

        # Utiliser un tenant actif existant (pas ROOT)
        # / Use an existing active tenant (not ROOT)
        client = Client.objects.exclude(
            categorie__in=[Client.ROOT, Client.WAITING_CONFIG]
        ).first()
        if client is None:
            pytest.skip("Aucun tenant actif disponible / No active tenant available")

        data = build_tenant_config_data(client)

        # Les champs latitude et longitude doivent etre presents dans le dict
        # (meme si None quand le lieu n'a pas de coordonnees)
        # / latitude and longitude keys must be in the dict
        # (even if None when the venue has no coords)
        assert "latitude" in data
        assert "longitude" in data
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_explorer.py::TestExplorerServices::test_build_tenant_config_data_includes_gps -v
```

Expected: FAIL with `AssertionError: assert 'latitude' in data`

- [ ] **Step 3: Add latitude/longitude to build_tenant_config_data**

In `seo/services.py`, in the `build_tenant_config_data()` function, add two fields to the initial `data` dict (after `"country": None,`):

```python
        "latitude": None,
        "longitude": None,
```

Then in the `if config.postal_address:` block (after the `data["country"]` line), add:

```python
                # Coordonnees GPS / GPS coordinates
                data["latitude"] = (
                    float(config.postal_address.latitude)
                    if config.postal_address.latitude
                    else None
                )
                data["longitude"] = (
                    float(config.postal_address.longitude)
                    if config.postal_address.longitude
                    else None
                )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_explorer.py::TestExplorerServices::test_build_tenant_config_data_includes_gps -v
```

Expected: PASS

- [ ] **Step 5: Add latitude/longitude to aggregate_lieux in tasks.py**

In `seo/tasks.py`, in the `aggregate_lieux` loop (around line 186), add two fields to the `lieux.append({...})` dict, after `"categorie"`:

```python
                    "latitude": config.get("latitude"),
                    "longitude": config.get("longitude"),
```

- [ ] **Step 6: Write test for GPS propagation in aggregate_lieux**

Add to `tests/pytest/test_explorer.py`:

```python
    def test_aggregate_lieux_contains_gps_fields(self):
        """L'agregat lieux contient latitude/longitude apres refresh
        / aggregate_lieux contains latitude/longitude after refresh"""
        from seo.tasks import refresh_seo_cache
        from seo.views_common import get_seo_cache
        from seo.models import SEOCache

        refresh_seo_cache()
        lieux_data = get_seo_cache(SEOCache.AGGREGATE_LIEUX)
        assert lieux_data is not None

        lieux = lieux_data.get("lieux", [])
        if len(lieux) == 0:
            pytest.skip("Aucun lieu dans le cache / No venue in cache")

        # Chaque lieu doit avoir les cles latitude et longitude
        # / Each venue must have latitude and longitude keys
        for lieu in lieux:
            assert "latitude" in lieu, f"Lieu {lieu.get('name')} manque latitude"
            assert "longitude" in lieu, f"Lieu {lieu.get('name')} manque longitude"
```

- [ ] **Step 7: Run all explorer tests**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_explorer.py -v
```

Expected: 2 tests PASS

---

## Task 2: Create build_explorer_data() helper

**Files:**
- Modify: `seo/services.py` (add function at the end)
- Test: `tests/pytest/test_explorer.py`

- [ ] **Step 1: Write failing tests for build_explorer_data**

Add to `tests/pytest/test_explorer.py`, in class `TestExplorerServices`:

```python
    def test_build_explorer_data_returns_three_keys(self):
        """build_explorer_data retourne lieux, events, memberships
        / build_explorer_data returns lieux, events, memberships"""
        from seo.tasks import refresh_seo_cache
        from seo.services import build_explorer_data

        refresh_seo_cache()
        data = build_explorer_data()

        assert "lieux" in data
        assert "events" in data
        assert "memberships" in data
        assert isinstance(data["lieux"], list)
        assert isinstance(data["events"], list)
        assert isinstance(data["memberships"], list)

    def test_build_explorer_data_excludes_lieux_without_coords(self):
        """Les lieux sans coordonnees GPS sont exclus
        / Venues without GPS coordinates are excluded"""
        from seo.tasks import refresh_seo_cache
        from seo.services import build_explorer_data

        refresh_seo_cache()
        data = build_explorer_data()

        for lieu in data["lieux"]:
            assert lieu["latitude"] is not None, (
                f"Lieu {lieu['name']} sans latitude inclus"
            )
            assert lieu["longitude"] is not None, (
                f"Lieu {lieu['name']} sans longitude inclus"
            )

    def test_build_explorer_data_nests_events_under_lieux(self):
        """Les events sont nestes sous leur lieu parent
        / Events are nested under their parent venue"""
        from seo.tasks import refresh_seo_cache
        from seo.services import build_explorer_data

        refresh_seo_cache()
        data = build_explorer_data()

        for lieu in data["lieux"]:
            assert "events" in lieu, f"Lieu {lieu['name']} manque la cle events"
            assert "memberships" in lieu, f"Lieu {lieu['name']} manque la cle memberships"
            assert isinstance(lieu["events"], list)
            assert isinstance(lieu["memberships"], list)

    def test_build_explorer_data_events_have_lieu_id(self):
        """Chaque event dans la liste plate a un lieu_id
        / Each event in the flat list has a lieu_id"""
        from seo.tasks import refresh_seo_cache
        from seo.services import build_explorer_data

        refresh_seo_cache()
        data = build_explorer_data()

        for event in data["events"]:
            assert "lieu_id" in event, f"Event {event.get('name')} manque lieu_id"
            assert "lieu_name" in event, f"Event {event.get('name')} manque lieu_name"
            assert "lieu_domain" in event, f"Event {event.get('name')} manque lieu_domain"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_explorer.py -v -k "build_explorer_data"
```

Expected: FAIL with `ImportError: cannot import name 'build_explorer_data'`

- [ ] **Step 3: Implement build_explorer_data**

Add at the end of `seo/services.py`:

```python
def build_explorer_data():
    """
    Construit les donnees pour la page Explorer.
    Neste les events et memberships sous leur lieu parent.
    Exclut les lieux sans coordonnees GPS.
    / Build data for the Explorer page.
    Nest events and memberships under their parent venue.
    Exclude venues without GPS coordinates.

    Entree : lit les 3 agregats du SEOCache (lieux, events, memberships).
    Sortie : dict avec 3 cles (lieux, events, memberships).
    / Input: reads 3 aggregates from SEOCache (venues, events, memberships).
    Output: dict with 3 keys (lieux, events, memberships).
    """
    from seo.models import SEOCache
    from seo.views_common import get_seo_cache

    lieux_data = get_seo_cache(SEOCache.AGGREGATE_LIEUX) or {}
    events_data = get_seo_cache(SEOCache.AGGREGATE_EVENTS) or {}
    memberships_data = get_seo_cache(SEOCache.AGGREGATE_MEMBERSHIPS) or {}

    all_lieux = lieux_data.get("lieux", [])
    all_events = events_data.get("events", [])
    all_memberships = memberships_data.get("memberships", [])

    # Index des lieux par tenant_id pour le rattachement des events/memberships
    # / Index venues by tenant_id for linking events/memberships
    lieux_by_tenant = {}
    for lieu in all_lieux:
        # Exclure les lieux sans coordonnees GPS
        # / Exclude venues without GPS coordinates
        if lieu.get("latitude") is None or lieu.get("longitude") is None:
            continue
        lieu_copy = dict(lieu)
        lieu_copy["events"] = []
        lieu_copy["memberships"] = []
        lieux_by_tenant[lieu["tenant_id"]] = lieu_copy

    # Rattacher les events a leur lieu parent / Link events to their parent venue
    flat_events = []
    for event in all_events:
        tenant_id = event["tenant_id"]
        lieu = lieux_by_tenant.get(tenant_id)
        if lieu is not None:
            lieu["events"].append(event)
        # Liste plate : ajouter le lieu_id, lieu_name, lieu_domain pour le JS
        # / Flat list: add lieu_id, lieu_name, lieu_domain for JS
        event_with_lieu = dict(event)
        if lieu is not None:
            event_with_lieu["lieu_id"] = tenant_id
            event_with_lieu["lieu_name"] = lieu.get("name", "")
            event_with_lieu["lieu_domain"] = lieu.get("domain", "")
        else:
            event_with_lieu["lieu_id"] = tenant_id
            event_with_lieu["lieu_name"] = ""
            event_with_lieu["lieu_domain"] = ""
        flat_events.append(event_with_lieu)

    # Rattacher les memberships a leur lieu parent / Link memberships to their parent venue
    flat_memberships = []
    for membership in all_memberships:
        tenant_id = membership["tenant_id"]
        lieu = lieux_by_tenant.get(tenant_id)
        if lieu is not None:
            lieu["memberships"].append(membership)
        membership_with_lieu = dict(membership)
        if lieu is not None:
            membership_with_lieu["lieu_id"] = tenant_id
            membership_with_lieu["lieu_name"] = lieu.get("name", "")
            membership_with_lieu["lieu_domain"] = lieu.get("domain", "")
        else:
            membership_with_lieu["lieu_id"] = tenant_id
            membership_with_lieu["lieu_name"] = ""
            membership_with_lieu["lieu_domain"] = ""
        flat_memberships.append(membership_with_lieu)

    # Liste finale des lieux (seulement ceux avec GPS)
    # / Final venue list (only those with GPS)
    lieux_list = list(lieux_by_tenant.values())

    return {
        "lieux": lieux_list,
        "events": flat_events,
        "memberships": flat_memberships,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_explorer.py -v
```

Expected: 6 tests PASS

---

## Task 3: Create explorer view and route

**Files:**
- Modify: `seo/views.py` (add `explorer()` view)
- Modify: `seo/urls.py` (add route)
- Modify: `seo/templates/seo/base.html` (add nav link)
- Test: `tests/pytest/test_explorer.py`

- [ ] **Step 1: Write failing test for the explorer view**

Add to `tests/pytest/test_explorer.py`:

```python
@pytest.mark.django_db
class TestExplorerView:
    """Tests pour la vue explorer / Tests for the explorer view"""

    @pytest.fixture(autouse=True)
    def _setup_cache_and_client(self):
        """
        Remplit le cache SEO et cree un client HTTP ROOT.
        / Populate SEO cache and create a ROOT HTTP client.
        """
        from seo.tasks import refresh_seo_cache

        refresh_seo_cache()
        self.root_client = DjangoTestClient(HTTP_HOST="www.tibillet.localhost")

    def test_explorer_view_returns_200(self):
        """La vue explorer retourne 200 / Explorer view returns 200"""
        response = self.root_client.get("/explorer/")
        assert response.status_code == 200

    def test_explorer_template_contains_json_script(self):
        """Le template contient le tag json_script avec les donnees
        / Template contains the json_script tag with data"""
        response = self.root_client.get("/explorer/")
        content = response.content.decode()
        assert 'id="explorer-data"' in content
        assert 'type="application/json"' in content

    def test_explorer_template_contains_leaflet(self):
        """Le template charge Leaflet via CDN / Template loads Leaflet via CDN"""
        response = self.root_client.get("/explorer/")
        content = response.content.decode()
        assert "leaflet" in content.lower()

    def test_explorer_template_contains_search_bar(self):
        """Le template contient la barre de recherche / Template contains search bar"""
        response = self.root_client.get("/explorer/")
        content = response.content.decode()
        assert "explorer-search" in content
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_explorer.py::TestExplorerView -v
```

Expected: FAIL (404 — route does not exist yet)

- [ ] **Step 3: Add the explorer view to seo/views.py**

Add at the end of `seo/views.py` (before the `sitemap_index_view` function):

```python
def explorer(request):
    """
    Page Explorer : carte Leaflet + liste filtree de lieux/events/adhesions.
    Outil de decouverte interactif (pas SEO crawlable).
    / Explorer page: Leaflet map + filtered list of venues/events/memberships.
    Interactive discovery tool (not SEO crawlable).

    URL: GET /explorer/
    """
    from seo.services import build_explorer_data

    explorer_data = build_explorer_data()

    context = {
        "explorer_data": explorer_data,
        "page_title": "Explorer - TiBillet",
        "page_description": "Explorez les lieux, evenements et adhesions du reseau TiBillet sur une carte interactive.",
    }

    return TemplateResponse(request, "seo/explorer.html", context)
```

- [ ] **Step 4: Add the route to seo/urls.py**

In `seo/urls.py`, add to `urlpatterns` (after the `recherche` route):

```python
    path("explorer/", views.explorer, name="explorer"),
```

- [ ] **Step 5: Add "Explorer" link in the navbar**

In `seo/templates/seo/base.html`, add a nav item after the "Adhésions" link (around line 91):

```html
                <li class="nav-item">
                    <a class="nav-link" href="/explorer/">
                        <i class="bi bi-map"></i> {% translate "Explorer" %}
                    </a>
                </li>
```

- [ ] **Step 6: Create the explorer.html template (minimal)**

Create `seo/templates/seo/explorer.html`:

```html
{% extends "seo/base.html" %}
{% load static i18n %}

{% block extra_head %}
{# Leaflet CSS (CDN) / Leaflet CSS (CDN) #}
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9/dist/leaflet.css" />
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5/dist/MarkerCluster.css" />
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5/dist/MarkerCluster.Default.css" />
<link rel="stylesheet" href="{% static 'seo/explorer.css' %}" />
{% endblock %}

{% block content %}

{# Barre de recherche + pills / Search bar + category pills #}
<div class="explorer-toolbar">
    <div class="explorer-search-row">
        <input type="search" class="explorer-search" id="explorer-search"
               placeholder="{% translate 'Rechercher un lieu, événement, adhésion...' %}"
               aria-label="{% translate 'Rechercher' %}">
        <div class="explorer-pills" id="explorer-pills">
            <button class="explorer-pill active" data-category="all">{% translate "Tous" %}</button>
            <button class="explorer-pill" data-category="lieu">{% translate "Lieux" %}</button>
            <button class="explorer-pill" data-category="event">{% translate "Événements" %}</button>
            <button class="explorer-pill" data-category="membership">{% translate "Adhésions" %}</button>
        </div>
    </div>
    <div class="explorer-counter" id="explorer-counter"></div>
</div>

{# Split view : liste + carte / Split view: list + map #}
<div class="explorer-container">
    {# Liste des resultats / Results list #}
    <div class="explorer-list" id="explorer-list"></div>

    {# Carte Leaflet / Leaflet map #}
    <div class="explorer-map" id="explorer-map"></div>
</div>

{# Bouton toggle mobile / Mobile toggle FAB #}
<button class="explorer-fab" id="explorer-fab" aria-label="{% translate 'Basculer carte/liste' %}">
    &#128506; {% translate "Carte" %}
</button>

{# Donnees JSON pour le JS / JSON data for JS #}
{{ explorer_data|json_script:"explorer-data" }}

{% endblock %}

{% block extra_js %}
<script src="https://unpkg.com/leaflet@1.9/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5/dist/leaflet.markercluster.js"></script>
<script src="{% static 'seo/explorer.js' %}"></script>
{% endblock %}
```

- [ ] **Step 7: Create a minimal explorer.css (enough for tests to pass)**

Create `seo/static/seo/explorer.css`:

```css
/*
 * Styles pour la page Explorer (carte Leaflet + liste).
 * / Styles for the Explorer page (Leaflet map + list).
 *
 * LOCALISATION: seo/static/seo/explorer.css
 */

/* Placeholder — sera complete dans Task 4 */
.explorer-container { display: flex; }
.explorer-list { width: 55%; }
.explorer-map { width: 45%; min-height: 400px; }
```

- [ ] **Step 8: Create a minimal explorer.js (enough for tests to pass)**

Create `seo/static/seo/explorer.js`:

```js
/**
 * Explorer — carte Leaflet + liste filtree + toggle mobile.
 * / Explorer — Leaflet map + filtered list + mobile toggle.
 *
 * LOCALISATION: seo/static/seo/explorer.js
 */

// Point d'entree / Entry point
document.addEventListener('DOMContentLoaded', function() {
    // Placeholder — sera complete dans les tasks suivantes
    console.log('Explorer initialise / Explorer initialized');
});
```

- [ ] **Step 9: Run tests to verify they pass**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_explorer.py -v
```

Expected: all 10 tests PASS

- [ ] **Step 10: Run existing SEO tests to check for regressions**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_seo.py -v
```

Expected: all existing tests still PASS

---

## Task 4: Build the full CSS

**Files:**
- Modify: `seo/static/seo/explorer.css` (replace placeholder content)

- [ ] **Step 1: Write the complete explorer.css**

Replace the content of `seo/static/seo/explorer.css` with:

```css
/*
 * Styles pour la page Explorer (carte Leaflet + liste).
 * / Styles for the Explorer page (Leaflet map + list).
 *
 * LOCALISATION: seo/static/seo/explorer.css
 */

/* --- Forcer le theme clair / Force light theme --- */
.explorer-toolbar,
.explorer-container,
.explorer-fab {
    color-scheme: light;
    --bs-body-bg: #fff;
    --bs-body-color: #222;
}

/* --- Toolbar (search + pills + counter) --- */
.explorer-toolbar {
    background: #fff;
    border-bottom: 1px solid #eee;
    padding: 12px 24px;
}

.explorer-search-row {
    display: flex;
    align-items: center;
    gap: 12px;
}

.explorer-search {
    flex: 1;
    background: #f5f5f5;
    border: 1px solid #ddd;
    border-radius: 999px;
    padding: 10px 16px;
    font-size: 14px;
    outline: none;
}

.explorer-search:focus {
    border-color: #222;
    box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.1);
}

.explorer-pills {
    display: flex;
    gap: 8px;
    flex-shrink: 0;
}

.explorer-pill {
    background: #fff;
    border: 1px solid #ccc;
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 400;
    cursor: pointer;
    white-space: nowrap;
    transition: background 150ms ease, color 150ms ease;
}

.explorer-pill:hover {
    background: #f5f5f5;
}

.explorer-pill.active {
    background: #222;
    color: #fff;
    border-color: #222;
    font-weight: 600;
}

.explorer-counter {
    font-size: 13px;
    color: #666;
    margin-top: 8px;
}

/* --- Split view desktop (>= 992px) --- */
.explorer-container {
    display: flex;
    height: calc(100vh - 160px);
}

.explorer-list {
    width: 55%;
    overflow-y: auto;
    padding: 16px 24px;
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.explorer-map {
    width: 45%;
    position: sticky;
    top: 0;
    height: calc(100vh - 160px);
    border-left: 1px solid #eee;
}

/* --- Cards --- */
.explorer-card {
    background: #fff;
    border-radius: 12px;
    padding: 16px;
    display: flex;
    gap: 16px;
    cursor: pointer;
    border: 2px solid transparent;
    transition: border-color 200ms ease, box-shadow 200ms ease;
    box-shadow:
        0px 0px 0px 1px rgba(0, 0, 0, 0.06),
        0px 1px 2px -1px rgba(0, 0, 0, 0.06),
        0px 2px 4px 0px rgba(0, 0, 0, 0.04);
    text-decoration: none;
    color: inherit;
}

.explorer-card:hover {
    box-shadow:
        0px 0px 0px 1px rgba(0, 0, 0, 0.08),
        0px 2px 6px -1px rgba(0, 0, 0, 0.10),
        0px 4px 8px 0px rgba(0, 0, 0, 0.06);
}

.explorer-card[data-highlighted="true"] {
    border-color: #222;
}

.explorer-card-icon {
    width: 80px;
    height: 80px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    flex-shrink: 0;
    object-fit: contain;
}

.explorer-card-icon.lieu { background: #e9ecef; color: #666; }
.explorer-card-icon.event { background: #fff3e0; color: #e65100; }
.explorer-card-icon.membership { background: #e3f2fd; color: #1565c0; }

.explorer-card-body {
    flex: 1;
    min-width: 0;
}

.explorer-card-header {
    display: flex;
    justify-content: space-between;
    align-items: start;
}

.explorer-card-title {
    font-weight: 600;
    font-size: 15px;
    margin: 0;
}

.explorer-badge {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 999px;
    white-space: nowrap;
}

.explorer-badge.lieu { background: #e8f5e9; color: #2e7d32; }
.explorer-badge.event { background: #fff3e0; color: #e65100; }
.explorer-badge.membership { background: #e3f2fd; color: #1565c0; }

.explorer-card-meta {
    font-size: 13px;
    color: #666;
    margin-top: 2px;
}

.explorer-card-desc {
    font-size: 13px;
    color: #888;
    margin-top: 4px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.explorer-card-stats {
    font-size: 12px;
    color: #999;
    margin-top: 6px;
}

/* --- Map pins (Leaflet DivIcon) --- */
.explorer-pin {
    background: #fff;
    color: #222;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
    white-space: nowrap;
    text-align: center;
    transition: background 150ms ease, color 150ms ease, transform 150ms ease;
}

.explorer-pin.selected {
    background: #222;
    color: #fff;
    transform: scale(1.08);
}

/* --- Leaflet popup overrides --- */
.leaflet-popup-content-wrapper {
    border-radius: 12px !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
}

.explorer-popup-title {
    font-weight: 600;
    font-size: 14px;
    margin: 0;
}

.explorer-popup-desc {
    font-size: 12px;
    color: #666;
    margin-top: 4px;
}

.explorer-popup-stats {
    font-size: 11px;
    color: #999;
    margin-top: 6px;
}

.explorer-popup-events {
    font-size: 12px;
    margin-top: 8px;
}

.explorer-popup-events li {
    margin-bottom: 2px;
}

.explorer-popup-link {
    display: inline-block;
    margin-top: 8px;
    font-size: 12px;
    font-weight: 600;
    color: #0d6efd;
    text-decoration: none;
}

.explorer-popup-link:hover {
    text-decoration: underline;
}

/* --- FAB toggle mobile --- */
.explorer-fab {
    display: none;
    position: fixed;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: #222;
    color: #fff;
    border: none;
    border-radius: 999px;
    padding: 12px 24px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    z-index: 1000;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    white-space: nowrap;
}

/* --- Mobile (< 992px) --- */
@media (max-width: 991.98px) {
    .explorer-search-row {
        flex-direction: column;
        gap: 8px;
    }

    .explorer-pills {
        overflow-x: auto;
        padding-bottom: 4px;
    }

    .explorer-container {
        display: block;
        height: auto;
    }

    .explorer-list {
        width: 100%;
        height: auto;
        padding: 12px 16px 80px;
    }

    .explorer-map {
        width: 100%;
        height: calc(100vh - 120px);
        position: relative;
        border-left: none;
        display: none;
    }

    .explorer-card-icon {
        width: 64px;
        height: 64px;
        font-size: 20px;
    }

    .explorer-card {
        padding: 12px;
        gap: 12px;
    }

    .explorer-card-title {
        font-size: 14px;
    }

    .explorer-fab {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* En vue carte : masquer la liste, montrer la carte */
    /* / In map view: hide list, show map */
    .explorer-view-map .explorer-list {
        display: none;
    }

    .explorer-view-map .explorer-map {
        display: block;
    }

    /* Masquer les pills en vue carte / Hide pills in map view */
    .explorer-view-map .explorer-pills {
        display: none;
    }
}
```

- [ ] **Step 2: Verify CSS is valid (no syntax errors)**

Open `http://tibillet.localhost:8002/explorer/` in a browser and check that the page loads without CSS errors in the console. (Manual check — no automated test needed for CSS.)

---

## Task 5: Build explorer.js — State, Init, Filtering, List Rendering

**Files:**
- Modify: `seo/static/seo/explorer.js` (replace placeholder)

- [ ] **Step 1: Write Sections 1-4 of explorer.js (state, init, filtering, list rendering)**

Replace the content of `seo/static/seo/explorer.js` with:

```js
/**
 * Explorer — carte Leaflet + liste filtree + toggle mobile.
 * / Explorer — Leaflet map + filtered list + mobile toggle.
 *
 * SECTIONS :
 *   1. Etat global / Global state
 *   2. Initialisation / Initialization
 *   3. Filtrage / Filtering
 *   4. Rendu liste / List rendering
 *   5. Carte Leaflet / Leaflet map
 *   6. Cross-highlighting desktop
 *   7. Toggle mobile / Mobile toggle
 *
 * LOCALISATION: seo/static/seo/explorer.js
 */

// ============================================================
// SECTION 1 — Etat global / Global state
// ============================================================

var explorerData = null;   // Donnees parsees depuis json_script / Parsed data from json_script
var activeFilters = {
    text: '',              // Texte de recherche / Search text
    category: 'all'        // Categorie active : all, lieu, event, membership
};
var map = null;            // Instance Leaflet (null = pas encore charge) / Leaflet instance (null = not loaded yet)
var markers = {};          // Dict lieu tenant_id -> marker Leaflet / Dict venue tenant_id -> Leaflet marker
var markerClusterGroup = null;
var mapInitialized = false;

// ============================================================
// SECTION 2 — Initialisation / Initialization
// ============================================================

function init() {
    // Lire les donnees JSON injectees par Django / Read JSON data injected by Django
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
            // Retirer la classe active de toutes les pills
            // / Remove active class from all pills
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

    // Filtrer les lieux / Filter venues
    if (activeFilters.category === 'all' || activeFilters.category === 'lieu') {
        for (var i = 0; i < explorerData.lieux.length; i++) {
            var lieu = explorerData.lieux[i];
            if (matchesText(lieu)) {
                filteredLieux.push(lieu);
            }
        }
    }

    // Filtrer les evenements / Filter events
    if (activeFilters.category === 'all' || activeFilters.category === 'event') {
        for (var j = 0; j < explorerData.events.length; j++) {
            var event = explorerData.events[j];
            if (matchesText(event)) {
                filteredEvents.push(event);
            }
        }
    }

    // Filtrer les adhesions / Filter memberships
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

    // Mettre a jour les marqueurs si la carte est initialisee
    // / Update markers if map is initialized
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

    // Lieux d'abord, puis evenements, puis adhesions
    // / Venues first, then events, then memberships
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

    // Rebrancher les event listeners pour le cross-highlighting desktop
    // / Rebind event listeners for desktop cross-highlighting
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
```

- [ ] **Step 2: Start the dev server and verify the list renders**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002
```

Open `http://tibillet.localhost:8002/explorer/` — the list should display cards (venues, events, memberships). Search and pills should filter the list. The map area will be empty (Task 6).

---

## Task 6: Build explorer.js — Map, Cross-highlighting, Mobile Toggle

**Files:**
- Modify: `seo/static/seo/explorer.js` (append Sections 5-7)

- [ ] **Step 1: Append Section 5 (Leaflet map) to explorer.js**

Add at the end of `seo/static/seo/explorer.js`:

```js
// ============================================================
// SECTION 5 — Carte Leaflet / Leaflet map
// ============================================================

function initMap() {
    if (mapInitialized) return;

    var mapContainer = document.getElementById('explorer-map');
    if (!mapContainer) return;

    // Creer l'instance Leaflet / Create Leaflet instance
    map = L.map('explorer-map', {
        zoomControl: true,
        scrollWheelZoom: true,
    });

    // Tuiles OpenStreetMap / OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19,
    }).addTo(map);

    // Groupe de clusters / Cluster group
    markerClusterGroup = L.markerClusterGroup();
    map.addLayer(markerClusterGroup);

    // Ajouter les marqueurs / Add markers
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

        // Custom DivIcon (pill avec nom du lieu) / Custom DivIcon (pill with venue name)
        var icon = L.divIcon({
            className: '',
            html: '<div class="explorer-pin" data-lieu-id="' + escapeHtml(lieu.tenant_id) + '">'
                + escapeHtml(lieu.name) + '</div>',
            iconSize: null,
            iconAnchor: [0, 0],
        });

        var marker = L.marker([lat, lng], { icon: icon });

        // Popup enrichi / Enriched popup
        var popupContent = buildPopupContent(lieu);
        marker.bindPopup(popupContent, { maxWidth: 280 });

        // Stocker le marker pour le cross-highlighting / Store marker for cross-highlighting
        markers[lieu.tenant_id] = marker;

        // Au clic sur le marker : scroll vers la card dans la liste
        // / On marker click: scroll to the card in the list
        (function(tenantId) {
            marker.on('click', function() {
                onMarkerClick(tenantId);
            });
        })(lieu.tenant_id);

        markerClusterGroup.addLayer(marker);
        bounds.push([lat, lng]);
    }

    // Ajuster la vue pour montrer tous les marqueurs / Fit view to show all markers
    if (bounds.length > 0) {
        map.fitBounds(bounds, { padding: [20, 20] });
    } else {
        // Vue par defaut : centre de la France / Default view: center of France
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

    // Prochains evenements (max 3) / Next events (max 3)
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

    // Adhesions (max 2) / Memberships (max 2)
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

    // Creer un set des tenant_ids filtres / Create a set of filtered tenant_ids
    var filteredIds = {};
    for (var i = 0; i < filteredLieux.length; i++) {
        filteredIds[filteredLieux[i].tenant_id] = true;
    }

    // Montrer/masquer les marqueurs / Show/hide markers
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
    var marker = markers[lieuId];
    if (!marker) return;

    // Trouver le div du pin et ajouter la classe selected
    // / Find the pin div and add the selected class
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

    // Smooth scroll vers la card / Smooth scroll to the card
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // Highlight temporaire (2 secondes) / Temporary highlight (2 seconds)
    card.setAttribute('data-highlighted', 'true');
    setTimeout(function() {
        card.removeAttribute('data-highlighted');
    }, 2000);
}

// ============================================================
// SECTION 7 — Toggle mobile / Mobile toggle
// ============================================================

var currentView = 'list'; // 'list' ou 'map'

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
        // Passer en vue carte / Switch to map view
        container.classList.add('explorer-view-map');
        fab.innerHTML = '&#9776; Liste';
        currentView = 'map';

        // Lazy init de la carte au premier toggle
        // / Lazy init the map on first toggle
        if (!mapInitialized) {
            initMap();
        } else {
            // Forcer le recalcul de la taille de la carte
            // / Force map size recalculation
            map.invalidateSize();
        }
    } else {
        // Passer en vue liste / Switch to list view
        container.classList.remove('explorer-view-map');
        fab.innerHTML = '&#128506; Carte';
        currentView = 'list';
    }
}

// ============================================================
// Point d'entree / Entry point
// ============================================================

document.addEventListener('DOMContentLoaded', init);
```

- [ ] **Step 2: Start the dev server and test manually**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002
```

Open `http://tibillet.localhost:8002/explorer/` and verify:

1. **Desktop:** The map shows markers on the right. Hovering a card highlights the marker. Clicking a marker scrolls the list.
2. **Mobile** (resize browser to < 992px): The FAB button is visible. Clicking "Carte" shows the map, clicking "Liste" shows the list.
3. **Filtering:** Typing in the search bar filters both list and map. Pills filter by category.
4. **Popup:** Clicking a marker shows the enriched popup with events and memberships.

- [ ] **Step 3: Run all tests (explorer + seo)**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_explorer.py tests/pytest/test_seo.py -v
```

Expected: all tests PASS, no regressions.

---

## Task 7: Final template adjustments

**Files:**
- Modify: `seo/templates/seo/explorer.html` (override `container-lg` for full-width)

- [ ] **Step 1: Check if the content block wraps in container-lg**

Read `seo/templates/seo/base.html` — the `{% block content %}` is inside `<main class="container-lg my-4">`. The explorer needs full-width for the split view. Override this by adding a `{% block main %}` or by restructuring the template.

The simplest approach: don't use `{% block content %}`. Instead, add a new block in `base.html` or override the entire body section. But modifying `base.html` could affect other pages.

Better approach: the explorer template extends `base.html` but uses a different strategy — we add a `{% block main_class %}` mechanism. However, to keep it FALC and avoid touching `base.html` for this, we can simply **not extend base.html** and write a standalone template that copies the navbar/footer.

Simplest FALC solution: add a CSS override in `explorer.css` to remove the container constraint:

```css
/* Surcharger le container-lg de base.html pour le full-width
 * / Override base.html container-lg for full-width */
.explorer-toolbar { margin: -1.5rem -12px 0; padding: 12px 24px; }
```

Actually the cleanest way: modify `base.html` to make the container optional.

- [ ] **Step 2: Add a block override in base.html**

In `seo/templates/seo/base.html`, replace the main content section (around line 114-118):

Current:
```html
<div class="flex-fill d-flex flex-column">
    <main class="container-lg my-4">
        {% block content %}{% endblock %}
    </main>
</div>
```

Replace with:
```html
<div class="flex-fill d-flex flex-column">
    {% block main_wrapper %}
    <main class="container-lg my-4">
        {% block content %}{% endblock %}
    </main>
    {% endblock main_wrapper %}
</div>
```

This adds a `main_wrapper` block that all existing pages ignore (they use `content`). The explorer overrides `main_wrapper` instead.

- [ ] **Step 3: Update explorer.html to use main_wrapper**

Replace the `{% block content %}` in `seo/templates/seo/explorer.html` with `{% block main_wrapper %}`:

```html
{% block main_wrapper %}
<main>

{# Barre de recherche + pills / Search bar + category pills #}
<div class="explorer-toolbar">
    <div class="explorer-search-row">
        <input type="search" class="explorer-search" id="explorer-search"
               placeholder="{% translate 'Rechercher un lieu, événement, adhésion...' %}"
               aria-label="{% translate 'Rechercher' %}">
        <div class="explorer-pills" id="explorer-pills">
            <button class="explorer-pill active" data-category="all">{% translate "Tous" %}</button>
            <button class="explorer-pill" data-category="lieu">{% translate "Lieux" %}</button>
            <button class="explorer-pill" data-category="event">{% translate "Événements" %}</button>
            <button class="explorer-pill" data-category="membership">{% translate "Adhésions" %}</button>
        </div>
    </div>
    <div class="explorer-counter" id="explorer-counter"></div>
</div>

{# Split view : liste + carte / Split view: list + map #}
<div class="explorer-container">
    <div class="explorer-list" id="explorer-list"></div>
    <div class="explorer-map" id="explorer-map"></div>
</div>

{# Bouton toggle mobile / Mobile toggle FAB #}
<button class="explorer-fab" id="explorer-fab" aria-label="{% translate 'Basculer carte/liste' %}">
    &#128506; {% translate "Carte" %}
</button>

{# Donnees JSON pour le JS / JSON data for JS #}
{{ explorer_data|json_script:"explorer-data" }}

</main>
{% endblock main_wrapper %}
```

- [ ] **Step 4: Run all tests to check no regression**

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_explorer.py tests/pytest/test_seo.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Manual visual check**

Open `http://tibillet.localhost:8002/explorer/` — verify the split view spans the full width. Check that other pages (`/lieux/`, `/evenements/`, etc.) still have their `container-lg` layout.

---

## Summary

| Task | What it does | Files |
|---|---|---|
| 1 | GPS coords in SEOCache | `seo/services.py`, `seo/tasks.py`, `tests/pytest/test_explorer.py` |
| 2 | `build_explorer_data()` helper | `seo/services.py`, `tests/pytest/test_explorer.py` |
| 3 | View + route + template skeleton | `seo/views.py`, `seo/urls.py`, `seo/templates/seo/base.html`, `seo/templates/seo/explorer.html`, `seo/static/seo/explorer.css`, `seo/static/seo/explorer.js` |
| 4 | Full CSS | `seo/static/seo/explorer.css` |
| 5 | JS sections 1-4 (state, init, filtering, list) | `seo/static/seo/explorer.js` |
| 6 | JS sections 5-7 (map, cross-highlighting, toggle) | `seo/static/seo/explorer.js` |
| 7 | Full-width template override | `seo/templates/seo/base.html`, `seo/templates/seo/explorer.html` |
