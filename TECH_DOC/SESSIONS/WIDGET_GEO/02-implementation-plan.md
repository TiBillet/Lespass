# Widget de saisie d'adresse géolocalisée — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommandé) ou superpowers:executing-plans pour implémenter ce plan task-par-task. Steps utilisent checkbox (`- [ ]`) syntax pour le tracking.
>
> **REGLE GIT ABSOLUE (à mettre EN TÊTE de chaque prompt de subagent)** :
> NE JAMAIS lancer de commande git (commit, push, add, checkout, stash, reset, restore, clean, rebase, branch, worktree, tag). Le mainteneur fait TOUS les commits lui-même. Si une tâche dit "commit", OUTPUTE le message de commit suggéré dans le rapport final et STOP.

**Goal :** créer un widget Django+Leaflet+leaflet-geosearch réutilisable pour saisir une adresse géolocalisée (search live, marqueur draggable, géocodage inverse), et l'utiliser pour refondre la step 03_place du wizard onboard.

**Architecture (rappel spec)** : recherche live côté navigateur (leaflet-geosearch → Nominatim direct), géocodage inverse côté serveur via endpoint `/widgets/geocode-reverse/` avec cache Redis 24h. 4 champs adresse séparés auto-remplis depuis `result.raw.address`. Préfixe `identifiant_widget` sur tous les IDs/names pour permettre N widgets sur la même page.

**Tech Stack** : Django 4.x + DRF, Leaflet 1.9.4 + leaflet-geosearch 4.4.0 (CDN unpkg), Bootstrap 5, vanilla JS (IIFE, FALC).

**Spec source** : `TECH_DOC/SESSIONS/WIDGET_GEO/01-design-spec.md`.

---

## File Structure

| Fichier | Type | Responsabilité |
|---|---|---|
| `BaseBillet/services_geocode.py` | NOUVEAU | Fonction `reverse_geocode(lat, lng, lang)` — proxy Nominatim avec cache Redis. Réutilisable hors widget. |
| `BaseBillet/views_widgets.py` | NOUVEAU | `WidgetReverseGeocodeViewSet` — endpoint DRF `/widgets/geocode-reverse/`. |
| `BaseBillet/form_fields.py` | NOUVEAU | `AdresseGeolocaliseeField` — helper statique de validation lat/lng (consommé par les serializers existants). |
| `BaseBillet/urls.py` | MODIFIÉ | Ajoute la route `/widgets/geocode-reverse/`. |
| `templates/widgets/widget_carte_adresse.html` | NOUVEAU | Template réutilisable (container + hidden inputs + champs adresse + load CDN). |
| `static/widgets/widget_carte_adresse.js` | NOUVEAU | Init IIFE multi-widget, search/dragend handlers. |
| `static/widgets/widget_carte_adresse.css` | NOUVEAU | Surcharges minimales (cohérence palette TiBillet). |
| `tests/pytest/test_widget_services_geocode_reverse.py` | NOUVEAU | Tests `reverse_geocode` (happy / cache / down / locale). |
| `tests/pytest/test_widget_views_geocode_reverse.py` | NOUVEAU | Tests endpoint (200 / 400 / 429 throttle). |
| `tests/pytest/test_widget_form_field_geo.py` | NOUVEAU | Tests `AdresseGeolocaliseeField.extraire_depuis`. |
| `onboard/templates/onboard/steps/03_place.html` | MODIFIÉ | Utilise `{% include "widgets/widget_carte_adresse.html" %}`. |
| `onboard/serializers.py` | MODIFIÉ | `OnboardPlaceSerializer` accepte `place_latitude` / `place_longitude` / `place_adresse`. |
| `onboard/views.py` | MODIFIÉ | Mapping nouveaux noms vers persistance ; suppression action `geocode`. |
| `onboard/urls.py` | MODIFIÉ | Suppression URL `geocode_endpoint`. |
| `onboard/templates/onboard/partials/map_widget.html` | SUPPRIMÉ | Remplacé par le widget. |
| `onboard/templates/onboard/partials/geocode_result.html` | SUPPRIMÉ | Plus de swap HTMX géocodage. |
| `onboard/tests/test_step_place.py` | MODIFIÉ | Adaptation noms préfixés ; suppression `test_geocode_endpoint_returns_partial_with_coords`. |
| `CHANGELOG.md` | MODIFIÉ | Entrée widget + refonte onboard 03_place. |
| `A TESTER et DOCUMENTER/widget_carte_adresse.md` | NOUVEAU | Checklist tests manuels. |

---

## Conventions communes à toutes les tasks

**Lancement test** :
```bash
docker exec lespass_django poetry run pytest /DjangoFiles/<chemin>/<fichier>::<test> -v
```

**Vérification globale** :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

**Suite complète onboard + widget** :
```bash
docker exec lespass_django poetry run pytest /DjangoFiles/onboard/tests/ /DjangoFiles/tests/pytest/test_widget_*.py -q
```

**Style code** :
- Compliance djc stricte : ViewSet explicite (PAS ModelViewSet), Serializer DRF, commentaires bilingues FR/EN, docstring `LOCALISATION:` en début de fichier, `data-testid` sur tout élément interactif.
- FALC : noms de variables verbeux, pas d'abréviations, pas de comprehensions complexes.

---

## Task 1 — Service `reverse_geocode` côté serveur

**Files:**
- Create: `BaseBillet/services_geocode.py`
- Test: `tests/pytest/test_widget_services_geocode_reverse.py`

- [ ] **Step 1.1 — Écrire le 1er test (happy path)**

Créer `tests/pytest/test_widget_services_geocode_reverse.py` :

```python
"""
Tests pour BaseBillet/services_geocode.py::reverse_geocode.
/ Tests for BaseBillet/services_geocode.py::reverse_geocode.

LOCALISATION: tests/pytest/test_widget_services_geocode_reverse.py
"""

from unittest.mock import MagicMock, patch

import pytest

from django.core.cache import cache


@pytest.fixture(autouse=True)
def vider_cache_avant_test():
    """Garantit un cache Redis propre entre les tests pour isoler les hits."""
    cache.clear()
    yield
    cache.clear()


def test_reverse_geocode_happy_path():
    """
    Mock Nominatim renvoyant un payload valide (lat/lng + address dict).
    On verifie que `reverse_geocode` extrait `display_name` + `address`.
    / Happy path with mocked Nominatim returning a valid payload.
    """
    from BaseBillet.services_geocode import reverse_geocode

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "display_name": "10 Rue de Rivoli, 75004 Paris, France",
        "address": {
            "house_number": "10",
            "road": "Rue de Rivoli",
            "postcode": "75004",
            "city": "Paris",
            "country": "France",
        },
    }

    with patch("BaseBillet.services_geocode.requests.get", return_value=fake_response):
        result = reverse_geocode(48.8566, 2.3522, lang="fr")

    assert result["display_name"] == "10 Rue de Rivoli, 75004 Paris, France"
    assert result["address"]["postcode"] == "75004"
    assert result["address"]["country"] == "France"
```

