"""
Garde-fou : aucun commentaire Django `{# ... #}` ne doit courir sur plusieurs lignes.
/ Guard: no Django `{# ... #}` comment may span multiple lines.

LOCALISATION : tests/pytest/test_gabarits_commentaires.py

LE PIÈGE
--------
Le lexer de gabarits de Django découpe le source avec :

    tag_re = re.compile(r'({%.*?%}|{{.*?}}|{#.*?#})')

Ce motif est compilé SANS `re.DOTALL`. En Python, `.` ne matche alors pas le saut
de ligne. Conséquence : un `{# ... #}` qui court sur plusieurs lignes n'est JAMAIS
reconnu comme un commentaire — il traverse le lexer et part tel quel dans le HTML
envoyé au navigateur.

`{# #}` est MONO-LIGNE. Pour plusieurs lignes : `{% comment %}…{% endcomment %}`.

Rien ne lève d'erreur : ni au `manage.py check`, ni au rendu, ni dans les logs. Le
commentaire s'affiche simplement en texte sur la page. Un commentaire posé dans un
`{% block extra_meta %}` fuit même dans le `<head>`, à côté du JSON-LD.

Le piège se représente à chaque commentaire un peu long — c'est-à-dire tout le
temps, vu que le projet impose des commentaires FALC bilingues FR/EN. D'où ce test.
/ The trap recurs with every longish comment — i.e. constantly, since the project
mandates verbose bilingual comments. Hence this test.

DEUX SÉVÉRITÉS, ET C'EST CE QUI TROMPE
--------------------------------------
Un `{# … #}` multi-lignes est TOUJOURS un bug, mais il ne se voit pas toujours :

- Gabarit SANS `{% extends %}` (un partial inclus) : tout le source est rendu,
  donc le faux commentaire **s'affiche en clair sur le site**.
- Gabarit AVEC `{% extends %}` : seul ce qui est dans un `{% block %}` est rendu.
  Un faux commentaire posé hors bloc est **jeté en silence** — il ne se voit pas,
  et il fuira le jour où quelqu'un déplacera le commentaire dans un bloc.

Ce test ne fait pas la différence : les deux sont fautifs, seul le délai avant
l'incident change.
/ A multi-line `{# … #}` is ALWAYS a bug, but it does not always show: without
`{% extends %}` it renders as visible text; with it, a comment outside any block
is silently discarded — and will leak the day someone moves it inside a block.

PORTÉE
------
Cadré sur `pages/`. Un passage sur tout le dépôt trouve 8 cas de plus — laboutik 2,
onboard 2, BaseBillet 2, Administration 1, crowds 1 — plus 7 dans OLD_REPO (code
mort). Aucun ne fuit aujourd'hui : leur commentaire est hors de tout `{% block %}`
dans un gabarit qui `{% extends %}`, donc jeté en silence. Ils fuiront le jour où
quelqu'un les déplacera dans un bloc. Élargir ce test à `RACINE_DU_DEPOT` suppose de
les corriger d'abord : c'est une décision mainteneur.
/ Scoped to `pages/`. A repo-wide pass finds 8 more (plus 7 in dead code). None leak
today: their comment sits outside any `{% block %}` in a template that `{% extends %}`,
so it is silently discarded — and will leak the day someone moves it into a block.
Widening the scope means fixing those first — a maintainer decision.
"""

import re
from pathlib import Path

import pytest

# Racine du dépôt : ce fichier est dans tests/pytest/.
# / Repo root: this file lives in tests/pytest/.
RACINE_DU_DEPOT = Path(__file__).resolve().parent.parent.parent

# Un `{#`, puis n'importe quoi qui ne referme pas, puis un saut de ligne avant le `#}`.
# / A `{#`, anything that does not close it, then a newline before the `#}`.
COMMENTAIRE_MULTILIGNE = re.compile(r"\{#(?:(?!#\}).)*?\n(?:(?!#\}).)*?#\}", re.S)


def _tous_les_gabarits():
    """
    Renvoie les gabarits HTML de l'app `pages` (socle + skins).
    / Returns the `pages` app HTML templates (base + skins).
    """
    dossiers_a_ignorer = {".git", "node_modules", "__pycache__", "www", ".venv"}

    racine_scannee = RACINE_DU_DEPOT / "pages"

    gabarits_trouves = []
    for chemin in racine_scannee.rglob("*.html"):
        # On saute tout gabarit situé sous un dossier ignoré.
        # / Skip any template sitting under an ignored folder.
        parties_du_chemin = set(chemin.parts)
        if parties_du_chemin & dossiers_a_ignorer:
            continue
        gabarits_trouves.append(chemin)

    return sorted(gabarits_trouves)


def test_aucun_commentaire_django_ne_court_sur_plusieurs_lignes():
    """
    Un `{# ... #}` multi-lignes s'affiche en clair sur le site. Il n'en existe aucun.
    / A multi-line `{# ... #}` renders as visible text. There must be none.
    """
    gabarits_fautifs = []

    for chemin_du_gabarit in _tous_les_gabarits():
        source_du_gabarit = chemin_du_gabarit.read_text(encoding="utf-8")

        for occurrence in COMMENTAIRE_MULTILIGNE.finditer(source_du_gabarit):
            # Numéro de ligne du `{#` fautif, pour que le message soit cliquable.
            # / Line number of the offending `{#`, so the message is clickable.
            numero_de_ligne = source_du_gabarit[: occurrence.start()].count("\n") + 1
            chemin_relatif = chemin_du_gabarit.relative_to(RACINE_DU_DEPOT)
            premiers_mots = occurrence.group(0)[:70].replace("\n", " ")

            gabarits_fautifs.append(f"{chemin_relatif}:{numero_de_ligne} -> {premiers_mots}...")

    if gabarits_fautifs:
        liste_formatee = "\n  ".join(gabarits_fautifs)
        pytest.fail(
            "Commentaire(s) Django `{# ... #}` sur plusieurs lignes : ils NE SONT PAS "
            "des commentaires et s'affichent en clair sur le site.\n"
            "Le lexer Django compile `tag_re` sans re.DOTALL, donc `.` ne franchit pas "
            "le saut de ligne.\n"
            "Correction : remplacer par `{% comment %} ... {% endcomment %}`.\n\n"
            f"  {liste_formatee}"
        )
