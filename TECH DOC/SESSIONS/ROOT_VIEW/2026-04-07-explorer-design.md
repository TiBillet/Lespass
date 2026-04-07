# Spec — Page Explorer (Carte Leaflet + Recherche/Lieux fusionnés)

> Date : 2026-04-07
> Branche : V2
> Inspiration : `TECH DOC/IDEAS/airbnb-mobile-map-search-anatomy.md`

---

## 1. Objectif

Créer une page `/explorer/` sur le ROOT (tibillet.localhost) qui permet de découvrir
les lieux, événements et adhésions du réseau TiBillet sur une carte interactive Leaflet
avec une liste filtrée synchronisée. Pattern inspiré de la recherche Airbnb.

**Ce n'est PAS une page SEO** — c'est un outil de découverte interactif (JS lourd).
Les pages `/lieux/`, `/evenements/`, `/adhesions/`, `/recherche/` restent en place
(HTML statique, JSON-LD, crawlable).

---

## 2. Décisions validées

| Décision | Choix | Raison |
|---|---|---|
| Mobile | Toggle Carte/Liste (pattern tablette Airbnb) | Fiable sur tous les navigateurs, simple à implémenter |
| Contenu carte | Lieux enrichis (popup avec events + adhésions) | Un marqueur = une adresse physique, pas de superposition |
| URL | `/explorer/` (nouvelle page) | Sépare l'outil interactif des pages SEO crawlables |
| Filtres | Texte libre + pills catégorie (Tous/Lieux/Événements/Adhésions) | Couvre les cas d'usage principaux sans complexité |
| Cross-highlighting | Bidirectionnel sans popover custom | Popup Leaflet natif suffit, scroll vers card au clic marqueur |
| Techno carte | Leaflet 1.9 + OSM tiles + MarkerCluster (CDN) | Libre, gratuit, léger, aligné valeurs coopératives |
| Lieux sans GPS | Masqués de l'explorer | Géoloc obligatoire à terme (code postal min à la création) |
| Données | JSON inline via `json_script` (~150 KB) | Zéro requête AJAX, rendu instantané, FALC |
| JS | Vanilla JS monolithique (~450 lignes) | Cohérent avec le projet (HTMX + vanilla), zéro tooling |
| Dark mode | Désactivé sur l'explorer | Simplifie le CSS, la carte OSM est en clair |

---

## 3. Layout Desktop (>= 992px)

### 3.1 Structure

```
┌──────────────────────────────────────────────────────────────┐
│  NAVBAR (héritée de seo/base.html) + lien "Explorer" actif   │
├──────────────────────────────────────────────────────────────┤
│  SEARCH BAR (texte libre, pill shape) + PILLS catégorie       │
├──────────────────────────────────────────────────────────────┤
│  COMPTEUR ("42 lieux · 18 événements · 7 adhésions")          │
├──────────────────────────────────────────────────────────────┤
│  ┌────────────────────────┬──────────────────────────────┐    │
│  │                        │                              │    │
│  │   LISTE (55%)          │      CARTE LEAFLET (45%)     │    │
│  │   overflow-y: auto     │      position: sticky        │    │
│  │   cards mixées         │      top: navbar_height      │    │
│  │   (lieux/events/       │      height: calc(100vh      │    │
│  │    adhésions)           │        - header_height)      │    │
│  │                        │      MarkerCluster            │    │
│  │                        │                              │    │
│  └────────────────────────┴──────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Barre de recherche

- Champ texte avec placeholder "Rechercher un lieu, événement, adhésion..."
- Filtre live au keyup avec debounce 300ms
- Recherche dans : `name`, `locality`, `short_description`
- À droite du champ : 4 pills cliquables (Tous / Lieux / Événements / Adhésions)
- La pill active a un fond noir (#222) et texte blanc
- Cliquer une pill filtre la liste par type de contenu
- Les deux filtres (texte + pill) se combinent (AND)

### 3.3 Compteur

- Texte "N lieux · N événements · N adhésions"
- Mis à jour en temps réel quand le filtre change
- Reflète le nombre d'items actuellement visibles

### 3.4 Liste de résultats

Cards mixées dans une seule liste scrollable. Chaque card affiche :

**Card Lieu :**
- Icône/logo (80x80px, border-radius: 8px)
- Nom (font-weight: 600)
- Badge vert "Lieu"
- Localité (ville, pays)
- Description courte (tronquée)
- "N événements · N adhésions"
- Attribut `data-lieu-id` pour le cross-highlighting

**Card Événement :**
- Icône calendrier (fond orange)
- Nom de l'événement
- Badge orange "Événement"
- Date + nom du lieu parent
- Description courte

**Card Adhésion :**
- Icône adhésion (fond bleu)
- Nom de l'adhésion
- Badge bleu "Adhésion"
- Nom du lieu parent

Lien au clic : `https://{domain}/` (lieu), `https://{domain}/event/{slug}/` (événement),
`https://{domain}/` (adhésion — pas de lien direct produit).

