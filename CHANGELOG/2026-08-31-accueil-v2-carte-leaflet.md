# Accueil V2 : vraie carte Leaflet dans le panneau « Où l'on est » / V2 home: real Leaflet map in the map panel

**Date :** 2026-08-31
**Migration :** Non

## Resume / Summary
**Quoi / What :** Le panneau `.map-panel` de l'accueil V2 affiche désormais une
**vraie carte Leaflet** centrée sur l'adresse du lieu (`config.postal_address`),
avec un marqueur et une popup au nom du tenant. Si le tenant n'a pas renseigné
de coordonnées GPS, l'ancien placeholder décoratif (fond quadrillé + pin) est
conservé.
/ The V2 home `.map-panel` now shows a real Leaflet map centered on the venue
address, with a marker and popup. Without GPS coordinates, the former decorative
placeholder is kept.

**Pourquoi / Why :** Le panneau était une fausse carte (fond quadrillé CSS + pin
positionné en dur à 50%/52%). La maquette demandait une carte réelle. Le pattern
est repris de `pages/V2/partials/bloc_lieu.html` : assets Leaflet vendorisés
chargés paresseusement (ids `leaflet-css`/`leaflet-js` dédoublonnés), garde
`_leaflet_id` anti double-init (swaps HTMX `hx-target="body"`), fond de carte
commun `tbPoserFondDeCarte()` (MapTiler + repli OSM France sans clé).
/ The panel was a fake map (CSS grid background + hardcoded pin). The pattern is
copied from `bloc_lieu.html`: lazily loaded vendored Leaflet assets, `_leaflet_id`
guard for HTMX body swaps, shared basemap with keyless fallback.

**Aucune modification Python** : `config` est déjà dans le contexte de `index()`
(`BaseBillet/views.py`) et `maptiler_key` est exposé à tous les gabarits par le
context processor `TiBillet/maptiler.py`. Coordonnées et clé passent par les
attributs `data-*` (pas de `window.xxx` ni de JSON injecté).
/ No Python change: `config` is already in the `index()` context and
`maptiler_key` comes from a context processor. Coordinates and key go through
`data-*` attributes.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `pages/templates/pages/V2/vues/accueil.html` | Carte Leaflet conditionnelle dans `.map-panel` (si latitude/longitude renseignées), sinon placeholder d'origine conservé ; `{% load static %}` ajouté ; label « Où l'on est » passé en `{% translate %}` ; `data-testid="accueil-carte-lieu"` + `role="application"` + `aria-label` |
| `pages/static/V2/css/V2.css` | Nouvelle règle `.map-panel__carte` (remplit le panneau, le fond quadrillé sert d'écran de chargement) ; `z-index: 1001` sur `.map-panel__toolbar` pour passer au-dessus des contrôles Leaflet |

### Choix d'implementation / Implementation notes
- `scrollWheelZoom: false` : la carte vit dans une page scrollable, la molette
  doit continuer à faire défiler la page.
- Popup du marqueur construite via `textContent` (jamais `innerHTML`) : pas
  d'injection XSS via `config.organisation`.
- Le fond quadrillé de `.map-panel` est conservé : il sert de fond de chargement
  avant l'arrivée des tuiles.

### Piege de localisation (DecimalField -> virgule FR) / Localization pitfall
`USE_L10N = True` + `LANGUAGE_CODE = 'fr'` (`TiBillet/settings.py`) : le moteur
de template **localise les `Decimal` à chaque interpolation `{{ ... }}`**
(`45.77` → `45,77`). Injectées en brut dans `data-lat`/`data-lng`, les
coordonnées étaient tronquées par `parseFloat("45,77")` → `45`, sans erreur
console. Fix : filtre `|unlocalize` (+ `{% load l10n %}`), commenté dans le
template pour éviter toute suppression future.

Pourquoi les autres cartes du projet n'ont pas ce bug :
- `bloc_lieu.html` et `explorer_widget.html` passent par `|json_script` →
  `json.dumps()` en Python, qui exige le point : protection **par design**.
- `evenement_geoloc.html` interpole avec `|safe` : `mark_safe()` convertit le
  `Decimal` en `SafeString` (str) **avant** l'étape de localisation, et
  `localize()` ignore les chaînes : protection **par accident**. Ne pas retirer
  le `|safe` de ce fichier sans ajouter `|unlocalize` à la place.

---

## Comment tester (a la main) / Manual test

### Test 1 — tenant AVEC coordonnées GPS
1. Admin → Configuration → adresse postale : vérifier que latitude/longitude
   sont renseignées.
2. Ouvrir l'accueil `/` (skin V2).
3. Vérification attendue : une vraie carte Leaflet remplit le panneau, centrée
   sur le lieu, avec un marqueur. Le label « Où l'on est » reste visible
   au-dessus de la carte. Clic sur le marqueur → popup avec le nom du lieu.
4. Naviguer vers une autre page puis revenir par la navbar (navigation HTMX) :
   la carte se ré-affiche sans erreur console, sans double initialisation.
5. La molette au-dessus de la carte fait défiler la page (pas de zoom captif).

### Test 2 — tenant SANS coordonnées GPS
1. Vider latitude/longitude de l'adresse du tenant.
2. Recharger `/`.
3. Vérification attendue : le placeholder d'origine s'affiche (fond quadrillé +
   pin avec le nom du tenant), aucun appel Leaflet.

### Test 3 — sans clé MapTiler
1. `MAPTILER_KEY` vide dans les settings.
2. Vérification attendue : la carte s'affiche quand même (repli tuiles
   OpenStreetMap France « Humanitarian »).

### Verifs complementaires
- Console navigateur : aucune erreur JS.
- Validation HTML : `role="application"` + `aria-label` présents sur
  `#carte-accueil` ; `data-testid="accueil-carte-lieu"` pour les tests E2E.
- Traductions : chaînes « Où l'on est » et « Carte interactive du lieu » à
  extraire (`makemessages`) — non fait dans cette session.
