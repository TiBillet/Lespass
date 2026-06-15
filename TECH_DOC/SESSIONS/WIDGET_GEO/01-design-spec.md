# Widget de saisie d'adresse géolocalisée — Design spec

**Date** : 2026-05-15
**Auteur** : conception JonasFW13 + Claude (brainstorming via skill superpowers:brainstorming)
**Statut** : implémentée — **architecture revue 2026-05-15 : full client (cf. note ci-dessous)**

> **Revert architecture 2026-05-15** : la spec validait l'approche Hybride (search client + reverse via endpoint serveur). Bascule en full client après découverte d'un problème multi-tenant routing (la route serveur n'était pas accessible sur ROOT où tourne le wizard onboard). Décision : supprimer l'endpoint serveur et appeler Nominatim direct depuis le browser pour le reverse aussi. Trade-off accepté : pas de cache mutualisé serveur (volume faible). Les sections 3.5 (service serveur) et 3.6 (endpoint) sont **obsolètes** — ne pas implémenter. Le helper `AdresseGeolocaliseeField` (3.4) reste valide et utile pour la validation serveur.
**Topic** : nouveau widget réutilisable Django + Leaflet + leaflet-geosearch
**Premier consommateur** : refonte step 03_place du wizard onboard
**Future** : Event admin, formulaire "ajouter un event" frontend, tout autre formulaire qui a besoin d'une adresse géolocalisée

---

## 1. Contexte et motivation

### Problème actuel (step 03_place du wizard onboard)
Le wizard onboard a aujourd'hui une UX en deux temps :
1. L'utilisateur tape une adresse postale dans 4 champs séparés (rue, code postal, ville, pays).
2. Au `change` du premier champ (delay 1s), un POST HTMX déclenche un géocodage Nominatim côté serveur (`/onboard/geocode/`), qui re-rend le partial `geocode_result.html` (incluant `map_widget.html`) et place le marqueur sur la carte.

**Limitations** :
- Pas de suggestions live (l'utilisateur doit valider l'adresse complète avant d'avoir un retour visuel).
- Le swap HTMX recrée la carte à chaque géocodage (flash visuel, perte du zoom courant).
- Pattern non-réutilisable : la logique vit dans `onboard/views.py` + `onboard/services.py` + 2 templates `onboard/partials/`.

### Objectif
Créer un widget réutilisable type "GPS" :
- **Search bar intégrée à la carte** (leaflet-geosearch) avec **suggestions live**.
- **Marqueur draggable** avec **géocodage inverse automatique** au drag.
- **Champs adresse séparés auto-remplis** depuis le résultat Nominatim (compat backend qui consomme du PostalAddress structuré).
- **Réutilisable** dans n'importe quel formulaire Django : onboard, Event admin, frontend "ajouter un event", etc.

### Contraintes
- Stack : Django 4.x + DRF, **pas de npm/webpack** — assets via CDN unpkg (Leaflet 1.9.4 + leaflet-geosearch 4.4.0).
- Pattern DJC/FALC : noms verbeux, commentaires bilingues FR/EN, code lisible top-down.
- Multi-tenant : le widget doit fonctionner aussi bien depuis le schema `public` (wizard onboard) que depuis n'importe quel tenant (Event admin).
- Locale : noms de lieux retournés par Nominatim selon la langue active de l'utilisateur Django (`get_language()`).
- Politique Nominatim : `User-Agent` identifiable + max 1 req/s par IP côté serveur (la search live côté navigateur est gérée par leaflet-geosearch).

---

## 2. Approche retenue (Hybride)

| Action | Côté navigateur (JS) | Côté serveur (Django) |
|---|---|---|
| Recherche live (typing dans la search bar) | leaflet-geosearch → Nominatim **direct** (1 req/s par user, géré par la lib) | — |
| Drag du marqueur (geocodage inverse) | `marker.on('dragend')` → fetch POST `/widgets/geocode-reverse/` | Endpoint DRF avec cache Redis 24h, User-Agent TiBillet, throttle 1/s |
| Soumission du formulaire parent | POST classique avec hidden inputs | Lecture par form field `AdresseGeolocaliseeField` ou par serializer du form parent |

**Justification** : équilibre simplicité / standard leaflet-geosearch / structure préservée. La recherche live côté browser évite un hop réseau supplémentaire (latence) ; le reverse côté serveur est mutualisable (cache partagé entre tous les users qui posent un marker au même endroit).

---

## 3. Composants livrés

### 3.1 Template widget réutilisable

**Fichier** : `templates/widgets/widget_carte_adresse.html`

**Variables de contexte** :
| Variable | Type | Défaut | Usage |
|---|---|---|---|
| `identifiant_widget` | str | **obligatoire** | Préfixe IDs DOM + `name=` HTTP. Ex: `"place"` → `id="place-container"`, `name="place_latitude"`. |
| `latitude_initiale` | float? | `None` | Pré-remplit le marqueur + centre la carte. Si `None` ET `longitude_initiale` `None`, vue centrée sur la France (zoom 5). |
| `longitude_initiale` | float? | `None` | idem |
| `adresse_initiale` | str? | `None` | Pré-remplit la search bar. Affiché tel quel (pas de re-geocoding au load). |
| `hauteur_carte` | str | `"400px"` | Hauteur CSS du container. Accepte n'importe quelle unité CSS. |
| `champs_adresse_separes` | bool | `True` | Si `False`, n'affiche QUE search + carte (cas usage : on n'a besoin que de lat/lng). |
| `noms_champs_separes` | dict? | `None` | Override les `name=` HTTP des 4 champs adresse. Défaut: `{"rue": "street_address", "code_postal": "postal_code", "ville": "address_locality", "pays": "address_country"}`. Permet la compat avec un backend existant qui attend d'autres noms. |
| `required` | bool | `False` | Ajoute `required` sur les hidden lat/lng (HTML5 validation côté client + signale au form field serveur). |

**Champs HTML émis** :

```html
<!-- Toujours émis -->
<input type="hidden" name="{identifiant_widget}_latitude" id="{identifiant_widget}-latitude">
<input type="hidden" name="{identifiant_widget}_longitude" id="{identifiant_widget}-longitude">
<input type="hidden" name="{identifiant_widget}_adresse" id="{identifiant_widget}-adresse">

<!-- Container de la carte (ID préfixé pour éviter collision N widgets / page) -->
<div id="{identifiant_widget}-container" data-widget-initialized="false"
     data-identifiant="{identifiant_widget}"
     style="height: {hauteur_carte}; ...">
</div>

<!-- Si champs_adresse_separes=True (défaut) -->
<input type="text" name="{noms_champs_separes.rue}"           id="{identifiant_widget}-street">
<input type="text" name="{noms_champs_separes.code_postal}"   id="{identifiant_widget}-postal">
<input type="text" name="{noms_champs_separes.ville}"         id="{identifiant_widget}-locality">
<input type="text" name="{noms_champs_separes.pays}"          id="{identifiant_widget}-country">
```

**Tags `<script>` et `<link>` Leaflet + leaflet-geosearch** : émis dans le template via `{% include %}` ou via un block `extra_head` selon le contexte. Décision pragmatique : on les émet INSIDE le widget template, à la fin (après le DOM du container). Si plusieurs widgets sur la même page, le navigateur dédoublonne les `<script src="...">` identiques (comportement standard).

### 3.2 JavaScript d'init

**Fichier** : `static/widgets/widget_carte_adresse.js`

**API exposée** : aucune — l'IIFE scanne le DOM au `DOMContentLoaded` et initialise tous les containers `[data-widget-initialized="false"][data-identifiant]`.

**Structure** :
```javascript
(function () {
    "use strict";

    // Configuration : aligne sur le serveur (politique Nominatim).
    const REVERSE_GEOCODE_URL = "/widgets/geocode-reverse/";
    const CARTODB_TILES = "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png";
    const FRANCE_CENTER = [46.6, 2.5];
    const FRANCE_ZOOM = 5;
    const DETAIL_ZOOM = 15;

    function initialiser_widget_carte_adresse(container) {
        const identifiant = container.dataset.identifiant;
        // ... récupère les inputs hidden + champs adresse via getElementById préfixé ...
        // ... crée la map Leaflet, ajoute le tile CartoDB ...
        // ... ajoute le GeoSearchControl avec OpenStreetMapProvider ...
        // ... bind les events search + dragend ...
    }

    function placer_marqueur_et_remplir_champs(map, identifiant, latitude, longitude, adresse_complete, parties_adresse) { ... }

    async function recuperer_coordonnees_apres_deplacement_du_marqueur(evenement_drag, identifiant) { ... }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll('[data-widget-initialized="false"][data-identifiant]')
            .forEach(initialiser_widget_carte_adresse);
    });

    // Cas HTMX : si un swap réinjecte le widget (re-render 422 par exemple),
    // on relance l'init sur les nouveaux containers.
    document.body.addEventListener("htmx:afterSettle", function () {
        document.querySelectorAll('[data-widget-initialized="false"][data-identifiant]')
            .forEach(initialiser_widget_carte_adresse);
    });
})();
```

**Mapping Nominatim → champs adresse** :
| Champ DOM | Source Nominatim `address.*` (avec `addressdetails=1`) |
|---|---|
| `{id}-street` | `house_number + " " + road` (concatène si les deux présents) |
| `{id}-postal` | `postcode` |
| `{id}-locality` | `city` ou `town` ou `village` ou `municipality` (premier non-vide) |
| `{id}-country` | `country` |

### 3.3 CSS

**Fichier** : `static/widgets/widget_carte_adresse.css`

Surcharges minimales :
- Container : `border-radius` cohérent avec le projet (10px), `overflow: hidden`.
- GeoSearchControl : style harmonisé avec les form-control Bootstrap du projet (border, shadow, focus ring vert TiBillet).
- Marqueur : icône Leaflet par défaut (déjà servie par CDN).

### 3.4 Form field optionnel

**Fichier** : `BaseBillet/form_fields.py::AdresseGeolocaliseeField`

```python
class AdresseGeolocaliseeField:
    """
    Helper de validation pour le widget carte adresse.

    Pas un Django Form (le projet utilise DRF Serializers). Expose une
    méthode statique `extraire_depuis(post_data, identifiant_widget,
    obligatoire=False)` qui retourne un dict validé ou raise
    ValidationError.
    """

    @staticmethod
    def extraire_depuis(post_data, identifiant_widget, obligatoire=False):
        """
        Retourne {latitude, longitude, adresse} ou raise ValidationError.

        :param post_data: request.POST ou request.data (dict-like).
        :param identifiant_widget: str, ex "place".
        :param obligatoire: bool, True -> raise si lat/lng absents.
        """
        # ... lit post_data[f"{identifiant_widget}_latitude"], etc.
        # ... cast float, vérifie -90 ≤ lat ≤ 90, -180 ≤ lng ≤ 180.
        # ... raise ValidationError(_("Coordonnées invalides")) si KO.
        # ... retourne {"latitude": ..., "longitude": ..., "adresse": ...}.
```

**Note** : pas un `forms.Field` parce que le projet utilise des **DRF Serializers** (cf. djc skill). C'est un helper statique consommé par les serializers existants.

### 3.5 Service serveur reverse geocode (mutualisable)

**Fichier** : `BaseBillet/services_geocode.py`

```python
def reverse_geocode(latitude, longitude, lang=None):
    """
    Géocodage inverse : (lat, lng) -> {display_name, address: {...}}.
    Cache Redis 24h sur (round(lat, 5), round(lng, 5), lang).
    """
```

**Logique reprise de `onboard/services.py::geocode`** :
- User-Agent `"TiBillet-Widget/1.0 (contact@tibillet.re)"`.
- Timeout 5s.
- Logs warning sur erreur réseau / status non-200.
- `accept-language` du user actuel (`get_language()`) si `lang=None`.

**Note refacto** : à terme, `onboard/services.py::geocode` (forward) gagnerait à être déplacé aussi dans `BaseBillet/services_geocode.py` pour mutualisation. **Hors scope cette session** — on garde `geocode` dans onboard tant que rien d'autre ne le consomme.

### 3.6 Endpoint reverse geocode

**Fichier** : `BaseBillet/views_widgets.py::WidgetReverseGeocodeViewSet`

```python
class WidgetReverseGeocodeViewSet(viewsets.ViewSet):
    """ViewSet DRF explicite (PAS ModelViewSet) — cf. djc skill."""

    permission_classes = [permissions.AllowAny]  # widget peut être public
    throttle_classes = [WidgetReverseGeocodeRateThrottle]  # 1/s/IP

    @action(detail=False, methods=["POST"], url_path="reverse")
    def reverse(self, request):
        """
        POST /widgets/geocode-reverse/
        Body: {"lat": 48.8566, "lng": 2.3522}
        Response 200: {"display_name": "...", "address": {...}}
        Response 400: {"detail": "Validation error"}
        Response 503: {"display_name": "", "address": {}}  # Nominatim down, pas un crash
        """
```

**URL** : `/widgets/geocode-reverse/` mappée dans `BaseBillet/urls.py` (URLs SHARED accessibles depuis tous les schemas).

---

## 4. Refonte step 03_place du wizard onboard (1er consommateur)

### 4.1 Suppressions

| Fichier | Action |
|---|---|
| `onboard/templates/onboard/partials/map_widget.html` | **Supprimé** — remplacé par le nouveau widget |
| `onboard/templates/onboard/partials/geocode_result.html` | **Supprimé** — plus de swap HTMX, le widget gère tout côté JS |
| `onboard/views.py::geocode` action + `geocode_endpoint` URL | **Supprimés** — recherche live faite côté navigateur par leaflet-geosearch |
| `onboard/services.py::geocode` (forward) | **Conservé** mais devient dead code dans onboard (la search live est désormais côté navigateur via leaflet-geosearch). Conservé volontairement parce que (1) zéro risque de régression, (2) servira immédiatement si un autre formulaire admin Django classique a besoin de forward serveur, (3) refacto vers `BaseBillet/services_geocode.py` propre quand on aura un 2e consommateur réel. |
| `onboard/tests/test_step_place.py::test_geocode_endpoint_returns_partial_with_coords` | **Supprimé** (endpoint disparu) |
| `onboard/tests/test_services_geocode.py` | **Conservé** — teste toujours `onboard/services.py::geocode` (qui existe encore) |

### 4.2 Template `03_place.html` — restructuré

```django
{% extends "onboard/base_wizard.html" %}
{% load i18n static %}

{% block step_content %}
<header>...</header>

<form method="post" action="{% url 'onboard-place' %}" novalidate
      data-testid="onboard-place-form" class="vstack gap-3">
    {% csrf_token %}

    {# Widget réutilisable. Le mapping `noms_champs_separes` permet de garder #}
    {# les noms HTTP existants côté backend (street_address, postal_code,    #}
    {# address_locality, address_country) pour ne pas casser le serializer.  #}
    {% include "widgets/widget_carte_adresse.html" with
        identifiant_widget="place"
        latitude_initiale=wc.latitude
        longitude_initiale=wc.longitude
        adresse_initiale=wc.street_address
        hauteur_carte="350px"
        champs_adresse_separes=True
        required=True %}

    <div class="d-flex justify-content-between pt-2">
        <a href="{% url 'onboard-identity' %}" class="btn btn-link">{% translate "Précédent" %}</a>
        <button type="submit" class="btn btn-primary btn-lg">{% translate "Continuer" %}</button>
    </div>
</form>
{% endblock %}
```

**Plus de `<script>` Leaflet inline** dans `03_place.html` — c'est le widget qui charge tout.

### 4.3 Adaptation du serializer

**Fichier** : `onboard/serializers.py::OnboardPlaceSerializer`

Ajout de la lecture des champs préfixés `place_latitude` / `place_longitude` / `place_adresse` :

```python
class OnboardPlaceSerializer(serializers.Serializer):
    # Champs existants
    street_address = serializers.CharField(...)
    postal_code = serializers.CharField(...)
    address_locality = serializers.CharField(...)
    address_country = serializers.CharField(...)

    # Nouveaux champs préfixés (conventions du widget)
    place_latitude = serializers.FloatField(min_value=-90, max_value=90, required=True)
    place_longitude = serializers.FloatField(min_value=-180, max_value=180, required=True)
    place_adresse = serializers.CharField(required=False, allow_blank=True)
```

**Note** : on POURRAIT utiliser `AdresseGeolocaliseeField.extraire_depuis(request.POST, "place")` à la place de DRF, mais on reste cohérent avec le pattern serializers du projet. Le form field reste disponible pour les usages hors-DRF (admin Django classique).

### 4.4 Mise à jour de la persistance

**Fichier** : `onboard/views.py::place` POST

```python
data = serializer.validated_data
with schema_context("meta"):
    WaitingConfiguration.objects.filter(uuid=wc.uuid).update(
        street_address=data["street_address"],
        postal_code=data["postal_code"],
        address_locality=data["address_locality"],
        address_country=data["address_country"],
        latitude=data["place_latitude"],   # nouveau nom préfixé
        longitude=data["place_longitude"], # idem
        current_step=WaitingConfiguration.STEP_DESCRIPTIONS,
    )
```

---

## 5. Data flow complet (cas onboard)

```
1. GET /onboard/place/
   ├─ Render 03_place.html
   └─ {% include "widgets/widget_carte_adresse.html" identifiant_widget="place" ... %}
      └─ HTML émis : container + hidden inputs + champs adresse + <script> CDN

2. DOMContentLoaded
   └─ widget_carte_adresse.js scanne data-widget-initialized="false"
      └─ Initialise la map + GeoSearchControl + marqueur (si coords initiales)

3. User tape "10 rue de Rivoli Paris" dans search bar
   └─ leaflet-geosearch (debounce 500ms) → GET https://nominatim.openstreetmap.org/search?q=...&accept-language=fr&addressdetails=1
   └─ Suggestions affichées
   └─ User clique sur une suggestion
      └─ Event 'geosearch/showlocation' → JS récupère result.x, result.y, result.raw.address
         ├─ Place marqueur draggable
         ├─ Remplit hidden : place-latitude, place-longitude, place-adresse
         └─ Remplit champs : place-street, place-postal, place-locality, place-country

4. User déplace le marqueur (drag)
   └─ Event 'dragend' → fetch POST /widgets/geocode-reverse/ {lat, lng}
   └─ Endpoint Django : reverse_geocode() → cache Redis check → Nominatim si miss → JSON
   └─ JS : remplit hidden + champs (mêmes règles que 3.)

5. User clique "Continuer"
   └─ POST /onboard/place/ avec :
      - place_latitude, place_longitude, place_adresse (du widget)
      - street_address, postal_code, address_locality, address_country (du widget, auto-remplis)
   └─ OnboardPlaceSerializer valide
   └─ Persistance dans WaitingConfiguration (schema meta)
   └─ Redirect vers /onboard/descriptions/
```

---

## 6. Error handling

| Cas | Comportement |
|---|---|
| Nominatim DOWN (recherche live côté navigateur) | leaflet-geosearch affiche "no results found" dans son dropdown. User peut cliquer directement sur la carte → marqueur placé manuellement → fetch reverse côté serveur (qui peut aussi échouer, voir ligne suivante) |
| Nominatim DOWN (reverse côté serveur) | Endpoint log warning + renvoie `{display_name: "", address: {}}` avec status 200 (pas une erreur métier). JS : marqueur placé sur la carte, hidden lat/lng remplis, champs adresse séparés non touchés (l'utilisateur peut les compléter à la main) |
| Throttle Nominatim (429) côté serveur | Idem timeout : log + `{display_name: "", address: {}}` 200. Le throttle DRF côté endpoint (`1/s/IP`) limite déjà notre propre trafic |
| Validation form serveur (lat hors range) | Serializer rejette → 422 + re-render formulaire avec erreurs. L'utilisateur voit "Coordonnées invalides" dans le récap d'erreurs en haut |
| User submit sans avoir placé de marqueur (`required=True`) | Hidden inputs vides → `place_latitude` absent → serializer raise → 422 "Veuillez sélectionner une adresse sur la carte" |
| HTMX swap réinjecte le widget | Listener `htmx:afterSettle` détecte les containers `data-widget-initialized="false"` non encore initialisés et lance l'init |
| 2 widgets sur la même page | Préfixe `identifiant_widget` garantit l'isolation des IDs DOM et des `name=` HTTP. Le scan au DOMContentLoaded initialise chacun indépendamment |
| Connexion réseau coupée pendant un drag | `fetch` reverse rejette → `catch` log console.warn + JS garde le marqueur placé, lat/lng à jour, adresse non touchée. Pas d'alert UI bruyant |

---

## 7. Testing

### 7.1 Tests pytest (à écrire)

**NOTE structure tests** : les tests à l'échelle projet vivent dans `tests/pytest/`
(cf. `GUIDELINES.md` et `tests/TESTS_README.md`). L'exception est `onboard/tests/`
qui est app-locale (héritage de la session onboard). Les nouveaux tests pour le
widget sont projet-wide → `tests/pytest/`.

**`tests/pytest/test_widget_form_field_geo.py`** :
- `test_extraire_depuis_renvoie_dict_valide` — happy path, coords valides.
- `test_extraire_depuis_lat_hors_range_raise` — lat = 91.
- `test_extraire_depuis_lng_hors_range_raise` — lng = -181.
- `test_extraire_depuis_obligatoire_sans_coords_raise` — POST vide + `obligatoire=True`.
- `test_extraire_depuis_optionnel_sans_coords_renvoie_none` — POST vide + `obligatoire=False` → `None` ou dict avec valeurs `None`.

**`tests/pytest/test_widget_services_geocode_reverse.py`** :
- `test_reverse_geocode_happy_path` — mock `requests.get` → 200 avec `address` dict → résultat retourné.
- `test_reverse_geocode_cache_hit` — 2e appel avec mêmes coords → pas de 2e call à `requests.get`.
- `test_reverse_geocode_nominatim_down_renvoie_dict_vide` — mock raise `requests.RequestException` → `{display_name: "", address: {}}`.
- `test_reverse_geocode_locale_dans_cache_key` — `lang="fr"` et `lang="en"` n'utilisent pas la même clé cache.

**`tests/pytest/test_widget_views_geocode_reverse.py`** :
- `test_endpoint_reverse_returns_200_happy` — mock `reverse_geocode` → 200 + JSON.
- `test_endpoint_reverse_validates_body` — body sans `lat` → 400.
- `test_endpoint_reverse_lat_hors_range_returns_400` — `lat=91` → 400.
- `test_endpoint_reverse_throttle_429_after_2nd_call` — 2 calls < 1s par même IP → 2e en 429.

**`onboard/tests/test_step_place.py`** :
- Tests existants à adapter pour le nouveau format (`place_latitude` au lieu de `latitude`).
- Suppression de `test_geocode_endpoint_returns_partial_with_coords` (endpoint supprimé).

### 7.2 Tests manuels Playwright (cette session, automatisés plus tard)

Documentés dans `A TESTER et DOCUMENTER/widget_carte_adresse.md` :
1. **Search live** : `/onboard/place/` → taper "Saint-Denis Réunion" → vérifier suggestions live → clic → marqueur placé + 4 champs adresse remplis (rue/CP/ville/pays) + hidden lat/lng remplis.
2. **Drag marqueur** : drag à 50m → vérifier nouveaux lat/lng dans les hidden + champs adresse re-remplis depuis le reverse.
3. **Click direct sur carte** : pas de search préalable → click → marqueur placé + reverse → champs adresse remplis.
4. **Submit complet** : remplir avec search → "Continuer" → arrive sur step descriptions, le brouillon a bien lat/lng en DB.
5. **Resume** : revenir sur `/onboard/place/` après navigation → carte centrée sur l'adresse précédente, marqueur déjà placé.
6. **Locale** : tester avec `?lang=en` → `display_name` Nominatim en anglais (ex: "Saint-Denis, Reunion" vs "Saint-Denis, La Réunion").
7. **Réseau coupé pendant drag** : DevTools → offline → drag marker → marqueur reste placé, lat/lng à jour, console.warn loggué, pas d'alert UI.

---

## 8. Hors scope (à faire plus tard)

| Item | Pourquoi reporté |
|---|---|
| Intégration dans Event admin Unfold | Scope session. Le widget est conçu pour. Ajouter `{% include %}` dans le template Unfold de Event quand on aura le temps. |
| Intégration dans le bouton frontend "Ajouter un event" | Idem. La step 5 du wizard onboard (`05_events.html`) a aussi un sous-form events_add où on pourrait l'intégrer. |
| Refacto `onboard/services.py::geocode` (forward) → `BaseBillet/services_geocode.py` | Pas de 2e consommateur pour l'instant. À déplacer quand un autre formulaire en aura besoin. |
| Tests Playwright automatisés (vs manuels) | Bloquant prod F2 dans le followups onboard. À faire dans une session dédiée Playwright. |
| Provider custom leaflet-geosearch (passage par notre proxy) | Approche B rejetée pour l'instant. Si on a un problème de quota Nominatim côté users finaux, on bascule. |
| Captcha sur l'endpoint reverse | Pas critique : throttle DRF 1/s/IP suffit pour empêcher le scraping. À ajouter si on observe de l'abuse. |

---

## 9. Fichiers livrés (récap)

### Nouveaux
- `templates/widgets/widget_carte_adresse.html`
- `static/widgets/widget_carte_adresse.js`
- `static/widgets/widget_carte_adresse.css`
- `BaseBillet/form_fields.py` (nouveau si n'existe pas, sinon ajout `AdresseGeolocaliseeField`)
- `BaseBillet/services_geocode.py` (nouveau, fonction `reverse_geocode`)
- `BaseBillet/views_widgets.py` (nouveau, `WidgetReverseGeocodeViewSet`)
- `tests/pytest/test_widget_form_field_geo.py`
- `tests/pytest/test_widget_services_geocode_reverse.py`
- `tests/pytest/test_widget_views_geocode_reverse.py`
- `A TESTER et DOCUMENTER/widget_carte_adresse.md`

### Modifiés
- `onboard/templates/onboard/steps/03_place.html` (utilise le widget)
- `onboard/serializers.py` (`OnboardPlaceSerializer` accepte `place_latitude` etc.)
- `onboard/views.py` (mapping nouveaux noms vers persistance)
- `onboard/urls.py` (suppression URL `geocode_endpoint`)
- `BaseBillet/urls.py` (ajout route `/widgets/geocode-reverse/`)
- `onboard/tests/test_step_place.py` (adaptations + suppression test endpoint geocode)
- `CHANGELOG.md`

### Supprimés
- `onboard/templates/onboard/partials/map_widget.html`
- `onboard/templates/onboard/partials/geocode_result.html`
- `onboard/views.py::geocode` action + URL
- `onboard/tests/test_step_place.py::test_geocode_endpoint_returns_partial_with_coords`

---

## 10. Critères d'acceptation

Le livrable est considéré réussi si :
- [ ] `manage.py check` : 0 issue.
- [ ] `pytest onboard/tests/ tests/pytest/test_widget_form_field_geo.py tests/pytest/test_widget_services_geocode_reverse.py tests/pytest/test_widget_views_geocode_reverse.py` : tous les tests passent.
- [ ] Step 03_place onboard : la search live fonctionne, le drag de marqueur fait un reverse, les 4 champs adresse sont auto-remplis, le submit persiste correctement.
- [ ] Locale : `?lang=en` change la langue des `display_name` retournés par Nominatim (search ET reverse).
- [ ] Le widget peut être inclus une 2e fois sur la même page avec un `identifiant_widget` différent sans collision.
- [ ] Aucun appel `git` ne sera fait par l'assistant — le mainteneur fait tous les commits lui-même.

---

## 11. Notes pour writing-plans

- Découper en **phases courtes** (max 3 fichiers modifiés avant un test).
- Phases proposées (à affiner par le skill writing-plans) :
  1. Backend : `services_geocode.reverse_geocode` + tests.
  2. Backend : `WidgetReverseGeocodeViewSet` + URL + tests.
  3. Backend : `AdresseGeolocaliseeField` + tests.
  4. Widget : template + CSS (statique).
  5. Widget : JS init + handlers (search, dragend, scan multi-widget).
  6. Refonte onboard step 03_place : template + serializer + view + tests.
  7. Suppressions onboard (endpoint `/onboard/geocode/`, partials obsolètes, test obsolète).
  8. Doc : CHANGELOG + `A TESTER et DOCUMENTER/widget_carte_adresse.md`.
- Vérification après chaque phase : `manage.py check` + pytest ciblé.
- Vérification visuelle Chrome après phase 6 (par le mainteneur, pas l'assistant).