### 3.5 Carte Leaflet

- Tuiles OpenStreetMap : `https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png`
- Vue initiale : fitBounds sur tous les marqueurs (zoom auto)
- MarkerCluster pour le regroupement à faible zoom

**Pins :**
- Custom DivIcon : pill blanc, texte noir, nom du lieu
- Style : `border-radius: 999px; background: #fff; padding: 4px 10px; font-weight: 600; font-size: 12px`
- Ombre : `box-shadow: 0 2px 6px rgba(0,0,0,0.2)`
- État selected : `background: #222; color: #fff; transform: scale(1.08)`
- Clusters : cercle avec nombre, style MarkerCluster par défaut

**Popup enrichi (au clic sur un pin) :**
- maxWidth: 280px
- Contenu HTML : nom, description, localité, prochains events (max 3), adhésions (max 2), lien "Visiter"
- Généré côté client par `buildPopupContent(lieu)`

### 3.6 Cross-highlighting bidirectionnel

| Direction | Déclencheur | Action |
|---|---|---|
| Liste → Carte | `mouseenter` sur une card lieu | Le marker correspondant passe en état selected (fond noir, scale 1.05) |
| Liste → Carte | `mouseleave` sur une card lieu | Le marker revient à l'état normal |
| Carte → Liste | `click` sur un marker | Smooth scroll de la liste vers la card correspondante + highlight temporaire (border) |

Les cards événement et adhésion n'ont pas de marker propre — le hover sur ces cards
highlight le marker du lieu parent.

---

## 4. Layout Mobile (< 992px)

### 4.1 Pattern

Toggle Carte/Liste (pattern tablette Airbnb 744-1127px). Deux vues plein écran,
un bouton flottant pour switcher.

### 4.2 Vue Liste (par défaut)

- Search bar en haut
- Pills catégorie scrollables horizontalement
- Compteur de résultats
- Cards scrollables (même structure que desktop, taille réduite : icône 64x64px)
- Bouton FAB en bas : pill noir "🗺 Carte"

### 4.3 Vue Carte

- Search bar flottante au-dessus de la carte (avec ombre, fond blanc)
- Carte Leaflet plein écran
- Même pins et popups que desktop
- Bouton FAB en bas : pill noir "☰ Liste"
- Pas de pills catégorie (pas assez de place)

### 4.4 Bouton FAB (toggle)

- `position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%)`
- `background: #222; color: #fff; border-radius: 999px; padding: 12px 24px`
- `font-weight: 600; box-shadow: 0 4px 12px rgba(0,0,0,0.3)`
- Transition : simple swap CSS (`display: none/flex`), pas d'animation
- z-index élevé (au-dessus de la carte et de la liste)

### 4.5 Lazy loading carte

Leaflet + tuiles OSM ne se chargent qu'au premier tap sur "Carte".
Pas d'impact sur le temps de chargement initial de la vue liste.

### 4.6 Pas de cross-highlighting mobile

