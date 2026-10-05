"""
tests/pytest/test_laboutik_icones.py — Icones de la caisse (Material Symbols).
/ POS icons (Material Symbols).

LOCALISATION : tests/pytest/test_laboutik_icones.py

La caisse n'utilise plus FontAwesome : elle affiche la police Material Symbols
LOCALE fournie par django-unfold, avec <span class="material-symbols-outlined">nom</span>.
Le selecteur d'icones de l'admin (ICON_POS) propose des noms Material.
Si un nom n'existe pas dans la police, la caisse afficherait le mot en toutes
lettres (« sports_bar ») au lieu du pictogramme. Ces tests l'empechent :
- chaque nom de ICON_POS existe dans la police, sans doublon ;
- chaque icone ecrite dans les gabarits et le JS de la caisse existe.
/ Every ICON_POS name and every hard-coded icon exists in the local font.

Pas de base de donnees : lecture de la police avec fontTools.
/ No database: the font is read with fontTools.

LANCEMENT / RUN :
    docker exec lespass_django poetry run pytest tests/pytest/test_laboutik_icones.py -v
"""

import os
import re

import pytest
import unfold
from django.conf import settings
from fontTools.ttLib import TTFont


CHEMIN_POLICE_LOCALE = os.path.join(
    os.path.dirname(unfold.__file__),
    "static", "unfold", "fonts", "material-symbols", "Material-Symbols-Outlined.woff2",
)

@pytest.fixture(scope="module")
def icones_de_la_police_locale():
    """
    Noms d'icones de la police : ce sont ses ligatures
    (« sports_bar » ecrit en texte devient le pictogramme).
    / Icon names of the font: its ligatures.
    """
    police = TTFont(CHEMIN_POLICE_LOCALE)
    caractere_par_glyphe = {glyphe: chr(code) for code, glyphe in police.getBestCmap().items()}
    noms_des_icones = set()
    for recherche in police["GSUB"].table.LookupList.Lookup:
        for sous_table in recherche.SubTable:
            if hasattr(sous_table, "ExtSubTable"):
                sous_table = sous_table.ExtSubTable
            if sous_table.__class__.__name__ != "LigatureSubst":
                continue
            for premier_glyphe, ligatures in sous_table.ligatures.items():
                for ligature in ligatures:
                    glyphes = [premier_glyphe] + ligature.Component
                    nom = "".join(caractere_par_glyphe.get(g, "?") for g in glyphes)
                    noms_des_icones.add(nom)
    return noms_des_icones


def test_la_police_locale_existe():
    """La police Material de django-unfold est bien installee. / The local font exists."""
    assert os.path.exists(CHEMIN_POLICE_LOCALE), CHEMIN_POLICE_LOCALE


# ------------------------------------------------------------------ #
#  Selecteur de l'admin / Admin picker
# ------------------------------------------------------------------ #

def test_chaque_icone_du_selecteur_de_l_admin_existe_dans_la_police(icones_de_la_police_locale):
    """Chaque nom propose dans l'admin (ICON_POS) existe dans la police.
    / Every name offered by the admin picker exists in the font."""
    from Administration.admin.products import ICON_POS

    absentes = sorted(nom for nom, _libelle in ICON_POS if nom not in icones_de_la_police_locale)
    assert absentes == [], f"Icones de l'admin absentes de la police : {absentes}"


def test_le_selecteur_de_l_admin_n_a_pas_de_doublon():
    """Chaque choix du selecteur a un nom distinct. / Each picker choice is distinct."""
    from Administration.admin.products import ICON_POS

    noms = [nom for nom, _libelle in ICON_POS]
    doublons = sorted({nom for nom in noms if noms.count(nom) > 1})
    assert doublons == [], f"Doublons dans ICON_POS : {doublons}"


def test_le_selecteur_de_l_admin_ne_propose_plus_de_fontawesome():
    """Aucun nom « fa-... » dans ICON_POS. Attention : « fastfood » et « favorite »
    sont des noms Material, d'ou le test sur « fa- » avec le tiret.
    / No "fa-..." name in ICON_POS (Material names like "fastfood" are fine)."""
    from Administration.admin.products import ICON_POS

    noms_fontawesome = [nom for nom, _libelle in ICON_POS if nom.startswith("fa-")]
    assert noms_fontawesome == []


# ------------------------------------------------------------------ #
#  Gabarits et JS de la caisse / POS templates and JS
# ------------------------------------------------------------------ #

def test_les_icones_ecrites_dans_la_caisse_existent_dans_la_police(icones_de_la_police_locale):
    """Les icones ecrites en dur dans les gabarits et le JS de la caisse existent.
    / Icons hard-coded in POS templates and JS exist in the font."""
    dossier_laboutik = os.path.join(settings.BASE_DIR, "laboutik")
    motif = re.compile(r'class="material-symbols-outlined[^"]*"[^>]*>\s*([a-z0-9_]+)\s*<')
    absentes = set()
    for sous_dossier in ("templates", os.path.join("static", "js")):
        for racine, _dossiers, fichiers in os.walk(os.path.join(dossier_laboutik, sous_dossier)):
            for nom_du_fichier in fichiers:
                if not nom_du_fichier.endswith((".html", ".js")) or nom_du_fichier.endswith(".min.js"):
                    continue
                with open(os.path.join(racine, nom_du_fichier), encoding="utf-8") as fichier:
                    for nom_icone in motif.findall(fichier.read()):
                        if nom_icone not in icones_de_la_police_locale:
                            absentes.add(f"{nom_du_fichier}: {nom_icone}")
    assert absentes == set(), f"Icones absentes : {sorted(absentes)}"


def test_la_caisse_n_utilise_plus_fontawesome():
    """Plus aucune classe FontAwesome dans les gabarits et le JS de la caisse.
    / No FontAwesome class left in POS templates and JS."""
    dossier_laboutik = os.path.join(settings.BASE_DIR, "laboutik")
    motif = re.compile(r'class="[^"]*\bfa[srb]?\b[^"]*"')
    fichiers_avec_fontawesome = []
    for sous_dossier in ("templates", os.path.join("static", "js")):
        for racine, _dossiers, fichiers in os.walk(os.path.join(dossier_laboutik, sous_dossier)):
            for nom_du_fichier in fichiers:
                if not nom_du_fichier.endswith((".html", ".js")):
                    continue
                with open(os.path.join(racine, nom_du_fichier), encoding="utf-8") as fichier:
                    if motif.search(fichier.read()):
                        fichiers_avec_fontawesome.append(nom_du_fichier)
    assert fichiers_avec_fontawesome == []


def test_le_selecteur_coche_une_icone_hors_liste_au_lieu_de_l_effacer():
    """Une icone absente de ICON_POS est rendue comme option cochee.
    / An icon missing from ICON_POS is rendered as a checked option."""
    from Administration.admin.products import IconPickerWidget

    html = IconPickerWidget().render("icon_pos", "icone_inconnue_de_la_liste")

    assert 'data-testid="icon-picker-valeur-hors-liste"' in html
    assert 'value="icone_inconnue_de_la_liste"' in html


def test_le_selecteur_n_ajoute_pas_d_option_pour_une_icone_de_la_liste():
    from Administration.admin.products import IconPickerWidget

    html = IconPickerWidget().render("icon_pos", "sports_bar")

    assert 'data-testid="icon-picker-valeur-hors-liste"' not in html
