"""
Tests de contenu — fonds de carte unifies MapTiler + repli dynamique OSM France HOT.
/ Content tests — unified MapTiler basemaps + dynamic OSM France HOT fallback.

LOCALISATION : tests/pytest/test_widget_carte_adresse_tiles.py
SPEC : TECH_DOC/SESSIONS/WIDGET_GEO/04-fonds-de-carte-maptiler-repli-osm.md

Toutes les cartes Leaflet du projet delegent leur fond au script commun
`static/cartes/tb_fond_de_carte.js` (fonction `tbPoserFondDeCarte`). C'est donc
CE script qui doit :
- utiliser MapTiler si une cle est configuree, sinon OSM France HOT ;
- basculer sur OSM France HOT si MapTiler renvoie des erreurs (quota epuise) ;
- ne jamais appeler CartoDB (filigrane "API KEY REQUIRED").
Les cartes, elles, doivent appeler `tbPoserFondDeCarte` et ne poser aucune
couche de tuiles a la main.
/ Every Leaflet map delegates its basemap to the shared script
`static/cartes/tb_fond_de_carte.js`. That script must use MapTiler (key) or
OSM France HOT (no key), switch to HOT when MapTiler fails (quota), and never
call CartoDB. The maps must call `tbPoserFondDeCarte` and add no tile layer
themselves.

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

CHEMIN_FOND_DE_CARTE_JS = RACINE_PROJET / "static" / "cartes" / "tb_fond_de_carte.js"
CHEMIN_WIDGET_JS = RACINE_PROJET / "static" / "widgets" / "widget_carte_adresse.js"
CHEMIN_EXPLORER_JS = RACINE_PROJET / "seo" / "static" / "seo" / "explorer.js"
DOSSIER_GABARITS_PAGES = RACINE_PROJET / "pages" / "templates" / "pages"

# `removeLayer` appele A L'INTERIEUR d'un setTimeout (P.WIDGET.5). Un simple
# "setTimeout(" ne prouverait rien.
# / `removeLayer` called INSIDE a setTimeout (P.WIDGET.5).
RETRAIT_DIFFERE = re.compile(r"setTimeout\(function \(\) \{\s*[\w.]+\.removeLayer\(")

# Les fichiers qui portent une carte Leaflet et appellent le fond commun.
# / The files that hold a Leaflet map and call the shared basemap.
FICHIERS_CARTES = [
    CHEMIN_WIDGET_JS,
    CHEMIN_EXPLORER_JS,
    DOSSIER_GABARITS_PAGES / "classic" / "partials" / "evenement_geoloc.html",
    DOSSIER_GABARITS_PAGES / "V2" / "partials" / "evenement_geoloc.html",
    DOSSIER_GABARITS_PAGES / "classic" / "partials" / "bloc_lieu.html",
    DOSSIER_GABARITS_PAGES / "faire_festival" / "partials" / "bloc_lieu.html",
    DOSSIER_GABARITS_PAGES / "V2" / "partials" / "bloc_lieu.html",
    DOSSIER_GABARITS_PAGES / "V2" / "partials" / "bloc_lieu_horizontal.html",
    DOSSIER_GABARITS_PAGES / "V2" / "vues" / "accueil.html",
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


def test_widget_js_delegue_son_fond_de_carte_au_script_commun():
    """
    Le JS du widget passe la cle au fond commun, sans CartoDB.
    / The widget JS hands the key to the shared basemap, no CartoDB.
    """
    source = CHEMIN_WIDGET_JS.read_text(encoding="utf-8")
    assert "tbPoserFondDeCarte(" in source
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


def test_le_fond_de_carte_commun_connait_maptiler_et_osm_hot():
    """
    Le script commun porte les deux fonds : MapTiler (avec cle) et OSM France
    HOT (sans cle, ou en repli).
    / The shared script holds both basemaps.
    """
    source = CHEMIN_FOND_DE_CARTE_JS.read_text(encoding="utf-8")
    assert "api.maptiler.com/maps/dataviz-v4" in source
    assert "tile.openstreetmap.fr/hot" in source


def test_le_fond_de_carte_commun_a_le_repli_dynamique_vers_osm_hot():
    """
    Le script commun bascule sur OSM France HOT quand MapTiler echoue.
    / The shared script switches to OSM France HOT when MapTiler fails.
    """
    source = CHEMIN_FOND_DE_CARTE_JS.read_text(encoding="utf-8")
    # Le seuil est vraiment compare (pas seulement cite en commentaire).
    # / The threshold is actually compared (not only quoted in a comment).
    assert ">= SEUIL_ERREURS_TUILES" in source
    assert "bascule_osm_faite" in source
    # P.WIDGET.5 : le retrait de la couche est differe, sinon un removeLayer
    # dans le handler `load` fait lever un TypeError dans Leaflet 1.9.4.
    # / P.WIDGET.5: layer removal is deferred (TypeError in `load` otherwise).
    assert RETRAIT_DIFFERE.search(source)


def test_chaque_carte_appelle_le_fond_de_carte_commun():
    """
    Chaque carte passe par `tbPoserFondDeCarte` : c'est ce qui lui donne le
    repli. Une carte qui poserait ses tuiles a la main n'aurait pas de repli.
    / Each map goes through `tbPoserFondDeCarte`, which carries the fallback.
    """
    for chemin in FICHIERS_CARTES:
        source = chemin.read_text(encoding="utf-8")
        assert "tbPoserFondDeCarte(" in source, chemin
        assert "api.maptiler.com" not in source, chemin
        assert "tile.openstreetmap.fr/hot" not in source, chemin


def test_aucune_carte_n_appelle_encore_cartocdn():
    """
    Plus aucune carte ne demande ses tuiles a CartoDB (filigrane
    "API KEY REQUIRED"). Scan limite aux fichiers nommes (un scan global
    traverserait .git / htmlcov et deviendrait faux).
    / No map calls CartoDB anymore. Scan limited to the named files.
    """
    for chemin in [CHEMIN_FOND_DE_CARTE_JS] + FICHIERS_CARTES:
        source = chemin.read_text(encoding="utf-8")
        assert "cartocdn" not in source, chemin
