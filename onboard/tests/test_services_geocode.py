"""
Tests du proxy Nominatim (service geocode).
/ Tests for the Nominatim geocode proxy service.

LOCALISATION: onboard/tests/test_services_geocode.py

NOTE : on utilise `django.test.TestCase` (pas `SimpleTestCase`) car le service
`geocode` lit/ecrit dans le cache Django (`from django.core.cache import cache`).
`TestCase` fournit l'isolation et l'acces aux backends configures par Django.
On evite `pytest` car `pytest-django` n'est pas installe sur cette branche ;
les tests s'executent via `manage.py test onboard.tests.test_services_geocode`.

Tous les tests mockent `requests.get` : AUCUN appel reseau reel n'est fait.
/ NOTE: we use `django.test.TestCase` (not `SimpleTestCase`) because the
`geocode` service reads/writes Django's cache. `TestCase` gives proper
isolation and access to the configured cache backends. We avoid `pytest`
because `pytest-django` isn't installed on this branch ; tests run via
`manage.py test onboard.tests.test_services_geocode`.

All tests mock `requests.get`: NO real network call is made.
"""

from unittest.mock import patch, MagicMock

import requests

from django.core.cache import cache
from django.test import TestCase


class GeocodeServiceTests(TestCase):
    """
    Tests unitaires du helper `geocode(query)`.
    / Unit tests for the `geocode(query)` helper.
    """

    def setUp(self):
        # On vide le cache avant chaque test pour eviter les fuites
        # de cle entre runs (LocMemCache est process-wide en test).
        # / Clear cache before each test to avoid key leaks across runs
        # (LocMemCache is process-wide in tests).
        cache.clear()

    def test_geocode_returns_lat_lng_on_success(self):
        """
        Un appel Nominatim qui renvoie un resultat est mappe vers un dict
        {latitude, longitude, display_name} avec les coordonnees parsees en
        float (Nominatim renvoie des strings).
        / A successful Nominatim call is mapped to a dict
        {latitude, longitude, display_name} with coordinates parsed as
        floats (Nominatim returns strings).
        """
        from onboard.services import geocode

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = [
            {"lat": "48.8566", "lon": "2.3522", "display_name": "Paris, France"}
        ]
        with patch("onboard.services.requests.get", return_value=fake_response):
            result = geocode("Tour Eiffel, Paris")

        self.assertEqual(
            result,
            {
                "latitude": 48.8566,
                "longitude": 2.3522,
                "display_name": "Paris, France",
            },
        )

    def test_geocode_returns_none_when_no_result(self):
        """
        Si Nominatim renvoie une liste vide (adresse introuvable), geocode
        renvoie None.
        / If Nominatim returns an empty list (address not found), geocode
        returns None.
        """
        from onboard.services import geocode

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = []
        with patch("onboard.services.requests.get", return_value=fake_response):
            result = geocode("Adresse inexistante xyz123")

        self.assertIsNone(result)

    def test_geocode_returns_none_on_timeout(self):
        """
        En cas de timeout reseau (ou toute autre RequestException), geocode
        renvoie None sans propager l'exception.
        / On network timeout (or any other RequestException), geocode
        returns None without propagating the exception.
        """
        from onboard.services import geocode

        with patch("onboard.services.requests.get", side_effect=requests.Timeout):
            result = geocode("Paris")

        self.assertIsNone(result)

    def test_geocode_uses_cache_on_second_call(self):
        """
        Deux appels successifs avec la meme query ne tapent Nominatim qu'une
        seule fois : le second appel est servi depuis le cache Redis (24h).
        / Two successive calls with the same query hit Nominatim only once :
        the second call is served from the Redis cache (24h).
        """
        from onboard.services import geocode

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = [
            {"lat": "1.0", "lon": "2.0", "display_name": "X"}
        ]
        with patch("onboard.services.requests.get", return_value=fake_response) as mock_get:
            geocode("Cache me")
            geocode("Cache me")  # 2e appel : doit etre servi depuis le cache.

            # Le mock n'a ete appele qu'1 fois grace au cache.
            # / The mock was called only once thanks to the cache.
            self.assertEqual(mock_get.call_count, 1)

    def test_geocode_returns_none_on_empty_query(self):
        """
        Les queries vides ou trop courtes (< 3 chars apres strip) sont
        rejetees immediatement, sans appel Nominatim.
        / Empty or too-short queries (< 3 chars after strip) are rejected
        immediately, with no Nominatim call.
        """
        from onboard.services import geocode

        with patch("onboard.services.requests.get") as mock_get:
            # Cas typiques rejetes : None, "", "  ", "ab".
            # / Typical rejected cases: None, "", "  ", "ab".
            self.assertIsNone(geocode(None))
            self.assertIsNone(geocode(""))
            self.assertIsNone(geocode("   "))
            self.assertIsNone(geocode("ab"))

            # Aucun appel reseau ne doit avoir eu lieu.
            # / No network call should have happened.
            self.assertEqual(mock_get.call_count, 0)
