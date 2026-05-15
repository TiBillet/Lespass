"""
Tests pour l'endpoint POST /widgets/geocode-reverse/.
/ Tests for the POST /widgets/geocode-reverse/ endpoint.

LOCALISATION: tests/pytest/test_widget_views_geocode_reverse.py

On utilise `APIRequestFactory` (DRF) plutôt que `Client` pour appeler le
ViewSet directement, sans passer par le middleware `django_tenants` qui
tenterait une lookup DB sur le domaine.
/ We use DRF's `APIRequestFactory` to call the ViewSet directly, bypassing
the `django_tenants` middleware that would attempt a DB domain lookup.
"""

import json
from unittest.mock import patch

import pytest

from django.core.cache import cache
from rest_framework.renderers import JSONRenderer
from rest_framework.test import APIRequestFactory

from BaseBillet.views_widgets import WidgetReverseGeocodeViewSet


@pytest.fixture(autouse=True)
def vider_cache_avant_test():
    """Cache Redis propre entre les tests — isole les compteurs de throttle."""
    cache.clear()
    yield
    cache.clear()


def _post_geocode_reverse(data, remote_addr="127.0.0.1"):
    """
    Helper : construit une request POST vers geocode_reverse et retourne la
    Response DRF. On utilise `REMOTE_ADDR` pour simuler une IP cliente.
    / Helper: build a POST request to geocode_reverse and return the DRF
    Response. We set REMOTE_ADDR to simulate a client IP.
    """
    factory = APIRequestFactory()
    request = factory.post(
        "/widgets/geocode-reverse/",
        data=json.dumps(data),
        content_type="application/json",
        REMOTE_ADDR=remote_addr,
    )
    view = WidgetReverseGeocodeViewSet.as_view({"post": "geocode_reverse"})
    response = view(request)
    # DRF lazy-renders le contenu — forcer le rendu pour accéder à .data.
    # / DRF lazy-renders content — force rendering to access .data.
    response.accepted_renderer = response.accepted_renderer or JSONRenderer()
    response.accepted_media_type = "application/json"
    response.renderer_context = {}
    response.render()
    return response


def test_endpoint_reverse_returns_200_avec_payload_geocoded():
    """
    POST avec un body valide -> 200 + JSON contenant `display_name` et `address`.
    / POST with valid body -> 200 + JSON containing `display_name` and `address`.
    """
    fake_payload = {
        "display_name": "Tour Eiffel, Paris",
        "address": {"city": "Paris", "country": "France"},
    }
    with patch(
        "BaseBillet.views_widgets.reverse_geocode",
        return_value=fake_payload,
    ):
        response = _post_geocode_reverse({"lat": 48.8584, "lng": 2.2945})

    assert response.status_code == 200, response.content[:300]
    data = json.loads(response.content)
    assert data["display_name"] == "Tour Eiffel, Paris"
    assert data["address"]["city"] == "Paris"


def test_endpoint_reverse_validates_body_lat_manquant():
    """Body sans `lat` -> 400 Bad Request avec clé `lat` dans l'erreur."""
    response = _post_geocode_reverse({"lng": 2.2945})
    assert response.status_code == 400
    erreurs = json.loads(response.content)
    assert "lat" in erreurs


def test_endpoint_reverse_lat_hors_range_returns_400():
    """`lat=91` (hors WGS84 [-90, 90]) -> 400 Bad Request."""
    response = _post_geocode_reverse({"lat": 91, "lng": 2.2945})
    assert response.status_code == 400


def test_endpoint_reverse_throttle_429_apres_2nd_call_immediat():
    """
    2 appels consécutifs depuis la même IP < 1s -> le 2e renvoie 429.
    Throttle DRF : WidgetReverseGeocodeRateThrottle (rate = "1/second").
    / 2 consecutive calls from same IP < 1s -> 2nd returns 429.
    DRF throttle: WidgetReverseGeocodeRateThrottle (rate = "1/second").
    """
    cache.clear()  # reset compteur throttle (clé interne DRF basée sur cache)

    fake_payload = {"display_name": "X", "address": {}}

    with patch(
        "BaseBillet.views_widgets.reverse_geocode",
        return_value=fake_payload,
    ):
        # Même IP pour les deux appels — DRF rate-limit par REMOTE_ADDR.
        # / Same IP for both calls — DRF rate-limits by REMOTE_ADDR.
        premier = _post_geocode_reverse({"lat": 48.8, "lng": 2.3}, remote_addr="10.0.0.1")
        deuxieme = _post_geocode_reverse({"lat": 48.8, "lng": 2.3}, remote_addr="10.0.0.1")

    assert premier.status_code == 200
    assert deuxieme.status_code == 429, (
        f"Expected 429 (throttled), got {deuxieme.status_code}"
    )
