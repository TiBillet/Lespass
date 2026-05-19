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
    """POST vide + obligatoire=False -> None."""
    from BaseBillet.form_fields import AdresseGeolocaliseeField

    result = AdresseGeolocaliseeField.extraire_depuis({}, "place", obligatoire=False)
    assert result is None


def test_extraire_depuis_coords_non_castables_raise():
    """
    Coords presentes mais non castables en float (ex: 'abc') -> ValidationError.
    Cas reel : input HTML hidden manipule cote client, ou bug du JS qui
    ecrit du texte au lieu d'un nombre.
    / Coords present but not castable to float (e.g. 'abc') -> ValidationError.
    Real case: client-side tampering of hidden inputs, or a JS bug writing
    text instead of a number.
    """
    from rest_framework.exceptions import ValidationError

    from BaseBillet.form_fields import AdresseGeolocaliseeField

    post_data = {"place_latitude": "abc", "place_longitude": "2.3"}
    with pytest.raises(ValidationError):
        AdresseGeolocaliseeField.extraire_depuis(post_data, "place")
