"""
Tests pour BaseBillet/services_geocode.py::reverse_geocode.
/ Tests for BaseBillet/services_geocode.py::reverse_geocode.

LOCALISATION: tests/pytest/test_widget_services_geocode_reverse.py
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

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


def test_reverse_geocode_nominatim_status_non_200_renvoie_dict_vide():
    """
    Quand Nominatim renvoie un status HTTP != 200 (ex: 429 rate-limit,
    503 outage), `reverse_geocode` log un warning et renvoie le payload
    vide — meme comportement gracieux que sur RequestException.
    / When Nominatim returns a non-200 HTTP status (e.g. 429 rate-limit,
    503 outage), `reverse_geocode` logs a warning and returns the empty
    payload — same graceful behavior as on RequestException.
    """
    from BaseBillet.services_geocode import reverse_geocode

    fake_response = MagicMock()
    fake_response.status_code = 429

    with patch("BaseBillet.services_geocode.requests.get", return_value=fake_response):
        result = reverse_geocode(48.8566, 2.3522, lang="fr")

    assert result == {"display_name": "", "address": {}}
