"""
Garde-fou : les couples de couleurs du socle passent WCAG AA, en clair ET en sombre.
/ Guard: the socle's colour pairs pass WCAG AA, in light AND dark mode.

LOCALISATION : tests/pytest/test_socle_contrastes.py

CE QUE CE TEST PROTÈGE
----------------------
Le socle garantit deux choses aux skins (CONTRAT-DE-SKIN + CHANTIER-10) :
  1. `--tb-accent-contraste` posé SUR `--tb-accent` tient >= 4.5:1.
  2. Le socle ne pose JAMAIS de texte sur `--tb-accent-vif` — donc ce jeton n'a
     besoin que de 3:1, en tant que geste (filets, bordures, pastilles).
Si quelqu'un change une valeur par défaut sans vérifier, ces garanties tombent en
silence : rien ne lève d'erreur, le site s'affiche, il devient juste illisible.

LE PIÈGE : LE SITE A DEUX SURFACES
---------------------------------
    --bs-body-bg      #212529 (sombre) / #ffffff (clair)   le corps de page
    --bs-tertiary-bg  #2b3035 (sombre) / #f6f5f1 (clair)   le pied et les surfaces alternées
En sombre la tertiary est plus CLAIRE que le corps ; en clair elle est plus SOMBRE.
Dans les deux cas, une encre calibrée sur le seul corps de page est lisible là où on
la regarde et illisible dans le pied, sans que rien ne le signale — pas d'erreur,
pas de log, la page s'affiche.
D'où la règle testée ici : **toute encre doit passer le seuil sur la PIRE des deux
surfaces**, jamais sur le corps de page seul.
/ In dark mode the tertiary surface is LIGHTER than the body; in light mode it is
DARKER. Either way, an ink calibrated on the body alone is legible where you look at
it and illegible in the footer, silently. Every ink must clear the threshold on the
WORST of the two surfaces.

Les valeurs ci-dessous sont les DÉFAUTS du socle, lus dans tb-blocs.css. Un skin qui
pose ses propres --skin-* est responsable de ses propres contrastes : le socle ne
peut pas les vérifier ici puisqu'il ne les connaît pas.
/ The values below are the socle's DEFAULTS. A skin setting its own --skin-* tokens
is responsible for its own contrasts.
"""

import re
from pathlib import Path

import pytest

CHEMIN_DU_CSS_DU_SOCLE = (
    Path(__file__).resolve().parent.parent.parent / "pages" / "static" / "pages" / "css" / "tb-blocs.css"
)

# Les surfaces de Bootstrap 5.3 sur lesquelles le socle pose ses encres.
# / The Bootstrap 5.3 surfaces the socle puts its inks on.
SURFACES_EN_MODE_CLAIR = {"--bs-body-bg": "#ffffff", "--bs-tertiary-bg": "#f6f5f1"}
SURFACES_EN_MODE_SOMBRE = {"--bs-body-bg": "#212529", "--bs-tertiary-bg": "#2b3035"}

SEUIL_TEXTE = 4.5  # WCAG AA, texte courant / body text
SEUIL_GESTE = 3.0  # WCAG AA, éléments non textuels / non-text elements


def _luminance_relative(couleur_hexadecimale):
    """
    Luminance relative WCAG 2.1 d'une couleur hexadécimale.
    / WCAG 2.1 relative luminance of a hex colour.
    """
    valeur = couleur_hexadecimale.lstrip("#")
    composantes = [int(valeur[i : i + 2], 16) / 255 for i in (0, 2, 4)]

    composantes_linearisees = []
    for composante in composantes:
        if composante <= 0.03928:
            composantes_linearisees.append(composante / 12.92)
        else:
            composantes_linearisees.append(((composante + 0.055) / 1.055) ** 2.4)

    rouge, vert, bleu = composantes_linearisees
    return 0.2126 * rouge + 0.7152 * vert + 0.0722 * bleu


def _rapport_de_contraste(premiere_couleur, seconde_couleur):
    """
    Rapport de contraste WCAG entre deux couleurs. Symétrique.
    / WCAG contrast ratio between two colours. Symmetric.
    """
    luminances = sorted(
        [_luminance_relative(premiere_couleur), _luminance_relative(seconde_couleur)],
        reverse=True,
    )
    return (luminances[0] + 0.05) / (luminances[1] + 0.05)


def _lire_les_defauts_du_socle():
    """
    Extrait les valeurs par défaut des jetons depuis tb-blocs.css.

    On lit le CSS plutôt que de recopier les valeurs ici : une constante recopiée
    diverge du jour où quelqu'un change le CSS sans toucher au test — et le test
    continuerait de valider une couleur qui n'existe plus.
    / We read the CSS rather than hardcoding the values: a copied constant drifts
    the day someone edits the CSS without touching the test, and the test would keep
    validating a colour that no longer exists.
    """
    source_du_css = CHEMIN_DU_CSS_DU_SOCLE.read_text(encoding="utf-8")

    # Motif : --tb-xxx: var(--skin-xxx, #rrggbb);
    motif_du_jeton = re.compile(r"(--tb-[a-z-]+):\s*var\(--skin-[a-z-]+,\s*(#[0-9a-fA-F]{6})\)")

    jetons_du_mode_clair = {}
    jetons_du_mode_sombre = {}

    # Le bloc sombre commence à [data-bs-theme="dark"] et court jusqu'à sa fermeture.
    # / The dark block starts at [data-bs-theme="dark"] and runs to its closing brace.
    debut_du_bloc_sombre = source_du_css.index('[data-bs-theme="dark"]')
    fin_du_bloc_sombre = source_du_css.index("}", debut_du_bloc_sombre)

    source_avant_le_bloc_sombre = source_du_css[:debut_du_bloc_sombre]
    source_du_bloc_sombre = source_du_css[debut_du_bloc_sombre:fin_du_bloc_sombre]

    for nom_du_jeton, valeur in motif_du_jeton.findall(source_avant_le_bloc_sombre):
        jetons_du_mode_clair[nom_du_jeton] = valeur.lower()

    # Le mode sombre hérite du clair, puis surcharge ce qu'il redéclare.
    # / Dark inherits from light, then overrides what it redeclares.
    jetons_du_mode_sombre.update(jetons_du_mode_clair)
    for nom_du_jeton, valeur in motif_du_jeton.findall(source_du_bloc_sombre):
        jetons_du_mode_sombre[nom_du_jeton] = valeur.lower()

    return jetons_du_mode_clair, jetons_du_mode_sombre


