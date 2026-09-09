"""
Les couleurs des fragments d'admin passent par des jetons, pas des hex.
/ Admin fragment colours go through tokens, not raw hex codes.

LOCALISATION : tests/pytest/test_admin_couleurs_gabarits.py

CE QUE CES TESTS PROTEGENT
--------------------------
Les gabarits d'admin DOIVENT poser leurs couleurs en style inline : les
classes Tailwind personnalisees ne sont pas dans le bundle d'Unfold et
rendraient du blanc sur blanc. C'est la regle du projet
(.claude/skills/djc/SKILL.md).

Mais la meme regle autorise explicitement les VARIABLES CSS. La difference est
loin d'etre cosmetique :

  style="border: 1px solid #ddd"                      -> gris froid, fige
  style="border: 1px solid var(--tb-tableau-bordure)" -> suit la peau ET le
                                                         mode sombre

Un `var(--color-base-200)` ecrit directement ne suffirait pas : cette variable
n'est pas redefinie en mode sombre. Seuls les jetons `--tb-*` le sont
(static/css/tibillet-admin.css). C'est POUR CA qu'ils existent.
/ Raw var(--color-base-*) is not dark-mode aware; only the --tb-* tokens are.

Ce fichier verrouille les quatre codes qui representaient l'essentiel du parc
(366 occurrences sur 582 au depart), pour qu'un copier-coller ne les
reintroduise pas.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

# Les quatre codes retires, avec le jeton qui les remplace.
# / The four removed codes and their replacement token.
CODES_BANNIS = {
    "#ddd": "--tb-tableau-bordure",
    "#f0f0f0": "--tb-tableau-entete",
    "#333": "--tb-texte-fort",
    "#666": "--tb-texte-doux",
}

# Couleurs SEMANTIQUES, a laisser en dur : elles disent « succes » et
# « danger », pas « gris de bordure ». Les faire suivre la peau les rendrait
# muettes. / Semantic colours, deliberately left as-is.
CODES_AUTORISES = {"#16a34a", "#dc2626"}

RACINES = [
    "Administration/templates",
    "pages/templates",
    "QrcodeCashless/templates",
    "controlvanne/templates",
    "comptabilite/templates",
    "newsletter/templates",
]


def _gabarits():
    for racine in RACINES:
        chemin = Path(settings.BASE_DIR) / racine
        if chemin.exists():
            yield from chemin.rglob("*.html")


@pytest.mark.parametrize("code, jeton", sorted(CODES_BANNIS.items()))
def test_aucun_code_gris_en_dur_dans_un_style(code, jeton):
    """
    Le garde-fou principal : ces quatre codes ne doivent plus apparaitre dans
    un attribut `style`. Ailleurs (commentaire, donnee) ils sont sans effet.
    / These four must no longer appear inside a style attribute.
    """
    fautifs = []
    for fichier in _gabarits():
        for style in re.findall(
            r'style="([^"]*)"', fichier.read_text(encoding="utf-8")
        ):
            if code in style:
                fautifs.append(str(fichier.relative_to(settings.BASE_DIR)))
    assert not fautifs, (
        f"{code} est revenu dans un style inline. Utiliser var({jeton}), "
        f"qui suit la peau ET le mode sombre.\nFichiers : {sorted(set(fautifs))}"
    )


def test_les_jetons_sont_definis_en_clair_ET_en_sombre():
    """
    Un jeton defini seulement en clair ne vaut pas mieux qu'un hex : la
    bordure resterait claire sur fond sombre. C'est exactement le piege que
    ces jetons existent pour eviter.
    / A token defined only for light mode is no better than a hex code.
    """
    feuille = (Path(settings.BASE_DIR) / "static/css/tibillet-admin.css").read_text(
        encoding="utf-8"
    )
    bloc_sombre = re.search(r"html\.dark\s*\{(.*?)\}", feuille, re.S)
    assert bloc_sombre, "Aucun bloc html.dark redefinissant les jetons."

    for jeton in CODES_BANNIS.values():
        assert f"{jeton}:" in feuille, f"{jeton} n'est defini nulle part."
        assert jeton in bloc_sombre.group(1), (
            f"{jeton} n'est pas redefini en mode sombre : les fragments qui "
            "l'utilisent resteront clairs sur fond sombre."
        )


def test_les_couleurs_semantiques_sont_conservees():
    """
    Le risque d'un remplacement mecanique est d'en faire trop. Vert de succes
    et rouge de danger doivent rester tels quels.
    / The risk of a mechanical pass is over-reach.
    """
    trouves = set()
    for fichier in _gabarits():
        contenu = fichier.read_text(encoding="utf-8")
        trouves |= {code for code in CODES_AUTORISES if code in contenu}
    assert trouves == CODES_AUTORISES, (
        f"Couleurs semantiques disparues : {sorted(CODES_AUTORISES - trouves)}"
    )
