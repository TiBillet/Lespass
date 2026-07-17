"""
Garde-fou : la couleur d'identite du site passe WCAG AA, en clair ET en sombre.
/ Guard: the site's identity colour passes WCAG AA, in light AND dark mode.

LOCALISATION : tests/pytest/test_marque.py

CE QUE CE TEST PROTEGE
----------------------
BaseBillet/static/commun/css/marque.css porte LA couleur du site : le socle public,
la page racine et le tunnel d'inscription la lisent tous. Changer d'identite = y
remplacer un bloc de valeurs. Ce test verifie que le bloc actif est valide.

Sans lui, changer la marque casse la lisibilite EN SILENCE : rien ne leve d'erreur,
les pages s'affichent, elles deviennent juste illisibles — et le pire est que ca ne
se voit pas forcement dans le theme ou l'on regarde.

LES DEUX PIEGES QUE CE TEST ENCODE
----------------------------------
1. UNE CHARTE N'EST PAS DE L'ENCRE. Cinq des six --kouler-* ne portent pas de texte
   (Zanana 1.92:1, Losean 3.25:1, Chouchou 3.50:1, Gris 3.95:1, Letchi 4.10:1 — il
   en faut 4.5). Une charte est faite pour un logo et pour l'impression. D'ou le
   dedoublement geste / encre.
2. LE SITE A DEUX SURFACES, et il faut calibrer sur la PIRE.
       --bs-body-bg      #ffffff (clair) / #212529 (sombre)   le corps de page
       --bs-tertiary-bg  #f6f5f1 (clair) / #2b3035 (sombre)   le pied, les alternes
   En clair la tertiary est plus SOMBRE que le corps ; en sombre elle est plus
   CLAIRE. Dans les deux cas, une encre calibree sur le seul corps de page est
   lisible la ou on la regarde et illisible dans le pied.
/ 1. A charter is a logo/print palette, not screen ink: five of six cannot carry
text. 2. The site has TWO surfaces and every ink must clear the WORST of the two.

Les valeurs sont lues DANS le CSS, jamais recopiees ici : une constante recopiee
diverge le jour ou quelqu'un edite le CSS sans toucher au test.
/ Values are read FROM the CSS, never copied here: a copied constant drifts.
"""

import re
from pathlib import Path

import pytest

CHEMIN_DU_CSS_DE_MARQUE = (
    Path(__file__).resolve().parent.parent.parent
    / "BaseBillet" / "static" / "commun" / "css" / "marque.css"
)

# Les surfaces de Bootstrap 5.3 sur lesquelles le site pose ses encres.
# / The Bootstrap 5.3 surfaces the site puts its inks on.
SURFACES_EN_MODE_CLAIR = {"--bs-body-bg": "#ffffff", "--bs-tertiary-bg": "#f6f5f1"}
SURFACES_EN_MODE_SOMBRE = {"--bs-body-bg": "#212529", "--bs-tertiary-bg": "#2b3035"}

SEUIL_TEXTE = 4.5  # WCAG AA, texte courant / body text


def _luminance_relative(couleur_hexadecimale):
    """Luminance relative WCAG 2.1. / WCAG 2.1 relative luminance."""
    composantes_lineaires = []
    for decalage in (1, 3, 5):
        composante = int(couleur_hexadecimale[decalage:decalage + 2], 16) / 255
        if composante <= 0.03928:
            composantes_lineaires.append(composante / 12.92)
        else:
            composantes_lineaires.append(((composante + 0.055) / 1.055) ** 2.4)

    rouge, vert, bleu = composantes_lineaires
    return 0.2126 * rouge + 0.7152 * vert + 0.0722 * bleu


def _rapport_de_contraste(premiere_couleur, seconde_couleur):
    """Rapport de contraste WCAG. Symetrique. / WCAG contrast ratio. Symmetric."""
    luminances = sorted(
        [_luminance_relative(premiere_couleur), _luminance_relative(seconde_couleur)],
        reverse=True,
    )
    return (luminances[0] + 0.05) / (luminances[1] + 0.05)


def _lire_le_bloc_de_marque_actif():
    """
    Extrait les valeurs du bloc de marque ACTIF (non commente) de marque.css.

    Les blocs alternatifs (Letchi, Chouchou, Piton) vivent dans des commentaires
    CSS : on les retire avant de lire, sinon on melangerait plusieurs identites.
    / The alternative blocks live inside CSS comments: they are stripped first,
    otherwise several identities would be mixed together.
    """
    source_du_css = CHEMIN_DU_CSS_DE_MARQUE.read_text(encoding="utf-8")

    # On retire tous les commentaires CSS : les blocs alternatifs sont dedans.
    # / Strip every CSS comment: the alternative blocks live in them.
    source_sans_commentaires = re.sub(r"/\*.*?\*/", "", source_du_css, flags=re.S)

    motif_du_jeton = re.compile(r"(--tb-marque[a-z-]*):\s*(#[0-9a-fA-F]{6})\s*;")

    jetons = {}
    for nom_du_jeton, valeur in motif_du_jeton.findall(source_sans_commentaires):
        jetons[nom_du_jeton] = valeur.lower()

    if not jetons:
        pytest.fail(
            f"Aucun jeton --tb-marque* actif trouve dans {CHEMIN_DU_CSS_DE_MARQUE}. "
            f"Le bloc de marque est-il entierement commente ?"
        )
    return jetons