Pas de hover sur mobile. Le tap sur un pin ouvre le popup Leaflet natif.
Pas de scroll automatique (la liste n'est pas visible en vue carte).

---

## 5. Data flow

### 5.1 Enrichissement SEOCache

`seo/services.py:build_tenant_config_data()` — ajouter 2 champs :

```python
if config.postal_address:
    data["latitude"] = float(config.postal_address.latitude) if config.postal_address.latitude else None
    data["longitude"] = float(config.postal_address.longitude) if config.postal_address.longitude else None
```

Ces champs se propagent dans `aggregate_lieux` via le Celery task existant (`refresh_seo_cache`).

### 5.2 Helper `build_explorer_data()`

Nouveau helper dans `seo/services.py` qui construit la structure pour le JS client :

```python
def build_explorer_data():
    """
    Construit les données pour la page Explorer.
    Neste les events et memberships sous leur lieu parent.
    / Build data for the Explorer page.
    Nest events and memberships under their parent venue.
    """
```

Entrée : lit les 3 agrégats du SEOCache (lieux, events, memberships).
Sortie : dict avec 3 clés (`lieux`, `events`, `memberships`).

- `lieux` : liste de dicts, chaque lieu enrichi avec ses `events` et `memberships` nestés
- `events` : liste plate de tous les événements (pour le filtre pills)
- `memberships` : liste plate de toutes les adhésions (pour le filtre pills)

Chaque événement et adhésion porte un `lieu_id` qui correspond au `tenant_id` du lieu parent
(c'est la clé de jointure entre les 3 agrégats SEOCache).

### 5.3 Vue `explorer(request)`

```python
def explorer(request):
    explorer_data = build_explorer_data()
    context = {
        "explorer_data": explorer_data,
        "page_title": "Explorer - TiBillet",
    }
    return TemplateResponse(request, "seo/explorer.html", context)
```

### 5.4 Injection dans le template

```html
{{ explorer_data|json_script:"explorer-data" }}
```

Le JS lit avec :
```js
var explorerData = JSON.parse(document.getElementById('explorer-data').textContent);
```

---

## 6. Structure JS — `explorer.js`

Fichier unique vanilla JS, ~450 lignes, 7 sections :

| Section | Rôle | ~Lignes |
|---|---|---|
| 1. État global | `explorerData`, `activeFilters`, `map`, `markers`, `markerClusterGroup` | 20 |
| 2. Initialisation | `init()`, `bindSearch()`, `bindPills()` | 30 |
| 3. Filtrage | `applyFilters()`, `matchesText()`, `updateCounters()` | 60 |
| 4. Rendu liste | `renderList()`, `buildLieuCard()`, `buildEventCard()`, `buildMembershipCard()` | 80 |
| 5. Carte Leaflet | `initMap()`, `addMarkers()`, `buildPopupContent()`, `updateMapMarkers()` | 100 |
| 6. Cross-highlighting | `onCardHover()`, `onCardLeave()`, `onMarkerClick()`, `scrollToCard()` | 50 |
| 7. Toggle mobile | `toggleView()`, `updateFAB()` | 30 |

Point d'entrée : `document.addEventListener('DOMContentLoaded', init)`.

Sur desktop : `initMap()` appelé dans `init()`.
Sur mobile : `initMap()` appelé au premier tap sur le FAB.

---

## 7. CSS — `explorer.css`

Styles spécifiques à l'explorer. ~150 lignes.

**Layout :**
- `.explorer-container` : `display: flex` (desktop), `display: block` (mobile)
- `.explorer-list` : `width: 55%; overflow-y: auto` (desktop), `width: 100%` (mobile)
- `.explorer-map` : `width: 45%; position: sticky; top: var(--navbar-h)` (desktop), `width: 100%; height: 100vh` (mobile)

**Composants :**
- `.explorer-search` : champ texte pill shape
- `.explorer-pill` / `.explorer-pill.active` : pills catégorie
- `.explorer-card` : cards résultats (réutilise `.seo-card` pour les ombres)
- `.explorer-card[data-highlighted]` : `border-color: #222` (cross-highlight)
- `.explorer-badge-lieu` / `-event` / `-adhesion` : badges couleur
- `.explorer-fab` : bouton flottant toggle mobile
- `.explorer-pin` : custom DivIcon Leaflet
- `.explorer-pin.selected` : état selected (fond noir)

**Leaflet overrides :**
- `.leaflet-popup-content-wrapper` : `border-radius: 12px`

**Pas de dark mode** — thème forcé clair sur cette page.

---

## 8. Template — `explorer.html`

Hérite de `seo/base.html` mais surcharge le contenu pour un layout full-width
(pas de `container-lg` sur la zone split view).

```html
{% extends "seo/base.html" %}

{% block extra_head %}
<!-- Leaflet CSS (CDN) -->
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9/dist/leaflet.css" />
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5/dist/MarkerCluster.css" />
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5/dist/MarkerCluster.Default.css" />
<link rel="stylesheet" href="{% static 'seo/explorer.css' %}" />
{% endblock %}

{% block content %}
<!-- Search bar + pills + compteur -->
<!-- Split: liste + carte -->
<!-- FAB mobile -->
<!-- JSON data -->
{{ explorer_data|json_script:"explorer-data" }}
{% endblock %}

{% block extra_js %}
<script src="https://unpkg.com/leaflet@1.9/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5/dist/leaflet.markercluster.js"></script>
<script src="{% static 'seo/explorer.js' %}"></script>
{% endblock %}
```

---

## 9. Fichiers

### Créés (4)

| Fichier | Rôle | ~Lignes |
|---|---|---|
| `seo/templates/seo/explorer.html` | Template full-width, CDN Leaflet, json_script | ~80 |
| `seo/static/seo/explorer.js` | Carte + liste + filtres + toggle mobile | ~450 |
| `seo/static/seo/explorer.css` | Layout split/mobile, cards, pins, FAB | ~150 |
| `tests/pytest/test_explorer.py` | Tests vue + données | ~60 |

### Modifiés (3)

| Fichier | Modification |
|---|---|
| `seo/services.py` | `build_tenant_config_data()` +latitude/longitude. Nouveau helper `build_explorer_data()` |
| `seo/views.py` | Nouvelle vue `explorer(request)` |
| `TiBillet/urls_public.py` | Route `path('explorer/', seo_views.explorer, name='explorer')` |

### Aucune migration. Aucun nouveau modèle. Aucune dépendance Python.

---

## 10. Hors scope V1

- Filtre par date (date picker range pour les événements)
- Dark mode sur la page explorer
- Bottom sheet mobile (3 snap points)
- Popover custom desktop (hover-intent avec grace period)
- "Search as I move the map" (re-filtrage par bounding box de la carte)
- Pagination de la liste
- Mini-pins (marqueurs secondaires sans nom)
- Skeleton loading
- Infinite scroll

---

## 11. Tests

### pytest (`test_explorer.py`)

1. **test_explorer_view_returns_200** — la vue répond en 200
2. **test_explorer_data_contains_lieux_with_coords** — `build_explorer_data()` inclut latitude/longitude
3. **test_explorer_data_nests_events_under_lieux** — les events sont bien nestés sous leur lieu
4. **test_explorer_data_excludes_lieux_without_coords** — les lieux sans GPS sont exclus
5. **test_explorer_template_contains_json_script** — le template contient le tag `json_script`
6. **test_build_tenant_config_data_includes_gps** — `build_tenant_config_data()` retourne latitude/longitude

---

## 12. Inspiration

Voir `TECH DOC/IDEAS/airbnb-mobile-map-search-anatomy.md` pour le document complet
d'analyse du pattern Airbnb. Cette spec en est une adaptation pour TiBillet :
- Lieux au lieu de logements
- Noms au lieu de prix sur les pins
- Toggle simple au lieu de bottom sheet mobile
- Popup Leaflet natif au lieu de popover custom
- Leaflet + OSM au lieu de Mapbox GL