- [ ] **Step 1.2 — Lancer le test (doit échouer : module n'existe pas)**

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_widget_services_geocode_reverse.py::test_reverse_geocode_happy_path -v
```
Attendu : `ModuleNotFoundError: No module named 'BaseBillet.services_geocode'`.

- [ ] **Step 1.3 — Créer le module avec implémentation minimale**

Créer `BaseBillet/services_geocode.py` :

```python
"""
Services de géocodage côté serveur (proxy Nominatim avec cache Redis).
/ Server-side geocoding services (Nominatim proxy with Redis cache).

LOCALISATION: BaseBillet/services_geocode.py

Mutualisable hors widget : tout formulaire ayant besoin de géocodage
serveur (forward ou reverse) peut consommer ces fonctions. La forward
existe encore dans `onboard/services.py::geocode` pour l'instant — sera
déplacée ici quand un 2e consommateur réel apparaîtra.

/ Reusable beyond the widget: any form needing server-side geocoding
(forward or reverse) can call these functions. Forward still lives in
`onboard/services.py::geocode` — to be moved here when a 2nd real
consumer appears.
"""

import hashlib
import logging

import requests

from django.core.cache import cache
from django.utils.translation import get_language

logger = logging.getLogger(__name__)


# Politique d'usage Nominatim : User-Agent identifiable, max 1 req/s par IP.
# / Nominatim usage policy: identifiable User-Agent, max 1 req/s per IP.
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_USER_AGENT = "TiBillet-Widget/1.0 (contact@tibillet.re)"
NOMINATIM_TIMEOUT = 5  # secondes / seconds
GEOCODE_CACHE_TTL = 24 * 60 * 60  # 24h en secondes / 24h in seconds


def _construire_cle_cache_reverse(latitude, longitude, lang):
    """
    Cle de cache deterministe pour le reverse geocode. On arrondit les
    coordonnees a 5 decimales (precision ~1.1m) pour augmenter le hit
    rate sur les drags successifs au meme endroit. La langue est dans
    la cle parce que Nominatim renvoie des `display_name` localises.
    / Deterministic cache key. Coords rounded to 5 decimals (~1.1m
    precision) to boost hit rate on successive drags at the same spot.
    Language is in the key because Nominatim returns localized names.
    """
    latitude_arrondie = round(latitude, 5)
    longitude_arrondie = round(longitude, 5)
    raw = f"{latitude_arrondie}:{longitude_arrondie}:{lang}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"widget:geocode-reverse:{h[:32]}"


def _resoudre_langue_utilisateur(lang_explicite=None):
    """
    Renvoie le code langue ISO 2 lettres a passer a Nominatim. Si
    `lang_explicite` est fourni on l'utilise, sinon on lit la langue
    active via `get_language()` (mise par `LocaleMiddleware`). Defaut
    "fr" si aucune langue n'est detectee.
    / Returns 2-letter ISO language code. Falls back to active Django
    language, then to "fr".
    """
    if lang_explicite:
        return lang_explicite.split("-")[0].lower()
    lang_complete = get_language() or "fr"
    return lang_complete.split("-")[0].lower()


def reverse_geocode(latitude, longitude, lang=None):
    """
    Géocodage inverse : (latitude, longitude) -> dict avec :
      - "display_name" : adresse complète formatée par Nominatim.
      - "address" : dict structuré (road, house_number, postcode, city, country, ...).

    Cache Redis 24h sur (lat arrondi 5 décimales, lng arrondi 5 décimales, lang).
    Renvoie `{"display_name": "", "address": {}}` si Nominatim KO
    (timeout, status non-200) — pas d'exception propagée.

    / Reverse geocoding. 24h Redis cache on rounded coords + lang.
    Returns empty payload on Nominatim error (no exception propagated).
    """
    langue_effective = _resoudre_langue_utilisateur(lang)
    cle_cache = _construire_cle_cache_reverse(latitude, longitude, langue_effective)

    payload_en_cache = cache.get(cle_cache)
    if payload_en_cache is not None:
        return payload_en_cache

    try:
        reponse = requests.get(
            NOMINATIM_REVERSE_URL,
            params={
                "lat": latitude,
                "lon": longitude,
                "format": "json",
                "addressdetails": 1,
                "accept-language": langue_effective,
            },
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=NOMINATIM_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning(
            "Nominatim reverse error for (%s, %s): %s",
            latitude, longitude, exc,
        )
        return {"display_name": "", "address": {}}

    if reponse.status_code != 200:
        logger.warning(
            "Nominatim reverse status %d for (%s, %s)",
            reponse.status_code, latitude, longitude,
        )
        return {"display_name": "", "address": {}}

    donnees_json = reponse.json()
    payload = {
        "display_name": donnees_json.get("display_name", ""),
        "address": donnees_json.get("address", {}) or {},
    }
    cache.set(cle_cache, payload, GEOCODE_CACHE_TTL)
    return payload
```

- [ ] **Step 1.4 — Lancer le test (doit passer)**

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_widget_services_geocode_reverse.py::test_reverse_geocode_happy_path -v
```
Attendu : `1 passed`.

- [ ] **Step 1.5 — Ajouter les 3 tests restants**

Ajouter à `tests/pytest/test_widget_services_geocode_reverse.py` :

```python
def test_reverse_geocode_cache_hit_evite_2e_appel_nominatim():
    """
    Apres un 1er appel reussi, un 2e appel avec memes coords + meme lang
    doit lire le cache Redis sans rappeler `requests.get`.
    """
    from BaseBillet.services_geocode import reverse_geocode

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "display_name": "Tour Eiffel, Paris",
        "address": {"city": "Paris"},
    }

    with patch("BaseBillet.services_geocode.requests.get", return_value=fake_response) as mock_get:
        reverse_geocode(48.8584, 2.2945, lang="fr")
        reverse_geocode(48.8584, 2.2945, lang="fr")  # 2e appel
        assert mock_get.call_count == 1, (
            "2e appel doit lire le cache, pas hitter Nominatim."
        )


def test_reverse_geocode_nominatim_down_renvoie_dict_vide():
    """
    Quand `requests.get` raise (timeout/dns/etc.), on log un warning
    et on renvoie `{display_name: "", address: {}}` (pas d'exception).
    """
    from BaseBillet.services_geocode import reverse_geocode

    with patch(
        "BaseBillet.services_geocode.requests.get",
        side_effect=requests.RequestException("simulated network down"),
    ):
        result = reverse_geocode(48.8566, 2.3522, lang="fr")

    assert result == {"display_name": "", "address": {}}


def test_reverse_geocode_locale_dans_cache_key():
    """
    Memes coords avec `lang="fr"` puis `lang="en"` doivent hitter
    Nominatim 2 fois (cles cache differentes).
    """
    from BaseBillet.services_geocode import reverse_geocode

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "display_name": "Brussels, Belgium",
        "address": {"city": "Brussels", "country": "Belgium"},
    }

    with patch("BaseBillet.services_geocode.requests.get", return_value=fake_response) as mock_get:
        reverse_geocode(50.8503, 4.3517, lang="fr")
        reverse_geocode(50.8503, 4.3517, lang="en")
        assert mock_get.call_count == 2
```

- [ ] **Step 1.6 — Lancer toute la suite du fichier**

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_widget_services_geocode_reverse.py -v
```
Attendu : `4 passed`.

- [ ] **Step 1.7 — manage.py check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```
Attendu : `System check identified no issues`.

- [ ] **Step 1.8 — Message de commit suggéré**

```
feat(widgets): add server-side reverse geocoding service

- BaseBillet/services_geocode.py: reverse_geocode() with Redis 24h cache
- Per-language cache keys (Nominatim returns localized names)
- Graceful fallback to empty payload on Nominatim error
- 4 tests covering happy path, cache hit, network error, locale isolation
```

---

## Task 2 — Endpoint DRF `/widgets/geocode-reverse/`

**Files:**
- Create: `BaseBillet/views_widgets.py`
- Modify: `BaseBillet/urls.py`
- Test: `tests/pytest/test_widget_views_geocode_reverse.py`

- [ ] **Step 2.1 — Écrire le 1er test (happy path POST)**

Créer `tests/pytest/test_widget_views_geocode_reverse.py` :

```python
"""
Tests pour l'endpoint POST /widgets/geocode-reverse/.
/ Tests for the POST /widgets/geocode-reverse/ endpoint.

LOCALISATION: tests/pytest/test_widget_views_geocode_reverse.py
"""

from unittest.mock import patch

import pytest

from django.core.cache import cache
from django.test import Client


DEV_HOST = "lespass.tibillet.localhost"


@pytest.fixture(autouse=True)
def vider_cache_avant_test():
    cache.clear()
    yield
    cache.clear()


def test_endpoint_reverse_returns_200_avec_payload_geocoded():
    """
    POST /widgets/geocode-reverse/ avec un body valide -> 200 + JSON
    contenant `display_name` et `address`.
    """
    client = Client(HTTP_HOST=DEV_HOST)

    fake_payload = {
        "display_name": "Tour Eiffel, Paris",
        "address": {"city": "Paris", "country": "France"},
    }
    with patch(
        "BaseBillet.views_widgets.reverse_geocode",
        return_value=fake_payload,
    ):
        response = client.post(
            "/widgets/geocode-reverse/",
            data={"lat": 48.8584, "lng": 2.2945},
            content_type="application/json",
        )

    assert response.status_code == 200, response.content[:300]
    data = response.json()
    assert data["display_name"] == "Tour Eiffel, Paris"
    assert data["address"]["city"] == "Paris"
```

- [ ] **Step 2.2 — Lancer le test (échoue : URL inconnue)**

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_widget_views_geocode_reverse.py::test_endpoint_reverse_returns_200_avec_payload_geocoded -v
```
Attendu : 404 ou erreur d'import.

- [ ] **Step 2.3 — Créer le ViewSet**

Créer `BaseBillet/views_widgets.py` :

```python
"""
Vues utilitaires pour les widgets réutilisables (carte adresse, etc.).
/ Utility views for reusable widgets (address map, etc.).

LOCALISATION: BaseBillet/views_widgets.py

ViewSet DRF explicite (`viewsets.ViewSet`, PAS `ModelViewSet`) — cf. djc.
Endpoint POST /widgets/geocode-reverse/ : géocodage inverse Nominatim
avec cache Redis. Consommé par `static/widgets/widget_carte_adresse.js`.
"""

import logging

from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from BaseBillet.services_geocode import reverse_geocode

logger = logging.getLogger(__name__)


# Throttle dédié au reverse geocode : on respecte la politique Nominatim
# (max 1 requête/seconde par IP). On déclare `rate` directement sur la
# classe pour ne pas dépendre de DEFAULT_THROTTLE_RATES dans settings.
# / Dedicated throttle: 1 req/s per IP per Nominatim policy.
class WidgetReverseGeocodeRateThrottle(AnonRateThrottle):
    """1 requête/seconde/IP — politique Nominatim/OpenStreetMap."""

    rate = "1/second"


class WidgetReverseGeocodeBodySerializer(serializers.Serializer):
    """
    Validation du body POST : `lat` et `lng` floats dans les ranges WGS84.
    / POST body validation: `lat` and `lng` as floats within WGS84 ranges.
    """

    lat = serializers.FloatField(min_value=-90, max_value=90, required=True)
    lng = serializers.FloatField(min_value=-180, max_value=180, required=True)


class WidgetReverseGeocodeViewSet(viewsets.ViewSet):
    """
    ViewSet pour le widget carte adresse — géocodage inverse seulement.

    POST /widgets/geocode-reverse/
    Body: {"lat": float, "lng": float}
    Response 200: {"display_name": str, "address": dict}
    Response 400: {"detail": "..."} (validation error)
    Response 429: throttled
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [WidgetReverseGeocodeRateThrottle]

    @action(detail=False, methods=["POST"], url_path="geocode-reverse")
    def geocode_reverse(self, request):
        """
        POST /widgets/geocode-reverse/ — proxy serveur vers Nominatim.
        / POST /widgets/geocode-reverse/ — server proxy to Nominatim.
        """
        serializer = WidgetReverseGeocodeBodySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        latitude = serializer.validated_data["lat"]
        longitude = serializer.validated_data["lng"]

        # `reverse_geocode` ne raise jamais — renvoie un payload vide en
        # cas d'échec. On propage tel quel (le client JS gère).
        # / `reverse_geocode` never raises — returns empty payload on
        # failure. We propagate as-is (JS client handles it).
        payload = reverse_geocode(latitude, longitude)
        return Response(payload, status=200)
```

- [ ] **Step 2.4 — Câbler l'URL**

Lire d'abord `BaseBillet/urls.py` (les URLs existantes). Ajouter en fin de `urlpatterns` (ou dans la zone API) :

```python
from rest_framework.routers import DefaultRouter

from BaseBillet.views_widgets import WidgetReverseGeocodeViewSet

# Router DRF dédié aux endpoints widgets. On préfère un router pour
# bénéficier du basename auto (URL = /widgets/<action.url_path>/).
# / Dedicated DRF router for widget endpoints (URL = /widgets/<...>/).
widgets_router = DefaultRouter()
widgets_router.register(
    r"widgets", WidgetReverseGeocodeViewSet, basename="widget-geocode",
)

urlpatterns += widgets_router.urls
```

ALTERNATIVE (plus FALC, sans DefaultRouter — pattern aligné sur `onboard/urls.py`) :

```python
from django.urls import path

from BaseBillet.views_widgets import WidgetReverseGeocodeViewSet

urlpatterns += [
    path(
        "widgets/geocode-reverse/",
        WidgetReverseGeocodeViewSet.as_view({"post": "geocode_reverse"}),
        name="widget-geocode-reverse",
    ),
]
```

**Choix : pattern explicite** (alternative ci-dessus) — cohérent avec le projet (cf. `onboard/urls.py`).

- [ ] **Step 2.5 — Lancer le 1er test (doit passer)**

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_widget_views_geocode_reverse.py::test_endpoint_reverse_returns_200_avec_payload_geocoded -v
```
Attendu : `1 passed`.

- [ ] **Step 2.6 — Ajouter les 3 tests restants**

```python
def test_endpoint_reverse_validates_body_lat_manquant():
    """Body sans `lat` -> 400 Bad Request."""
    client = Client(HTTP_HOST=DEV_HOST)
    response = client.post(
        "/widgets/geocode-reverse/",
        data={"lng": 2.2945},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "lat" in response.json()


def test_endpoint_reverse_lat_hors_range_returns_400():
    """`lat=91` (hors WGS84) -> 400 Bad Request."""
    client = Client(HTTP_HOST=DEV_HOST)
    response = client.post(
        "/widgets/geocode-reverse/",
        data={"lat": 91, "lng": 2.2945},
        content_type="application/json",
    )
    assert response.status_code == 400


def test_endpoint_reverse_throttle_429_apres_2nd_call_immediat():
    """
    2 appels consécutifs depuis la même IP < 1s -> le 2e renvoie 429
    (throttle DRF AnonRateThrottle 1/second).
    """
    cache.clear()  # reset compteur throttle (clé interne DRF)

    fake_payload = {"display_name": "X", "address": {}}
    client = Client(HTTP_HOST=DEV_HOST)

    with patch(
        "BaseBillet.views_widgets.reverse_geocode",
        return_value=fake_payload,
    ):
        first = client.post(
            "/widgets/geocode-reverse/",
            data={"lat": 48.8, "lng": 2.3},
            content_type="application/json",
        )
        second = client.post(
            "/widgets/geocode-reverse/",
            data={"lat": 48.8, "lng": 2.3},
            content_type="application/json",
        )

    assert first.status_code == 200
    assert second.status_code == 429, (
        f"Expected 429 (throttled), got {second.status_code}"
    )
```

- [ ] **Step 2.7 — Lancer toute la suite + check**

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_widget_views_geocode_reverse.py -v
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```
Attendu : `4 passed` + `0 issues`.

- [ ] **Step 2.8 — Message de commit suggéré**

```
feat(widgets): add /widgets/geocode-reverse/ endpoint

- BaseBillet/views_widgets.py: WidgetReverseGeocodeViewSet (DRF explicit)
- BaseBillet/urls.py: route /widgets/geocode-reverse/
- AnonRateThrottle 1/s/IP (Nominatim policy)
- Body validation via WidgetReverseGeocodeBodySerializer (WGS84 ranges)
- 4 tests: happy 200, validation 400 (missing lat / out-of-range), throttle 429
```

---

## Task 3 — Form field helper `AdresseGeolocaliseeField`

**Files:**
- Create: `BaseBillet/form_fields.py`
- Test: `tests/pytest/test_widget_form_field_geo.py`

- [ ] **Step 3.1 — Écrire les 5 tests d'un coup**

Créer `tests/pytest/test_widget_form_field_geo.py` :

```python
"""
Tests pour BaseBillet/form_fields.py::AdresseGeolocaliseeField.
/ Tests for AdresseGeolocaliseeField helper.

LOCALISATION: tests/pytest/test_widget_form_field_geo.py
"""

import pytest


def test_extraire_depuis_renvoie_dict_valide():
    """Coords valides -> dict {latitude, longitude, adresse}."""
    from BaseBillet.form_fields import AdresseGeolocaliseeField

    post_data = {
        "place_latitude": "48.8566",
        "place_longitude": "2.3522",
        "place_adresse": "10 Rue de Rivoli, Paris",
    }
    result = AdresseGeolocaliseeField.extraire_depuis(post_data, "place")
    assert result == {
        "latitude": 48.8566,
        "longitude": 2.3522,
        "adresse": "10 Rue de Rivoli, Paris",
    }


def test_extraire_depuis_lat_hors_range_raise():
    """`lat=91` hors range -> ValidationError."""
    from rest_framework.exceptions import ValidationError

    from BaseBillet.form_fields import AdresseGeolocaliseeField

    post_data = {"place_latitude": "91", "place_longitude": "2"}
    with pytest.raises(ValidationError):
        AdresseGeolocaliseeField.extraire_depuis(post_data, "place")


def test_extraire_depuis_lng_hors_range_raise():
    """`lng=-181` hors range -> ValidationError."""
    from rest_framework.exceptions import ValidationError

    from BaseBillet.form_fields import AdresseGeolocaliseeField

    post_data = {"place_latitude": "48", "place_longitude": "-181"}
    with pytest.raises(ValidationError):
        AdresseGeolocaliseeField.extraire_depuis(post_data, "place")


def test_extraire_depuis_obligatoire_sans_coords_raise():
    """POST vide + obligatoire=True -> ValidationError."""
    from rest_framework.exceptions import ValidationError

    from BaseBillet.form_fields import AdresseGeolocaliseeField

    with pytest.raises(ValidationError):
        AdresseGeolocaliseeField.extraire_depuis({}, "place", obligatoire=True)


def test_extraire_depuis_optionnel_sans_coords_renvoie_none():
    """POST vide + obligatoire=False -> None (ou dict avec None)."""
    from BaseBillet.form_fields import AdresseGeolocaliseeField

    result = AdresseGeolocaliseeField.extraire_depuis({}, "place", obligatoire=False)
    assert result is None
```

- [ ] **Step 3.2 — Lancer (5 tests doivent échouer : module manquant)**

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_widget_form_field_geo.py -v
```
Attendu : 5 erreurs `ModuleNotFoundError`.

- [ ] **Step 3.3 — Créer le helper**

Créer `BaseBillet/form_fields.py` :

```python
"""
Helpers de validation pour les form fields personnalisés.
/ Validation helpers for custom form fields.

LOCALISATION: BaseBillet/form_fields.py

Pour le widget carte adresse : `AdresseGeolocaliseeField` extrait et
valide les coordonnées (latitude/longitude) + l'adresse formatée
depuis un `request.POST` ou `request.data`. Les noms de champs sont
préfixés par l'`identifiant_widget` du widget (ex: `place_latitude`).

Pas un `forms.Field` Django : le projet utilise des DRF Serializers
(cf. djc skill). C'est un helper statique consommé par les serializers.

/ For the address map widget: `AdresseGeolocaliseeField` extracts and
validates lat/lng + formatted address from `request.POST` or
`request.data`. Field names are prefixed by the widget's
`identifiant_widget` (e.g. `place_latitude`). Not a Django `forms.Field`
because the project uses DRF Serializers — this is a static helper
consumed by the serializers.
"""

from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ValidationError


class AdresseGeolocaliseeField:
    """
    Helper statique. Pas d'instance — uniquement la méthode `extraire_depuis`.
    """

    LATITUDE_MIN = -90
    LATITUDE_MAX = 90
    LONGITUDE_MIN = -180
    LONGITUDE_MAX = 180

    @staticmethod
    def extraire_depuis(post_data, identifiant_widget, obligatoire=False):
        """
        Lit les 3 champs `<identifiant>_latitude/longitude/adresse` dans
        `post_data` (dict-like : `request.POST`, `request.data`, dict).

        Renvoie :
          - dict `{"latitude": float, "longitude": float, "adresse": str}` si OK.
          - `None` si tous les champs sont absents/vides ET `obligatoire=False`.
          - Lève `ValidationError` si :
              * `obligatoire=True` ET coords absentes/vides ;
              * coords présentes mais hors range WGS84 ;
              * coords présentes mais non castables en float.

        :param post_data: request.POST / request.data / dict.
        :param identifiant_widget: str — préfixe des champs (ex: "place").
        :param obligatoire: bool — True force la présence des coords.

        / Reads the 3 fields `<id>_latitude/longitude/adresse` from
        `post_data`. Returns a validated dict, or None if all empty and
        not required, or raises ValidationError on invalid coords.
        """
        cle_latitude = f"{identifiant_widget}_latitude"
        cle_longitude = f"{identifiant_widget}_longitude"
        cle_adresse = f"{identifiant_widget}_adresse"

        latitude_brute = post_data.get(cle_latitude, "").strip() if isinstance(post_data.get(cle_latitude, ""), str) else post_data.get(cle_latitude)
        longitude_brute = post_data.get(cle_longitude, "").strip() if isinstance(post_data.get(cle_longitude, ""), str) else post_data.get(cle_longitude)
        adresse_brute = post_data.get(cle_adresse, "")

        coords_absentes = (not latitude_brute) and (not longitude_brute)

        if coords_absentes:
            if obligatoire:
                raise ValidationError(_(
                    "Veuillez sélectionner une adresse sur la carte."
                ))
            return None

        # Cast en float — raise ValidationError si non castable.
        # / Cast to float — raise ValidationError if not castable.
        try:
            latitude = float(latitude_brute)
            longitude = float(longitude_brute)
        except (TypeError, ValueError):
            raise ValidationError(_("Coordonnées invalides (format)."))

        if not (AdresseGeolocaliseeField.LATITUDE_MIN
                <= latitude
                <= AdresseGeolocaliseeField.LATITUDE_MAX):
            raise ValidationError(_("Latitude hors range WGS84 (-90 à 90)."))

        if not (AdresseGeolocaliseeField.LONGITUDE_MIN
                <= longitude
                <= AdresseGeolocaliseeField.LONGITUDE_MAX):
            raise ValidationError(_("Longitude hors range WGS84 (-180 à 180)."))

        return {
            "latitude": latitude,
            "longitude": longitude,
            "adresse": adresse_brute or "",
        }
```

- [ ] **Step 3.4 — Lancer la suite (5 doivent passer)**

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_widget_form_field_geo.py -v
```
Attendu : `5 passed`.

- [ ] **Step 3.5 — manage.py check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Step 3.6 — Message de commit suggéré**

```
feat(widgets): add AdresseGeolocaliseeField helper

- BaseBillet/form_fields.py: static helper extraire_depuis()
- Validates lat/lng WGS84 ranges, returns dict or None or raises
- Compatible with DRF Serializers (project pattern, no Django Forms)
- 5 tests: happy / lat oor / lng oor / required missing / optional missing
```

---

## Task 4 — Template + CSS du widget

**Files:**
- Create: `templates/widgets/widget_carte_adresse.html`
- Create: `static/widgets/widget_carte_adresse.css`

Pas de test pytest pour cette task (rendu UI testé en Playwright manuel + via l'intégration onboard à la Task 6).

- [ ] **Step 4.1 — Créer le template**

```bash
mkdir -p /home/jonas/TiBillet/dev/Lespass/templates/widgets
mkdir -p /home/jonas/TiBillet/dev/Lespass/static/widgets
```

Créer `templates/widgets/widget_carte_adresse.html` :

```django
{% load i18n static %}
{% comment %}
LOCALISATION: templates/widgets/widget_carte_adresse.html

Widget Django réutilisable : carte Leaflet + barre de recherche
leaflet-geosearch + marqueur draggable. Géocodage inverse via
endpoint serveur /widgets/geocode-reverse/.

Variables de contexte (cf. spec section 3.1) :
  - identifiant_widget (str, OBLIGATOIRE) : préfixe IDs DOM + name HTTP.
  - latitude_initiale (float?) : pré-remplit + centre la carte.
  - longitude_initiale (float?) : idem.
  - adresse_initiale (str?) : pré-remplit la search bar.
  - hauteur_carte (str, défaut "400px") : hauteur CSS du container.
  - champs_adresse_separes (bool, défaut True) : affiche les 4 champs adresse.
  - noms_champs_separes (dict?) : override des `name=` des 4 champs adresse.
  - required (bool, défaut False) : ajoute required sur les hidden lat/lng.

/ Reusable Django widget: Leaflet map + leaflet-geosearch search bar +
draggable marker. Reverse geocoding via /widgets/geocode-reverse/.
{% endcomment %}

{# Defaults FALC pour les variables optionnelles. On les pose dans des #}
{# variables locales pour ne pas dupliquer les `default:` partout. #}
{# / FALC defaults for optional variables. #}
{% with hauteur_effective=hauteur_carte|default:"400px" %}
{% with afficher_champs=champs_adresse_separes|default_if_none:True %}
{% with name_rue=noms_champs_separes.rue|default:"street_address" %}
{% with name_cp=noms_champs_separes.code_postal|default:"postal_code" %}
{% with name_ville=noms_champs_separes.ville|default:"address_locality" %}
{% with name_pays=noms_champs_separes.pays|default:"address_country" %}

<div class="widget-carte-adresse" data-testid="widget-carte-adresse-{{ identifiant_widget }}">

    {# Container Leaflet (data-* lus par widget_carte_adresse.js au scan DOMContentLoaded). #}
    {# / Leaflet container (data-* read by JS at DOMContentLoaded scan). #}
    <div id="{{ identifiant_widget }}-container"
         class="widget-carte-adresse-map"
         data-widget-initialized="false"
         data-identifiant="{{ identifiant_widget }}"
         data-lat-initiale="{{ latitude_initiale|default_if_none:'' }}"
         data-lng-initiale="{{ longitude_initiale|default_if_none:'' }}"
         data-adresse-initiale="{{ adresse_initiale|default_if_none:''|escape }}"
         style="height: {{ hauteur_effective }};"
         data-testid="widget-carte-adresse-map-{{ identifiant_widget }}"></div>

    {# Hidden inputs : valeurs réelles soumises au formulaire parent. #}
    {# / Hidden inputs: actual values submitted by the parent form. #}
    <input type="hidden"
           id="{{ identifiant_widget }}-latitude"
           name="{{ identifiant_widget }}_latitude"
           value="{{ latitude_initiale|default_if_none:'' }}"
           {% if required %}required{% endif %}
           data-testid="widget-carte-adresse-latitude-{{ identifiant_widget }}">
    <input type="hidden"
           id="{{ identifiant_widget }}-longitude"
           name="{{ identifiant_widget }}_longitude"
           value="{{ longitude_initiale|default_if_none:'' }}"
           {% if required %}required{% endif %}
           data-testid="widget-carte-adresse-longitude-{{ identifiant_widget }}">
    <input type="hidden"
           id="{{ identifiant_widget }}-adresse"
           name="{{ identifiant_widget }}_adresse"
           value="{{ adresse_initiale|default_if_none:'' }}"
           data-testid="widget-carte-adresse-adresse-{{ identifiant_widget }}">

    {# Champs adresse séparés (auto-remplis par le JS depuis Nominatim). #}
    {# Affichés par défaut, masqués si champs_adresse_separes=False. #}
    {# / Separate address fields (auto-filled by JS from Nominatim). #}
    {% if afficher_champs %}
    <div class="widget-carte-adresse-fields mt-3">
        <div class="row g-3">
            <div class="col-12">
                <label for="{{ identifiant_widget }}-street" class="form-label">
                    {% translate "Rue et numéro" %}
                </label>
                <input type="text"
                       id="{{ identifiant_widget }}-street"
                       name="{{ name_rue }}"
                       class="form-control"
                       data-testid="widget-carte-adresse-street-{{ identifiant_widget }}">
            </div>
            <div class="col-md-4">
                <label for="{{ identifiant_widget }}-postal" class="form-label">
                    {% translate "Code postal" %}
                </label>
                <input type="text"
                       id="{{ identifiant_widget }}-postal"
                       name="{{ name_cp }}"
                       class="form-control"
                       data-testid="widget-carte-adresse-postal-{{ identifiant_widget }}">
            </div>
            <div class="col-md-8">
                <label for="{{ identifiant_widget }}-locality" class="form-label">
                    {% translate "Ville" %}
                </label>
                <input type="text"
                       id="{{ identifiant_widget }}-locality"
                       name="{{ name_ville }}"
                       class="form-control"
                       data-testid="widget-carte-adresse-locality-{{ identifiant_widget }}">
            </div>
            <div class="col-12">
                <label for="{{ identifiant_widget }}-country" class="form-label">
                    {% translate "Pays" %}
                </label>
                <input type="text"
                       id="{{ identifiant_widget }}-country"
                       name="{{ name_pays }}"
                       class="form-control"
                       value="France"
                       data-testid="widget-carte-adresse-country-{{ identifiant_widget }}">
            </div>
        </div>
    </div>
    {% endif %}
</div>

{# Assets Leaflet + leaflet-geosearch via CDN unpkg. Le navigateur dédoublonne #}
{# les <script src="..."> identiques (cas N widgets sur la même page). #}
{# / Leaflet + leaflet-geosearch via unpkg CDN. Browser dedupes identical scripts. #}
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<link rel="stylesheet" href="https://unpkg.com/leaflet-geosearch@4.4.0/dist/geosearch.css">
<link rel="stylesheet" href="{% static 'widgets/widget_carte_adresse.css' %}">

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script src="https://unpkg.com/leaflet-geosearch@4.4.0/dist/bundle.min.js"></script>
<script src="{% static 'widgets/widget_carte_adresse.js' %}" defer></script>

{% endwith %}{% endwith %}{% endwith %}{% endwith %}{% endwith %}{% endwith %}
```

- [ ] **Step 4.2 — Créer le CSS**

Créer `static/widgets/widget_carte_adresse.css` :

```css
/*
 * Widget carte adresse — surcharges minimales harmonisation TiBillet.
 * / Address map widget — minimal overrides for TiBillet harmonization.
 *
 * LOCALISATION: static/widgets/widget_carte_adresse.css
 */

.widget-carte-adresse-map {
    border-radius: 0.625rem;
    overflow: hidden;
    box-shadow:
        0 0 0 1px rgba(15, 23, 42, 0.04),
        0 1px 2px -1px rgba(15, 23, 42, 0.06),
        0 2px 4px 0 rgba(15, 23, 42, 0.04);
    /* z-index: assure que la carte reste sous les modals Bootstrap (1050+). */
    /* / z-index: keeps the map below Bootstrap modals (1050+). */
    position: relative;
    z-index: 1;
}

/* leaflet-geosearch : harmonise le style avec les form-control Bootstrap. */
/* / leaflet-geosearch: harmonize style with Bootstrap form-control. */
.leaflet-control-geosearch form input {
    border-radius: 0.5rem !important;
    border: 1px solid #cbd5e1 !important;
    padding: 0.5rem 0.75rem !important;
    font-size: 0.95rem !important;
}
.leaflet-control-geosearch form input:focus {
    border-color: #16a34a !important;
    box-shadow:
        0 0 0 1px #16a34a,
        0 0 0 4px rgba(22, 163, 74, 0.15) !important;
    outline: none !important;
}

/* Liste de suggestions : style cohérent avec la palette TiBillet. */
/* / Suggestions list: TiBillet palette consistency. */
.leaflet-control-geosearch .results {
    border-radius: 0.5rem;
    overflow: hidden;
    box-shadow:
        0 0 0 1px rgba(15, 23, 42, 0.06),
        0 4px 6px -2px rgba(15, 23, 42, 0.08),
        0 10px 15px -3px rgba(15, 23, 42, 0.05);
}
.leaflet-control-geosearch .results > * {
    padding: 0.5rem 0.75rem;
    font-size: 0.9rem;
}
.leaflet-control-geosearch .results > .active,
.leaflet-control-geosearch .results > :hover {
    background-color: rgba(22, 163, 74, 0.08);
    color: #166534;
}
```

- [ ] **Step 4.3 — Vérification visuelle (à faire par le mainteneur après Task 6)**

Pas de test automatisé à cette étape. La vérification visuelle se fait après l'intégration dans onboard step 03_place (Task 6).

- [ ] **Step 4.4 — Message de commit suggéré**

```
feat(widgets): add reusable address map widget template + CSS

- templates/widgets/widget_carte_adresse.html: container + hidden inputs
  + 4 separate address fields (auto-filled), CDN load Leaflet 1.9.4 +
  leaflet-geosearch 4.4.0
- static/widgets/widget_carte_adresse.css: TiBillet palette overrides
- 7 context vars: identifiant_widget (required), lat/lng/adresse initiale,
  hauteur_carte, champs_adresse_separes, noms_champs_separes, required
- data-testid prefixed by identifiant_widget for E2E targeting
```

---

## Task 5 — JS d'init du widget

**Files:**
- Create: `static/widgets/widget_carte_adresse.js`

Pas de test JS automatisé (vanilla, testé manuellement via Task 6 + Playwright F2 followups).

- [ ] **Step 5.1 — Écrire le JS complet**

Créer `static/widgets/widget_carte_adresse.js` :

```javascript
/**
 * Widget carte adresse — JS init.
 * / Address map widget — JS init.
 *
 * LOCALISATION : static/widgets/widget_carte_adresse.js
 *
 * Roles :
 * 1. Scanne le DOM au DOMContentLoaded pour trouver les containers
 *    `[data-widget-initialized="false"][data-identifiant]` non encore initialisés.
 * 2. Pour chaque container :
 *    - Crée la map Leaflet (CartoDB Voyager tiles).
 *    - Ajoute le GeoSearchControl (recherche live Nominatim côté navigateur).
 *    - Si lat/lng initiales, place un marqueur draggable centré dessus.
 *    - Bind les events : suggestion click + dragend.
 * 3. À chaque event : remplit les hidden inputs lat/lng/adresse + auto-remplit
 *    les 4 champs adresse séparés depuis `result.raw.address`.
 * 4. Re-scanne au `htmx:afterSettle` pour gérer les ré-injections HTMX.
 *
 * / Roles: scan DOM at DOMContentLoaded, init each widget container,
 * handle search/dragend events, fill hidden inputs + separate address
 * fields. Re-scan on htmx:afterSettle for HTMX re-injections.
 *
 * FALC : pas de framework, pas de bundler. Code lisible top-down.
 */
(function () {
    "use strict";

    // Configuration : alignée sur le serveur (politique Nominatim, route widget).
    // / Config: aligned with server-side (Nominatim policy, widget route).
    const URL_ENDPOINT_REVERSE = "/widgets/geocode-reverse/";
    const URL_TUILES_CARTODB = "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png";
    const ATTRIBUTION_TUILES = "&copy; OpenStreetMap &copy; CARTO";
    const CENTRE_FRANCE = [46.6, 2.5];
    const ZOOM_FRANCE = 5;
    const ZOOM_DETAIL = 15;
    const SOUS_DOMAINES_CARTODB = "abcd";

    /**
     * Initialise un widget pour un container DOM donné.
     * @param {HTMLElement} container - le div [data-identifiant=...].
     */
    function initialiser_widget_carte_adresse(container) {
        const identifiant = container.dataset.identifiant;
        if (!identifiant) {
            return;
        }

        // Marquage idempotent : évite de ré-initialiser un widget existant.
        // / Idempotent flag: avoid re-initializing an existing widget.
        if (container.dataset.widgetInitialized === "true") {
            return;
        }
        container.dataset.widgetInitialized = "true";

        // Récupération des inputs hidden + champs adresse séparés.
        // / Get hidden inputs + separate address fields.
        const input_latitude = document.getElementById(identifiant + "-latitude");
        const input_longitude = document.getElementById(identifiant + "-longitude");
        const input_adresse = document.getElementById(identifiant + "-adresse");
        const input_rue = document.getElementById(identifiant + "-street");
        const input_code_postal = document.getElementById(identifiant + "-postal");
        const input_ville = document.getElementById(identifiant + "-locality");
        const input_pays = document.getElementById(identifiant + "-country");

        if (!input_latitude || !input_longitude || !input_adresse) {
            // Sécurité : sans hidden inputs, le widget n'a aucun sens.
            // / Safety: without hidden inputs, the widget makes no sense.
            console.warn(
                "widget_carte_adresse: hidden inputs manquants pour",
                identifiant,
            );
            return;
        }

        // Lecture des coordonnées initiales depuis les data-* du container.
        // / Read initial coordinates from container data-*.
        const latitude_initiale = parseFloat(container.dataset.latInitiale);
        const longitude_initiale = parseFloat(container.dataset.lngInitiale);
        const a_des_coords_initiales = !isNaN(latitude_initiale)
            && !isNaN(longitude_initiale);

        // Création de la map Leaflet (centre France si pas de coords).
        // / Leaflet map creation (France center if no initial coords).
        const map = L.map(container).setView(
            a_des_coords_initiales
                ? [latitude_initiale, longitude_initiale]
                : CENTRE_FRANCE,
            a_des_coords_initiales ? ZOOM_DETAIL : ZOOM_FRANCE,
        );

        L.tileLayer(URL_TUILES_CARTODB, {
            attribution: ATTRIBUTION_TUILES,
            subdomains: SOUS_DOMAINES_CARTODB,
            maxZoom: 20,
        }).addTo(map);

        // Provider Nominatim (recherche live côté navigateur). Locale auto :
        // leaflet-geosearch lit `<html lang>` ; on force fallback "fr".
        // / Nominatim provider (browser-side live search). Locale auto:
        // leaflet-geosearch reads <html lang>; we fallback to "fr".
        const langue_html = (document.documentElement.lang || "fr").split("-")[0];
        const provider = new GeoSearch.OpenStreetMapProvider({
            params: {
                "accept-language": langue_html,
                "addressdetails": 1,
            },
        });

        const search_control = new GeoSearch.GeoSearchControl({
            provider: provider,
            style: "bar",
            showMarker: false,  // on gère notre propre marqueur draggable.
            showPopup: false,
            autoClose: true,
            keepResult: true,
            searchLabel: container.dataset.adresseInitiale
                || "Saisissez une adresse",
            notFoundMessage: "Adresse introuvable.",
        });
        map.addControl(search_control);

        // Marqueur draggable (créé seulement quand on a des coords valides).
        // / Draggable marker (created only when valid coords are available).
        let marqueur = null;

        function placer_marqueur_et_remplir_champs(latitude, longitude, adresse_complete, parties_adresse) {
            const lat_lng = L.latLng(latitude, longitude);

            if (marqueur === null) {
                marqueur = L.marker(lat_lng, { draggable: true }).addTo(map);
                marqueur.on("dragend", function (evenement_drag) {
                    recuperer_coordonnees_apres_deplacement_du_marqueur(evenement_drag);
                });
            } else {
                marqueur.setLatLng(lat_lng);
            }

            input_latitude.value = latitude.toFixed(6);
            input_longitude.value = longitude.toFixed(6);
            if (adresse_complete) {
                input_adresse.value = adresse_complete;
            }

            // Auto-remplissage des 4 champs adresse séparés (si présents).
            // Mapping : house_number+road, postcode, city|town|village, country.
            // / Auto-fill the 4 separate address fields if present.
            if (parties_adresse) {
                if (input_rue) {
                    const numero = parties_adresse.house_number || "";
                    const rue = parties_adresse.road || "";
                    input_rue.value = (numero + " " + rue).trim();
                }
                if (input_code_postal && parties_adresse.postcode) {
                    input_code_postal.value = parties_adresse.postcode;
                }
                if (input_ville) {
                    input_ville.value = parties_adresse.city
                        || parties_adresse.town
                        || parties_adresse.village
                        || parties_adresse.municipality
                        || "";
                }
                if (input_pays && parties_adresse.country) {
                    input_pays.value = parties_adresse.country;
                }
            }
        }

        /**
         * Geocodage inverse après drag du marqueur. POST vers
         * /widgets/geocode-reverse/, met à jour les champs.
         * / Reverse geocoding after marker drag. POST to
         * /widgets/geocode-reverse/, update fields.
         */
        async function recuperer_coordonnees_apres_deplacement_du_marqueur(evenement_drag) {
            const nouvelle_position = evenement_drag.target.getLatLng();
            const latitude = nouvelle_position.lat;
            const longitude = nouvelle_position.lng;

            // Mise à jour immédiate des hidden lat/lng (UX réactive).
            // / Immediate update of hidden lat/lng (responsive UX).
            input_latitude.value = latitude.toFixed(6);
            input_longitude.value = longitude.toFixed(6);

            try {
                const reponse = await fetch(URL_ENDPOINT_REVERSE, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": _lire_token_csrf(),
                    },
                    body: JSON.stringify({ lat: latitude, lng: longitude }),
                });

                if (!reponse.ok) {
                    console.warn(
                        "widget_carte_adresse: reverse endpoint status",
                        reponse.status,
                    );
                    return;
                }

                const donnees = await reponse.json();
                placer_marqueur_et_remplir_champs(
                    latitude,
                    longitude,
                    donnees.display_name || "",
                    donnees.address || {},
                );
            } catch (erreur) {
                // Réseau coupé ou erreur fetch : on garde le marqueur placé,
                // les hidden lat/lng à jour, on log un warn discret.
                // / Network error: keep marker placed, hidden updated, warn.
                console.warn("widget_carte_adresse: reverse fetch error", erreur);
            }
        }

        /**
         * Lit le token CSRF depuis le cookie Django (nom standard `csrftoken`).
         * / Read CSRF token from Django's standard `csrftoken` cookie.
         */
        function _lire_token_csrf() {
            const cookies = document.cookie.split(";");
            for (let i = 0; i < cookies.length; i++) {
                const paire = cookies[i].trim().split("=");
                if (paire[0] === "csrftoken") {
                    return decodeURIComponent(paire[1]);
                }
            }
            return "";
        }

        // Event leaflet-geosearch : l'utilisateur a cliqué sur une suggestion.
        // / leaflet-geosearch event: user clicked a suggestion.
        map.on("geosearch/showlocation", function (evenement_suggestion) {
            const result = evenement_suggestion.location;
            // result.x = longitude, result.y = latitude (convention GeoJSON).
            // result.raw = payload Nominatim brut (avec address si addressdetails=1).
            // / result.x = lng, result.y = lat (GeoJSON). result.raw = raw Nominatim.
            placer_marqueur_et_remplir_champs(
                result.y,
                result.x,
                result.label || "",
                (result.raw && result.raw.address) || {},
            );
            map.setView([result.y, result.x], ZOOM_DETAIL);
        });

        // Click direct sur la carte (sans search) : place le marqueur + reverse.
        // / Direct map click (no search): place marker + reverse.
        map.on("click", function (evenement_click) {
            const fake_drag_event = { target: { getLatLng: () => evenement_click.latlng } };
            // On crée le marqueur si absent, puis on simule le dragend pour
            // déclencher le reverse geocode (DRY).
            // / Create marker if missing, then simulate dragend to trigger
            // reverse (DRY).
            if (marqueur === null) {
                marqueur = L.marker(evenement_click.latlng, { draggable: true }).addTo(map);
                marqueur.on("dragend", function (evt) {
                    recuperer_coordonnees_apres_deplacement_du_marqueur(evt);
                });
            } else {
                marqueur.setLatLng(evenement_click.latlng);
            }
            recuperer_coordonnees_apres_deplacement_du_marqueur(fake_drag_event);
        });

        // Si on a des coords initiales, on place le marqueur tout de suite.
        // / If initial coords exist, place the marker immediately.
        if (a_des_coords_initiales) {
            placer_marqueur_et_remplir_champs(
                latitude_initiale,
                longitude_initiale,
                container.dataset.adresseInitiale || "",
                {},  // pas d'address dict initial — on ne re-geocode pas au load.
            );
        }
    }

    /**
     * Scanne le DOM et initialise tous les widgets non encore traités.
     * / Scan DOM and initialize all non-yet-initialized widgets.
     */
    function scanner_et_initialiser_tous_les_widgets() {
        const containers = document.querySelectorAll(
            '[data-widget-initialized="false"][data-identifiant]',
        );
        containers.forEach(initialiser_widget_carte_adresse);
    }

    document.addEventListener("DOMContentLoaded", scanner_et_initialiser_tous_les_widgets);

    // HTMX : si un swap réinjecte un widget (ex: re-render 422 d'un form),
    // on relance le scan pour initialiser les nouveaux containers.
    // / HTMX: re-scan on swap to init new widgets injected by partials.
    document.body.addEventListener("htmx:afterSettle", scanner_et_initialiser_tous_les_widgets);
})();
```

- [ ] **Step 5.2 — manage.py check (vérifie pas de typo template loading)**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Step 5.3 — Message de commit suggéré**

```
feat(widgets): add address map widget JS init

- static/widgets/widget_carte_adresse.js: vanilla IIFE, multi-widget scan
- DOMContentLoaded + htmx:afterSettle scan for re-injections
- Auto-fill 4 separate address fields from Nominatim addressdetails
- Click-on-map = place marker + reverse (DRY with dragend)
- CSRF token read from Django csrftoken cookie
- Locale auto from <html lang>, fallback "fr"
```

---

## Task 6 — Refonte onboard step 03_place (template + serializer + view)

**Files:**
- Modify: `onboard/templates/onboard/steps/03_place.html`
- Modify: `onboard/serializers.py`
- Modify: `onboard/views.py`
- Modify: `onboard/tests/test_step_place.py`

- [ ] **Step 6.1 — Modifier `onboard/serializers.py::OnboardPlaceSerializer`**

Lire d'abord `onboard/serializers.py` autour de `OnboardPlaceSerializer`. Remplacer les champs `latitude` / `longitude` (ou ajouter à côté) par les noms préfixés :

```python
class OnboardPlaceSerializer(serializers.Serializer):
    """
    Step 3 — Adresse + coordonnées GPS via le widget carte adresse.
    / Step 3 — Address + GPS coords via the address map widget.

    Les champs `place_*` viennent du widget réutilisable
    `templates/widgets/widget_carte_adresse.html` (préfixe
    `identifiant_widget="place"`). Les 4 champs adresse séparés
    (street_address, postal_code, address_locality, address_country)
    gardent leurs noms historiques pour rester compatibles avec le
    modèle `WaitingConfiguration`.
    """

    # Champs adresse historiques (auto-remplis par le widget).
    # / Historical address fields (auto-filled by the widget).
    street_address = serializers.CharField(
        max_length=255, required=True, allow_blank=False,
    )
    postal_code = serializers.CharField(
        max_length=20, required=True, allow_blank=False,
    )
    address_locality = serializers.CharField(
        max_length=120, required=True, allow_blank=False,
    )
    address_country = serializers.CharField(
        max_length=80, required=True, allow_blank=False,
    )

    # Coordonnées GPS du widget (préfixe identifiant_widget="place").
    # / GPS coords from widget (identifiant_widget="place").
    place_latitude = serializers.FloatField(
        min_value=-90, max_value=90, required=True,
    )
    place_longitude = serializers.FloatField(
        min_value=-180, max_value=180, required=True,
    )
    place_adresse = serializers.CharField(
        required=False, allow_blank=True, max_length=500,
    )
```

- [ ] **Step 6.2 — Modifier `onboard/views.py::place` POST (mapping persistance)**

Lire d'abord la zone `def place(...)` POST. Remplacer la persistance pour utiliser `data["place_latitude"]` / `place_longitude` au lieu de `data["latitude"]` / `data["longitude"]` :

```python
# === POST ===
from onboard.serializers import OnboardPlaceSerializer

serializer = OnboardPlaceSerializer(data=request.data)
if not serializer.is_valid():
    initial_from_post = {
        key: request.data.get(key, "")
        for key in (
            "street_address", "postal_code", "address_locality", "address_country",
            "place_latitude", "place_longitude", "place_adresse",
        )
    }
    return render(request, "onboard/steps/03_place.html", {
        "step": "place",
        "wc": wc,
        "errors": serializer.errors,
        "initial": initial_from_post,
    }, status=422)

data = serializer.validated_data
with schema_context("meta"):
    WaitingConfiguration.objects.filter(uuid=wc.uuid).update(
        street_address=data["street_address"],
        postal_code=data["postal_code"],
        address_locality=data["address_locality"],
        address_country=data["address_country"],
        latitude=data["place_latitude"],
        longitude=data["place_longitude"],
        current_step=WaitingConfiguration.STEP_DESCRIPTIONS,
    )
return redirect("onboard-descriptions")
```

- [ ] **Step 6.3 — Réécrire `03_place.html`**

Remplacer entièrement `onboard/templates/onboard/steps/03_place.html` par :

```django
{% extends "onboard/base_wizard.html" %}
{% load i18n %}

{% comment %}
LOCALISATION: onboard/templates/onboard/steps/03_place.html

Step 3 du wizard onboarding : adresse + carte. Refondue 2026-05-15
pour utiliser le widget réutilisable `templates/widgets/widget_carte_adresse.html`
(pattern GPS avec leaflet-geosearch).

Soumet à `onboard-place` (POST). En cas d'erreur (422), la vue re-rend
ce template avec `errors` et `initial` (qui re-pré-remplit le widget
via `latitude_initiale` / `longitude_initiale` / `adresse_initiale`).

/ Step 3 of the onboarding wizard: address + map. Refactored 2026-05-15
to use the reusable widget (GPS pattern with leaflet-geosearch).
{% endcomment %}

{% block page_title %}{% translate "Créer votre espace TiBillet — Lieu" %}{% endblock %}

{% block step_content %}
<header class="mb-4">
    <p class="onboard-step-counter mb-1">{% translate "Étape 3 / 6" %}</p>
    <p class="text-muted mb-0">
        {% translate "Cherchez votre adresse dans la barre de recherche, ou cliquez directement sur la carte. Le marqueur peut être déplacé pour ajuster la position." %}
    </p>
</header>

{% if errors %}
<div class="alert alert-danger" role="alert" data-testid="onboard-place-errors">
    <strong>{% translate "Merci de corriger les erreurs ci-dessous." %}</strong>
    <ul class="mb-0 mt-1">
        {% for field, msgs in errors.items %}
        <li>
            <strong>{{ field }}</strong> :
            {% for msg in msgs %}{{ msg }}{% if not forloop.last %} / {% endif %}{% endfor %}
        </li>
        {% endfor %}
    </ul>
</div>
{% endif %}

<form method="post" action="{% url 'onboard-place' %}" novalidate
      data-testid="onboard-place-form" class="vstack gap-3">
    {% csrf_token %}

    {# Widget réutilisable carte adresse. Préfixe "place" pour les name=. #}
    {# Pré-remplissage depuis WC si on a déjà des coords (resume / 422). #}
    {# / Reusable address map widget. "place" prefix for name=. Pre-fills #}
    {# from WC if coords exist (resume / 422). #}
    {% include "widgets/widget_carte_adresse.html" with identifiant_widget="place" latitude_initiale=initial.place_latitude|default:wc.latitude longitude_initiale=initial.place_longitude|default:wc.longitude adresse_initiale=initial.place_adresse|default:wc.street_address hauteur_carte="350px" champs_adresse_separes=True required=True %}

    <div class="d-flex justify-content-between pt-2">
        <a href="{% url 'onboard-identity' %}" class="btn btn-link"
           data-testid="onboard-place-prev">
            <i class="bi bi-arrow-left me-1" aria-hidden="true"></i>
            {% translate "Précédent" %}
        </a>
        <button type="submit" class="btn btn-primary btn-lg"
                data-testid="onboard-place-submit">
            {% translate "Continuer" %}
            <i class="bi bi-arrow-right ms-1" aria-hidden="true"></i>
        </button>
    </div>
</form>
{% endblock step_content %}
```

- [ ] **Step 6.4 — Adapter `onboard/tests/test_step_place.py` (nouveaux noms POST)**

Lire d'abord les tests existants. Les tests qui font `client.post("/onboard/place/", data={"latitude": ..., "longitude": ...})` doivent passer `place_latitude` et `place_longitude`. Exemple à modifier :

```python
def test_place_post_persists_address_and_redirects(cleanup_waiting_configs):
    client = Client(HTTP_HOST=DEV_HOST)
    wc = _create_confirmed_wc(client, cleanup=cleanup_waiting_configs)

    response = client.post("/onboard/place/", data={
        "street_address": "10 Rue de Rivoli",
        "postal_code": "75004",
        "address_locality": "Paris",
        "address_country": "France",
        "place_latitude": "48.8566",        # <-- préfixé
        "place_longitude": "2.3522",        # <-- préfixé
        "place_adresse": "10 Rue de Rivoli, 75004 Paris, France",  # <-- nouveau
    })

    assert response.status_code in (302, 303)
    assert response["Location"] == "/onboard/descriptions/"

    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.street_address == "10 Rue de Rivoli"
    assert wc.latitude == 48.8566
    assert wc.longitude == 2.3522
```

(Faire l'équivalent pour tous les autres tests qui POSTent vers `/onboard/place/`.)

- [ ] **Step 6.5 — Lancer les tests onboard step_place**

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/onboard/tests/test_step_place.py -v
```
Attendu : tous les tests adaptés passent. Le test `test_geocode_endpoint_returns_partial_with_coords` reste cassé pour l'instant (sera supprimé en Task 7).

- [ ] **Step 6.6 — manage.py check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```

- [ ] **Step 6.7 — Message de commit suggéré**

```
feat(onboard): use reusable address map widget on step 03_place

- onboard/serializers.py: OnboardPlaceSerializer accepts place_latitude
  / place_longitude / place_adresse (widget naming convention)
- onboard/views.py: place POST maps prefixed names to WC.latitude/longitude
- onboard/templates/onboard/steps/03_place.html: rewritten to use
  {% include "widgets/widget_carte_adresse.html" %} (identifiant="place")
- onboard/tests/test_step_place.py: adapted POST data to prefixed names
```

---

## Task 7 — Suppressions onboard (code obsolète)

**Files:**
- Delete: `onboard/templates/onboard/partials/map_widget.html`
- Delete: `onboard/templates/onboard/partials/geocode_result.html`
- Modify: `onboard/views.py` (suppression action `geocode`)
- Modify: `onboard/urls.py` (suppression URL)
- Modify: `onboard/tests/test_step_place.py` (suppression test obsolète)

- [ ] **Step 7.1 — Supprimer les 2 partials**

```bash
rm /home/jonas/TiBillet/dev/Lespass/onboard/templates/onboard/partials/map_widget.html
rm /home/jonas/TiBillet/dev/Lespass/onboard/templates/onboard/partials/geocode_result.html
```

- [ ] **Step 7.2 — Supprimer l'action `geocode` dans `onboard/views.py`**

Lire `onboard/views.py` pour trouver le bloc `@action(detail=False, ..., url_path="geocode")` puis sa méthode (souvent `def geocode(self, request)`). Supprimer l'action ENTIÈRE (du décorateur jusqu'à la fin de la méthode, blank line incluse).

Vérifier également si `GeocodeRateThrottle` est encore utilisé ailleurs dans `views.py`. Si oui (probablement pas), le garder ; sinon, le supprimer aussi.

- [ ] **Step 7.3 — Supprimer la route URL dans `onboard/urls.py`**

Lire `onboard/urls.py`, trouver la ligne `path("geocode/", ...)` ou `path("onboard-geocode", ...)`. Supprimer.

- [ ] **Step 7.4 — Supprimer le test obsolète**

Dans `onboard/tests/test_step_place.py`, trouver et supprimer la fonction `test_geocode_endpoint_returns_partial_with_coords` ENTIÈRE. Vérifier qu'aucun autre test ne dépend de l'endpoint.

- [ ] **Step 7.5 — Lancer la suite onboard**

```bash
docker exec lespass_django poetry run pytest /DjangoFiles/onboard/tests/ -q
```
Attendu : tous les tests passent (1 test en moins par rapport au baseline).

- [ ] **Step 7.6 — manage.py check**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
```
Attendu : 0 issue.

- [ ] **Step 7.7 — Message de commit suggéré**

```
chore(onboard): remove obsolete geocode endpoint + partials

After Task 6 widget integration, server-side forward geocoding via
/onboard/geocode/ is no longer used (leaflet-geosearch queries
Nominatim directly from the browser).

- delete onboard/templates/onboard/partials/map_widget.html
- delete onboard/templates/onboard/partials/geocode_result.html
- onboard/views.py: remove geocode action + GeocodeRateThrottle (if unused)
- onboard/urls.py: remove route
- onboard/tests/test_step_place.py: remove test_geocode_endpoint_*
```

---

## Task 8 — Documentation : CHANGELOG + A TESTER

**Files:**
- Modify: `CHANGELOG.md`
- Create: `A TESTER et DOCUMENTER/widget_carte_adresse.md`

- [ ] **Step 8.1 — Ajouter entrée CHANGELOG.md**

Lire `CHANGELOG.md` en haut. Ajouter en haut (sections numérotées en ordre chronologique inverse) :

```markdown
## N. Widget de saisie d'adresse géolocalisée / Geolocated address input widget

**Quoi / What:** nouveau widget Django+Leaflet+leaflet-geosearch réutilisable
pour saisir une adresse (search live, marqueur draggable, géocodage inverse).
Refonte de la step 03_place du wizard onboard pour l'utiliser.

**Pourquoi / Why:** UX précédente (saisie en 4 champs séparés + géocodage HTMX
au change) trop friction. Pattern GPS standard (suggestions live + drag) plus
intuitif et réutilisable dans d'autres formulaires (Event admin, etc.).

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `templates/widgets/widget_carte_adresse.html` | NOUVEAU — widget réutilisable |
| `static/widgets/widget_carte_adresse.js` | NOUVEAU — init IIFE multi-widget |
| `static/widgets/widget_carte_adresse.css` | NOUVEAU — surcharges palette TiBillet |
| `BaseBillet/services_geocode.py` | NOUVEAU — `reverse_geocode()` cache Redis 24h |
| `BaseBillet/views_widgets.py` | NOUVEAU — `WidgetReverseGeocodeViewSet` |
| `BaseBillet/form_fields.py` | NOUVEAU — `AdresseGeolocaliseeField` helper |
| `BaseBillet/urls.py` | route `/widgets/geocode-reverse/` |
| `onboard/templates/onboard/steps/03_place.html` | utilise le widget |
| `onboard/serializers.py` | `OnboardPlaceSerializer` : nouveaux champs `place_*` |
| `onboard/views.py` | mapping persistance + suppression action `geocode` |
| `onboard/urls.py` | suppression route geocode |
| `onboard/templates/onboard/partials/map_widget.html` | SUPPRIMÉ |
| `onboard/templates/onboard/partials/geocode_result.html` | SUPPRIMÉ |
| `tests/pytest/test_widget_*.py` | NOUVEAUX (3 fichiers, 13 tests) |
| `onboard/tests/test_step_place.py` | adapté + suppression test endpoint geocode |

### Migration
- **Migration nécessaire / Migration required:** Non
- Pas de modification de schéma DB.

### Breaking changes
- Endpoint `POST /onboard/geocode/` supprimé. Aucun consommateur externe (uniquement utilisé en interne par l'ex-step 03_place).
```

- [ ] **Step 8.2 — Créer `A TESTER et DOCUMENTER/widget_carte_adresse.md`**

```markdown
# Widget carte adresse — Tests manuels

## Ce qui a été fait

Nouveau widget Django réutilisable pour saisir une adresse géolocalisée :
- Carte Leaflet avec barre de recherche intégrée (leaflet-geosearch).
- Suggestions live Nominatim côté navigateur (1 req/s par user, géré par la lib).
- Marqueur draggable avec géocodage inverse côté serveur (cache Redis 24h).
- 4 champs adresse séparés auto-remplis depuis le résultat Nominatim.
- Préfixe `identifiant_widget` pour permettre N widgets sur la même page.

Premier consommateur : refonte de la step 03_place du wizard onboard.

### Modifications

Cf. `CHANGELOG.md` section "Widget de saisie d'adresse géolocalisée" + spec
`TECH_DOC/SESSIONS/WIDGET_GEO/01-design-spec.md`.

## Tests à réaliser

### Préalable

```bash
# Restart byobu si tu as touché aux templatetags ou ajouté des routes URL
# (Django scanne ces ressources au démarrage, pas à chaud).

# Vérification serveur
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_widget_*.py /DjangoFiles/onboard/tests/ -q
```

### Test 1 : Search live + auto-remplissage
1. Aller sur `/onboard/identity/` puis valider avec un email pour atterrir sur `/onboard/verify/`.
2. Saisir l'OTP (ou bypass DEBUG en dev).
3. Sur `/onboard/place/` : la carte Leaflet est affichée centrée sur la France.
4. Cliquer dans la barre de recherche en haut à droite de la carte → taper "10 rue de Rivoli Paris".
5. **Attendu :** suggestions live apparaissent en dessous de la barre.
6. Cliquer sur la 1re suggestion.
7. **Attendu :** marqueur draggable placé sur la carte, carte centrée dessus, et les 4 champs adresse en dessous se remplissent automatiquement (rue, code postal, ville, pays).

### Test 2 : Drag du marqueur (reverse geocode)
1. Sur `/onboard/place/` après Test 1.
2. Drag du marqueur de ~50 mètres.
3. **Attendu :** au drop, les 4 champs adresse se mettent à jour (nouveau quartier / nouvelle rue selon Nominatim). Pas de flash visuel sur la carte.
4. Vérifier dans DevTools Network : POST `/widgets/geocode-reverse/` avec `{lat, lng}`, réponse 200 JSON avec `display_name` + `address`.

### Test 3 : Click direct sur carte (sans search)
1. Sur `/onboard/place/` page fraîche.
2. Cliquer directement sur un point de la carte (sans utiliser la search).
3. **Attendu :** marqueur placé, fetch reverse, champs adresse remplis.

### Test 4 : Submit complet
1. Sur `/onboard/place/` après une search réussie.
2. Cliquer "Continuer".
3. **Attendu :** redirect vers `/onboard/descriptions/`. En DB :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import schema_context
from MetaBillet.models import WaitingConfiguration
with schema_context('meta'):
    wc = WaitingConfiguration.objects.order_by('-id').first()
    print('lat:', wc.latitude, 'lng:', wc.longitude, 'street:', wc.street_address)
"
```

### Test 5 : Resume (coords pré-remplies)
1. Aller sur `/onboard/descriptions/` puis revenir manuellement sur `/onboard/place/`.
2. **Attendu :** carte centrée sur l'adresse précédemment saisie, marqueur déjà placé, search bar vide (pas de re-geocode au load).

### Test 6 : Locale (anglais vs français)
1. Modifier la locale Django : `?lang=en` dans l'URL OU changer le `LANGUAGE_CODE` de la session.
2. Aller sur `/onboard/place/` → search "Brussels Belgium".
3. **Attendu :** `display_name` retourné en anglais ("Brussels, Belgium").
4. Repasser en `lang=fr` → search "Bruxelles Belgique" → "Bruxelles, Belgique".

### Test 7 : Réseau coupé pendant un drag
1. DevTools → Network → throttling → Offline.
2. Drag du marqueur.
3. **Attendu :** marqueur reste placé, hidden inputs lat/lng à jour, console.warn "reverse fetch error" loggué dans DevTools, **pas d'alert UI bruyant**.

### Test 8 : Throttle serveur
1. Faire 2 drags rapprochés (< 1s).
2. **Attendu :** le 2e POST vers `/widgets/geocode-reverse/` renvoie 429 (DRF AnonRateThrottle 1/s/IP). Côté UI, marqueur reste placé, lat/lng à jour, champs non re-remplis (gracieux dégradé).

### Test 9 : N widgets sur même page (cas hypothétique futur)
Pas testable directement aujourd'hui (le wizard n'a qu'un widget). À tester quand on intègrera dans Event admin avec un 2e identifiant_widget différent. Vérifier qu'aucun ID ne collisionne.

## Compatibilité

- Pas de migration DB.
- L'endpoint `POST /onboard/geocode/` est supprimé. Vérifier que rien (frontend, mobile, scripts externes) ne l'appelait — il était utilisé uniquement par l'ex-step 03_place.
- Le widget charge Leaflet + leaflet-geosearch via CDN unpkg. En cas de coupure réseau / firewall corporate qui bloque unpkg, la carte ne s'affiche pas (dégradation côté client uniquement).
- CDN unpkg sert l'ETag → cache navigateur OK.
```

- [ ] **Step 8.3 — Message de commit suggéré**

```
docs(widgets): CHANGELOG entry + manual test checklist

- CHANGELOG.md: section "Widget de saisie d'adresse géolocalisée"
- A TESTER et DOCUMENTER/widget_carte_adresse.md: 9 manual test scenarios
```

---

## Task 9 — i18n (workflow projet)

**Files:**
- Modify: `locale/fr/LC_MESSAGES/django.po`
- Modify: `locale/en/LC_MESSAGES/django.po`

- [ ] **Step 9.1 — Extraire les nouvelles strings**

```bash
docker exec lespass_django poetry run django-admin makemessages -l fr -l en
```

- [ ] **Step 9.2 — Remplir les `msgstr` manquants**

Ouvrir `locale/fr/LC_MESSAGES/django.po` et `locale/en/LC_MESSAGES/django.po`. Trouver les nouvelles entrées (sans `msgstr` ou avec `#, fuzzy`).

Strings concernées (approx, à confirmer après makemessages) :
- "Cherchez votre adresse dans la barre de recherche, ou cliquez directement sur la carte. Le marqueur peut être déplacé pour ajuster la position."
- "Veuillez sélectionner une adresse sur la carte."
- "Coordonnées invalides (format)."
- "Latitude hors range WGS84 (-90 à 90)."
- "Longitude hors range WGS84 (-180 à 180)."
- "Rue et numéro" (déjà existant probablement)
- "Code postal" (déjà existant)
- "Ville" (déjà existant)
- "Pays" (déjà existant)

Vérifier qu'aucune entrée n'a `#, fuzzy` (artefact de `makemessages` à corriger).

- [ ] **Step 9.3 — Compiler**

```bash
docker exec lespass_django poetry run django-admin compilemessages
```

- [ ] **Step 9.4 — manage.py check + pytest final**

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_widget_*.py /DjangoFiles/onboard/tests/ -q
```

- [ ] **Step 9.5 — Message de commit suggéré**

```
i18n(widgets): translations FR/EN for address widget

- locale/fr/LC_MESSAGES/django.po: new strings + .mo compiled
- locale/en/LC_MESSAGES/django.po: idem
```

---

## Self-Review du plan

**Couverture spec** (chaque section spec → tâche correspondante) :
- Spec §3.1 (template) → Task 4 ✅
- Spec §3.2 (JS) → Task 5 ✅
- Spec §3.3 (CSS) → Task 4 ✅
- Spec §3.4 (form field) → Task 3 ✅
- Spec §3.5 (service serveur) → Task 1 ✅
- Spec §3.6 (endpoint) → Task 2 ✅
- Spec §4 (refonte onboard) → Task 6 + Task 7 ✅
- Spec §5 (data flow) → couvert implicitement par Tasks 1-6 ✅
- Spec §6 (error handling) → couvert par les tests de chaque task ✅
- Spec §7 (testing) → Tasks 1, 2, 3 (pytest), Task 8 (manuel) ✅
- Spec §8 (hors scope) → respecté (pas de Event admin, pas de refacto forward) ✅
- Spec §9 (fichiers livrés) → tous référencés dans Tasks 1-8 ✅
- Spec §10 (critères acceptation) → vérifiable après Task 9 ✅
- i18n workflow projet → Task 9 ✅

**Placeholder scan** : aucun "TBD" / "TODO". Tous les blocs de code sont complets.

**Type consistency** :
- `reverse_geocode(latitude, longitude, lang=None)` : signature cohérente Tasks 1, 2, 5 ✅
- `WidgetReverseGeocodeViewSet.geocode_reverse` : URL `/widgets/geocode-reverse/` cohérent Tasks 2, 5 ✅
- `AdresseGeolocaliseeField.extraire_depuis(post_data, identifiant_widget, obligatoire=False)` : signature cohérente Task 3 ✅
- IDs DOM : `{identifiant_widget}-latitude` / `-longitude` / `-adresse` / `-street` / `-postal` / `-locality` / `-country` / `-container` cohérents Tasks 4, 5, 6 ✅
- `name=` HTTP : `{identifiant_widget}_latitude` etc. cohérents Tasks 3, 4, 6 ✅

Aucun écart trouvé. Le plan est prêt à être exécuté.

---

## Exécution recommandée

**Subagent-Driven** (recommandé par le mainteneur dans le prompt initial) :
- 1 subagent par task, avec la règle git EN TÊTE de chaque prompt.
- Review entre les tasks.
- Modèle Sonnet pour Tasks 4, 5 (templates + JS gros mais peu de logique). Modèle Opus pour Tasks 1, 2, 3, 6 (logique métier + tests + sécurité).

**Inline Execution** : possible si le mainteneur préfère, en suivant le plan étape par étape dans la session courante.
