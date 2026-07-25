"""
Test de rendu — la carte de la fiche evenement sert Leaflet en local et delegue
son fond de carte au script commun du projet.
/ Render test — the event page map serves Leaflet locally and delegates its
basemap to the project-wide script.

LOCALISATION : tests/pytest/test_event_map_tiles.py

Deux regles que ce test protege :

1. AUCUN CDN. Le CDN unpkg et le serveur de tuiles tile.openstreetmap.org
   renvoient des 403 selon le navigateur (referer/origin). Leaflet est donc
   vendore dans `pages/static/pages/vendor/leaflet/`.
2. LE FOND DE CARTE N'EST PAS DANS CE GABARIT. Les URLs de tuiles (MapTiler
   avec cle, OpenStreetMap France « Humanitarian » sans cle) vivent dans
   `static/cartes/tb_fond_de_carte.js`, partage par toutes les cartes du
   projet. Le gabarit se contente de charger ce script et de lui passer la
   cle via `data-maptiler-key`. Chercher `api.maptiler.com` dans le HTML
   rendu echouerait donc : ce n'est pas un bug, c'est la factorisation.

/ Two rules this test protects:
1. NO CDN. unpkg and tile.openstreetmap.org return 403 depending on the
   browser, so Leaflet is vendored under `pages/static/pages/vendor/leaflet/`.
2. THE BASEMAP IS NOT IN THIS TEMPLATE. Tile URLs live in
   `static/cartes/tb_fond_de_carte.js`, shared by every map of the project.
   The template only loads that script and hands it the key through
   `data-maptiler-key`.

Test de contenu (pas de reseau, pas de navigateur, non-flaky) : on rend le
gabarit et on verifie les chaines presentes et absentes.
/ Content test (no network, no browser, non-flaky): render the template and
check which strings are present or absent.
"""

from types import SimpleNamespace

from django.template.loader import render_to_string

# Chemin du gabarit tel que resolu par le moteur de templates. Le socle
# `classic` est le filet de securite : tous les skins retombent dessus.
# / Template path as resolved by the template engine. The `classic` base is the
# safety net every skin falls back to.
GABARIT_GEOLOC = "pages/classic/partials/evenement_geoloc.html"


def _evenement_de_test():
    """
    Evenement minimal pour rendre le gabarit de geolocalisation.
    / Minimal event to render the geolocation template.

    Le gabarit ne lit que l'identifiant, le nom et l'adresse postale : un
    objet simple suffit, pas besoin de toucher la base de donnees.
    / The template only reads the id, the name and the postal address: a plain
    object is enough, no database needed.
    """
    adresse_postale = SimpleNamespace(
        latitude=45.7676,
        longitude=4.8799,
        street_address="1 rue des Tests",
        postal_code="69100",
        address_locality="Villeurbanne",
    )
    return SimpleNamespace(
        id=42,
        name="Event de test",
        postal_address=adresse_postale,
    )


def test_carte_event_charge_leaflet_en_local_et_le_fond_de_carte_commun():
    """
    Leaflet est servi depuis nos statiques et le fond de carte commun est
    charge, sans aucune trace des serveurs qui renvoient des 403.
    / Leaflet is served from our own static files and the shared basemap script
    is loaded, with no trace of the 403-returning servers.
    """
    html_rendu = render_to_string(
        GABARIT_GEOLOC,
        {"event": _evenement_de_test(), "maptiler_key": ""},
    )

    # Leaflet vendore dans l'application `pages`.
    # / Leaflet vendored inside the `pages` app.
    assert "pages/vendor/leaflet/leaflet.js" in html_rendu
    assert "pages/vendor/leaflet/leaflet.css" in html_rendu

    # Le script du fond de carte commun est charge, et le gabarit l'appelle.
    # / The shared basemap script is loaded, and the template calls it.
    assert "cartes/tb_fond_de_carte.js" in html_rendu
    assert "tbPoserFondDeCarte(" in html_rendu

    # Les sources qui renvoyaient des 403 ont disparu. On vise les URLs
    # REELLES (script CDN, gabarit d'URL de tuile), pas les commentaires du
    # gabarit qui citent l'ancien serveur pour expliquer la contrainte.
    # / The 403-returning sources are gone. We target the ACTUAL URLs (CDN
    # script, tile URL template), not the template comments that mention the
    # old server to explain the constraint.
    assert "unpkg.com" not in html_rendu
    assert "https://tile.openstreetmap.org/{z}/{x}/{y}.png" not in html_rendu


def test_carte_event_transmet_la_cle_maptiler_au_fond_de_carte_commun():
    """
    La cle MapTiler est deposee dans `data-maptiler-key` sur le conteneur de
    la carte : c'est par la que le script commun la recupere.
    / The MapTiler key lands in `data-maptiler-key` on the map container: this
    is where the shared script picks it up.
    """
    html_rendu = render_to_string(
        GABARIT_GEOLOC,
        {"event": _evenement_de_test(), "maptiler_key": "MAcleDeTest123"},
    )

    # La cle voyage par un attribut data-*, jamais par une variable globale JS.
    # / The key travels through a data-* attribute, never through a JS global.
    assert 'data-maptiler-key="MAcleDeTest123"' in html_rendu

    # Le script commun lit la cle depuis le dataset du conteneur.
    # / The shared script reads the key from the container's dataset.
    assert "mapElement.dataset.maptilerKey" in html_rendu
