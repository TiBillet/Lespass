"""
Test de rendu — la carte de la page event utilise le meme fond que la carto
federation (pas le serveur de tuiles qui renvoie des 403).
/ Render test — the event page map uses the same basemap as the federation map
(not the tile server that returns 403).

LOCALISATION : tests/pytest/test_event_map_tiles.py

Le partial reunion/views/event/partial/geoloc.html chargeait Leaflet depuis le
CDN unpkg et tapait tile.openstreetmap.org : les deux renvoient des 403 selon le
navigateur. On sert desormais Leaflet vendore et le fond OSM France HOT (ou
MapTiler si une cle est fournie), exactement comme /federation/.
/ The geoloc partial loaded Leaflet from unpkg and hit tile.openstreetmap.org;
both return 403 depending on the browser. It now serves vendored Leaflet and the
OSM France HOT basemap (or MapTiler if a key is set), just like /federation/.

Test de contenu (pas de reseau, non-flaky) : on rend le partial et on verifie
les URLs presentes/absentes.
/ Content test (no network, non-flaky): render the partial and check URLs.
"""

from types import SimpleNamespace

import pytest

from django.template.loader import render_to_string


def _fake_event():
    """Event minimal pour rendre geoloc.html. / Minimal event to render geoloc.html."""
    postal_address = SimpleNamespace(
        latitude=45.7676,
        longitude=4.8799,
        street_address="1 rue des Tests",
        postal_code="69100",
        address_locality="Villeurbanne",
    )
    return SimpleNamespace(
        id=42,
        name="Event de test",
        postal_address=postal_address,
    )


def test_carte_event_sans_cle_maptiler_utilise_osm_france_hot():
    """
    Sans cle MapTiler : fond OSM France HOT, Leaflet vendore, et AUCUNE trace des
    serveurs qui renvoient des 403 (unpkg, tile.openstreetmap.org).
    / No MapTiler key: OSM France HOT basemap, vendored Leaflet, and NO trace of
    the 403-returning servers.
    """
    html = render_to_string(
        "reunion/views/event/partial/geoloc.html",
        {"event": _fake_event(), "maptiler_key": ""},
    )

    # Le nouveau fond de carte et le Leaflet vendore sont presents.
    # / The new basemap and vendored Leaflet are present.
    assert "tile.openstreetmap.fr/hot" in html
    assert "seo/vendor/leaflet/leaflet.js" in html
    assert "seo/vendor/leaflet/leaflet.css" in html

    # Les sources qui renvoyaient des 403 ont disparu. On vise les URLs REELLES
    # (script CDN, gabarit de tuile), pas les commentaires du template qui citent
    # tile.openstreetmap.org pour expliquer le correctif.
    # / The 403-returning sources are gone. We target the ACTUAL URLs (CDN script,
    # tile URL template), not the template comments that mention the old server.
    assert "unpkg.com" not in html
    assert "https://tile.openstreetmap.org/{z}/{x}/{y}.png" not in html


def test_carte_event_avec_cle_maptiler_utilise_maptiler():
    """
    Avec une cle MapTiler : le fond MapTiler est utilise, la cle est injectee.
    / With a MapTiler key: the MapTiler basemap is used, the key is injected.
    """
    html = render_to_string(
        "reunion/views/event/partial/geoloc.html",
        {"event": _fake_event(), "maptiler_key": "MAcleDeTest123"},
    )

    assert "api.maptiler.com" in html
    assert "MAcleDeTest123" in html