@pytest.mark.parametrize("mode", ["clair", "sombre"])
def test_l_encre_de_marque_tient_sur_les_deux_surfaces(mode):
    """
    L'encre de marque passe 4.5:1 sur les DEUX surfaces, pas seulement le corps.
    / The brand ink clears 4.5:1 on BOTH surfaces, not just the body.
    """
    jetons = _lire_le_bloc_de_marque_actif()

    if mode == "clair":
        couleur_de_l_encre = jetons["--tb-marque-encre"]
        surfaces = SURFACES_EN_MODE_CLAIR
    else:
        couleur_de_l_encre = jetons["--tb-marque-encre-sombre"]
        surfaces = SURFACES_EN_MODE_SOMBRE

    for nom_de_la_surface, couleur_de_la_surface in surfaces.items():
        rapport_mesure = _rapport_de_contraste(couleur_de_l_encre, couleur_de_la_surface)

        assert rapport_mesure >= SEUIL_TEXTE, (
            f"[mode {mode}] l'encre de marque ({couleur_de_l_encre}) sur "
            f"{nom_de_la_surface} ({couleur_de_la_surface}) ne fait que "
            f"{rapport_mesure:.2f}:1, il faut >= {SEUIL_TEXTE}:1.\n"
            f"RAPPEL : le site a DEUX surfaces. Calibrer une encre sur --bs-body-bg "
            f"seulement la fait echouer sur --bs-tertiary-bg (le pied de page), "
            f"sans rien signaler."
        )


@pytest.mark.parametrize("mode", ["clair", "sombre"])
def test_le_contraste_tient_sur_l_aplat_de_marque(mode):
    """
    --tb-marque-contraste pose SUR --tb-marque-encre tient >= 4.5:1.
    C'est ce que fait tout .btn-primary du site. Si ca tombe, tous les boutons
    pleins deviennent illisibles — y compris celui du tunnel de paiement.
    / What every .btn-primary does. If this fails, every filled button breaks.
    """
    jetons = _lire_le_bloc_de_marque_actif()

    if mode == "clair":
        couleur_de_l_aplat = jetons["--tb-marque-encre"]
        couleur_de_l_encre = jetons["--tb-marque-contraste"]
    else:
        couleur_de_l_aplat = jetons["--tb-marque-encre-sombre"]
        couleur_de_l_encre = jetons["--tb-marque-contraste-sombre"]

    rapport_mesure = _rapport_de_contraste(couleur_de_l_encre, couleur_de_l_aplat)

    assert rapport_mesure >= SEUIL_TEXTE, (
        f"[mode {mode}] le contraste ({couleur_de_l_encre}) sur l'aplat de marque "
        f"({couleur_de_l_aplat}) ne fait que {rapport_mesure:.2f}:1, "
        f"il faut >= {SEUIL_TEXTE}:1."
    )


def test_le_bleu_bootstrap_n_est_plus_ecrit_en_dur_dans_nos_css():
    """
    Aucun de NOS fichiers CSS ne code le #0d6efd de Bootstrap en dur.

    Ce bleu n'a jamais ete choisi par personne : c'est le defaut de Bootstrap. Le
    reecrire en dur quelque part le rendrait imperméable au changement d'identite —
    ce fichier ne serait plus « le seul endroit ou on change la couleur ».
    Le CSS de Bootstrap lui-meme est evidemment exclu : c'est sa couleur.
    / None of OUR stylesheets hardcode Bootstrap's blue. It was never anyone's
    choice. Hardcoding it anywhere would make it immune to a brand change.
    """
    racine_du_depot = CHEMIN_DU_CSS_DE_MARQUE.parent.parent.parent.parent.parent

    dossiers_a_ignorer = {"www", "node_modules", ".venv", ".git", "OLD_REPO"}
    fichiers_fautifs = []

    for chemin in racine_du_depot.rglob("*.css"):
        if set(chemin.parts) & dossiers_a_ignorer:
            continue
        # Le CSS de Bootstrap porte sa propre couleur : ce n'est pas notre code.
        # / Bootstrap's own stylesheet carries its own colour: not our code.
        if "bootstrap" in chemin.name or "material" in chemin.name:
            continue

        source_brute = chemin.read_text(encoding="utf-8", errors="ignore")
        # On retire les commentaires CSS avant de chercher : citer le bleu pour
        # documenter pourquoi on s'en debarrasse n'est pas le coder en dur.
        # / Strip CSS comments first: quoting the blue to document why we drop it
        # is not hardcoding it.
        source = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), source_brute, flags=re.S)
        for occurrence in re.finditer(r"#0d6efd", source, flags=re.I):
            ligne = source[: occurrence.start()].count("\n") + 1
            contexte = source[max(0, occurrence.start() - 60):occurrence.start() + 10]
            # `var(--bs-primary, #0d6efd)` est un REPLI, pas un choix : la variable
            # est definie, donc le repli ne sert jamais. On le tolere.
            # / A fallback inside var() is never used since the variable is set.
            if "var(--bs-primary" in contexte or "var(--tb-marque" in contexte:
                continue
            fichiers_fautifs.append(f"{chemin.relative_to(racine_du_depot)}:{ligne}")

    assert not fichiers_fautifs, (
        "Le bleu par defaut de Bootstrap (#0d6efd) est ecrit EN DUR dans nos CSS. "
        "Personne ne l'a jamais choisi, et il ne suivra pas un changement d'identite.\n"
        "Le rebrancher sur var(--tb-marque-encre) ou var(--bs-primary).\n\n  "
        + "\n  ".join(fichiers_fautifs)
    )
