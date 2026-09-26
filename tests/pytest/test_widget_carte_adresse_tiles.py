"""
Tests de contenu — fonds de carte unifies MapTiler + repli dynamique OSM France HOT.
/ Content tests — unified MapTiler basemaps + dynamic OSM France HOT fallback.

LOCALISATION : tests/pytest/test_widget_carte_adresse_tiles.py
SPEC : TECH_DOC/SESSIONS/WIDGET_GEO/04-fonds-de-carte-maptiler-repli-osm.md

Les 4 cartes Leaflet du projet (widget adresse, page event, explorer,
infos pratiques Faire Festival) doivent :
- utiliser MapTiler si une cle est configuree, sinon OSM France HOT ;
- basculer sur OSM France HOT si MapTiler renvoie des erreurs (quota epuise) ;
- ne plus jamais appeler CartoDB (filigrane "API KEY REQUIRED").
/ The 4 Leaflet maps must use MapTiler (key) or OSM France HOT (no key), switch
to HOT when MapTiler fails (quota), and never call CartoDB again.

Pas de reseau, pas de navigateur : on rend les templates et on lit les sources.
Le comportement JS reel (bascule, synchro formulaire) est verifie a la main
via Playwright (cf. spec section 6.2).
/ No network, no browser: render templates and read sources. The real JS
behaviour is checked manually with Playwright (spec section 6.2).
"""

import re
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.test import override_settings


RACINE_PROJET = Path(settings.BASE_DIR)

CHEMIN_WIDGET_JS = RACINE_PROJET / "static" / "widgets" / "widget_carte_adresse.js"
CHEMIN_EXPLORER_JS = RACINE_PROJET / "seo" / "static" / "seo" / "explorer.js"
CHEMIN_GEOLOC_HTML = (
    RACINE_PROJET / "BaseBillet" / "templates" / "reunion" / "views"
    / "event" / "partial" / "geoloc.html"
)
CHEMIN_INFOS_PRATIQUES_HTML = (
    RACINE_PROJET / "BaseBillet" / "templates" / "faire_festival" / "views"
    / "infos_pratiques.html"
)

# `removeLayer` appele A L'INTERIEUR d'un setTimeout (P.WIDGET.5). Un simple
# "setTimeout(" ne prouverait rien : explorer.js et geoloc.html en ont d'autres.
# / `removeLayer` called INSIDE a setTimeout (P.WIDGET.5).
RETRAIT_DIFFERE = re.compile(r"setTimeout\(function \(\) \{\s*[\w.]+\.removeLayer\(")

# Les 4 fichiers qui portent une carte Leaflet.
# / The 4 files that hold a Leaflet map.
FICHIERS_CARTES = [
    CHEMIN_WIDGET_JS,
    CHEMIN_EXPLORER_JS,
    CHEMIN_GEOLOC_HTML,
    CHEMIN_INFOS_PRATIQUES_HTML,
]


def _rendre_widget():
    """Rend le widget adresse avec un contexte minimal. / Render the widget."""
    return render_to_string(
        "widgets/widget_carte_adresse.html",
        {"identifiant_widget": "place"},
    )


@override_settings(MAPTILER_KEY="MAcleDeTest123")
def test_widget_recoit_la_cle_maptiler_quand_elle_est_configuree():
    """
    Avec une cle : le conteneur du widget porte data-maptiler-key.
    / With a key: the widget container carries data-maptiler-key.
    """
    html = _rendre_widget()
    assert 'data-maptiler-key="MAcleDeTest123"' in html


@override_settings(MAPTILER_KEY="")
def test_widget_sans_cle_maptiler_a_un_attribut_vide():
    """
    Sans cle (override explicite : le .env de dev en definit une) :
    attribut vide -> le JS prend OSM France HOT.
    / No key (explicit override, dev .env sets one): empty attribute.
    """
    html = _rendre_widget()
    assert 'data-maptiler-key=""' in html


def test_widget_js_utilise_maptiler_ou_osm_hot_et_plus_cartocdn():
    """
    Le JS du widget connait les deux fonds et le repli, plus CartoDB.
    / The widget JS knows both basemaps and the fallback, no more CartoDB.
    """
    source = CHEMIN_WIDGET_JS.read_text(encoding="utf-8")
    assert "api.maptiler.com/maps/dataviz-v4" in source
    assert "tile.openstreetmap.fr/hot" in source
    assert "cartocdn" not in source


def test_widget_js_garde_les_protections_des_pieges_p_widget():
    """
    Non-regression des pieges P.WIDGET.1 a 4 (tests/PIEGES.md).
    / Non-regression for P.WIDGET.1-4 traps.
    """
    source = CHEMIN_WIDGET_JS.read_text(encoding="utf-8")
    # P.WIDGET.1 : jamais de requestSubmit, bouton loupe en type="button".
    assert "requestSubmit" not in source
    assert 'bouton_recherche.type = "button"' in source
    # P.WIDGET.2 : zoom deplace en haut a droite.
    assert 'setPosition("topright")' in source
    # P.WIDGET.4 : pas d'autocompletion Nominatim.
    assert "autoComplete: false" in source


def test_les_4_cartes_ont_le_repli_dynamique_vers_osm_hot():
    """
    Chaque carte porte le mecanisme de repli (identifiants propres au repli,
    absents avant cette spec) et l'URL OSM France HOT.
    / Each map carries the fallback mechanism and the HOT URL.
    """
    for chemin in FICHIERS_CARTES:
        source = chemin.read_text(encoding="utf-8")
        # Le seuil est vraiment compare (pas seulement cite en commentaire).
        # / The threshold is actually compared (not only quoted in a comment).
        assert ">= SEUIL_ERREURS_TUILES" in source, chemin
        assert "bascule_osm_faite" in source, chemin
        # P.WIDGET.5 : le retrait de la couche est differe, sinon un removeLayer
        # dans le handler `load` fait lever un TypeError dans Leaflet 1.9.4.
        # / P.WIDGET.5: layer removal is deferred (TypeError in `load` otherwise).
        assert RETRAIT_DIFFERE.search(source), chemin
        assert "tile.openstreetmap.fr/hot" in source, chemin
        assert "api.maptiler.com/maps/dataviz-v4" in source, chemin


def test_aucune_carte_n_appelle_encore_cartocdn():
    """
    Plus aucune carte ne demande ses tuiles a CartoDB (filigrane
    "API KEY REQUIRED"). Scan limite aux 4 fichiers nommes (un scan global
    traverserait .git / htmlcov et deviendrait faux).
    / No map calls CartoDB anymore. Scan limited to the 4 named files.
    """
    for chemin in FICHIERS_CARTES:
        source = chemin.read_text(encoding="utf-8")
        assert "cartocdn" not in source, chemin