@pytest.mark.parametrize("mode", ["clair", "sombre"])
def test_l_encre_de_contraste_tient_sur_l_aplat_d_accent(mode):
    """
    GARANTIE 1 : --tb-accent-contraste posé SUR --tb-accent tient >= 4.5:1.
    C'est ce que fait .tb-bloc__bouton--plein. Si ça tombe, tous les boutons
    pleins du site deviennent illisibles.
    / GUARANTEE 1: --tb-accent-contraste on --tb-accent holds >= 4.5:1.
    """
    jetons_clairs, jetons_sombres = _lire_les_defauts_du_socle()
    jetons = jetons_clairs if mode == "clair" else jetons_sombres

    couleur_de_l_aplat = jetons["--tb-accent"]
    couleur_de_l_encre = jetons["--tb-accent-contraste"]

    rapport_mesure = _rapport_de_contraste(couleur_de_l_encre, couleur_de_l_aplat)

    assert rapport_mesure >= SEUIL_TEXTE, (
        f"[mode {mode}] --tb-accent-contraste ({couleur_de_l_encre}) sur --tb-accent "
        f"({couleur_de_l_aplat}) ne fait que {rapport_mesure:.2f}:1, il faut >= {SEUIL_TEXTE}:1. "
        f"Le socle GARANTIT ce couple aux skins : tous les boutons pleins en dépendent."
    )


@pytest.mark.parametrize("mode", ["clair", "sombre"])
@pytest.mark.parametrize("nom_du_jeton_encre", ["--tb-accent", "--tb-texte-doux"])
def test_les_encres_tiennent_sur_les_deux_surfaces(mode, nom_du_jeton_encre):
    """
    LE PIÈGE : une encre doit passer sur les DEUX surfaces, pas seulement le corps.

    Le pied de page utilise --bs-tertiary-bg, pas --bs-body-bg. En sombre, la
    tertiary est plus CLAIRE que le corps : une encre qui passe sur le corps peut
    échouer sur le pied. Sans ce test, le pied devient illisible en silence.
    / An ink must clear BOTH surfaces. The footer uses --bs-tertiary-bg, which in
    dark mode is LIGHTER than the body: an ink passing on the body can fail there.
    """
    jetons_clairs, jetons_sombres = _lire_les_defauts_du_socle()

    if mode == "clair":
        jetons, surfaces = jetons_clairs, SURFACES_EN_MODE_CLAIR
    else:
        jetons, surfaces = jetons_sombres, SURFACES_EN_MODE_SOMBRE

    couleur_de_l_encre = jetons[nom_du_jeton_encre]

    for nom_de_la_surface, couleur_de_la_surface in surfaces.items():
        rapport_mesure = _rapport_de_contraste(couleur_de_l_encre, couleur_de_la_surface)

        assert rapport_mesure >= SEUIL_TEXTE, (
            f"[mode {mode}] {nom_du_jeton_encre} ({couleur_de_l_encre}) sur "
            f"{nom_de_la_surface} ({couleur_de_la_surface}) ne fait que "
            f"{rapport_mesure:.2f}:1, il faut >= {SEUIL_TEXTE}:1.\n"
            f"RAPPEL : le site a DEUX surfaces. Calibrer une encre sur --bs-body-bg "
            f"seulement la fait échouer sur --bs-tertiary-bg (le pied de page) sans "
            f"rien signaler."
        )


@pytest.mark.parametrize("mode", ["clair", "sombre"])
def test_le_geste_vif_tient_son_seuil_de_geste(mode):
    """
    GARANTIE 2 : --tb-accent-vif est un GESTE, pas une encre. Le socle n'y pose
    jamais de texte, donc 3:1 suffit — mais il doit rester VISIBLE sur le papier,
    sinon les filets et les pastilles disparaissent.
    / GUARANTEE 2: --tb-accent-vif is a GESTURE, never text. 3:1 suffices, but it
    must stay visible on paper or the rules and dots vanish.
    """
    jetons_clairs, jetons_sombres = _lire_les_defauts_du_socle()

    if mode == "clair":
        jetons, surfaces = jetons_clairs, SURFACES_EN_MODE_CLAIR
    else:
        jetons, surfaces = jetons_sombres, SURFACES_EN_MODE_SOMBRE

    couleur_du_geste = jetons["--tb-accent-vif"]

    for nom_de_la_surface, couleur_de_la_surface in surfaces.items():
        rapport_mesure = _rapport_de_contraste(couleur_du_geste, couleur_de_la_surface)

        assert rapport_mesure >= SEUIL_GESTE, (
            f"[mode {mode}] --tb-accent-vif ({couleur_du_geste}) sur "
            f"{nom_de_la_surface} ({couleur_de_la_surface}) ne fait que "
            f"{rapport_mesure:.2f}:1, il faut >= {SEUIL_GESTE}:1 pour un geste."
        )
