"""
Garde-fou : l'encre d'un badge de tag est toujours lisible sur la couleur du lieu.
/ Guard: a tag badge's ink is always legible on the venue's chosen colour.

LOCALISATION : tests/pytest/test_tag_contraste.py

CE QUE CE TEST PROTEGE
----------------------
`Tag.color` est saisi par le gestionnaire dans l'admin pour coder ses categories.
`Tag.contrast_fg` choisit l'encre posee dessus. Si ce choix est faux, le lieu
obtient des badges illisibles SANS AVERTISSEMENT : rien ne leve d'erreur, la page
s'affiche, elle est juste illisible — et le gestionnaire n'a aucun moyen de savoir
que sa couleur pose probleme.

LE PIEGE : LUMINOSITE PERCUE != CONTRASTE
-----------------------------------------
La formule YIQ `(r*299 + g*587 + b*114) / 1000` mesure la luminosite PERCUE. Elle
ne mesure pas le contraste, et elle n'est pas la norme d'accessibilite. Elle choisit
du blanc sur des teintes moyennes ou seul le noir passe : sur douze couleurs
courantes elle produit quatre badges sous 4.5:1 (rouge 3.82, vert 2.87, bleu 4.30,
rose 4.10). WCAG 2.1 linearise chaque composante (correction gamma) avant de les
ponderer — c'est cette linearisation qui change le verdict.
/ The YIQ formula measures PERCEIVED BRIGHTNESS, not contrast, and is not the
accessibility standard. WCAG 2.1 linearises each channel (gamma) before weighting.

POURQUOI CE TEST NE PEUT PAS ECHOUER SUR UNE COULEUR PARTICULIERE
-----------------------------------------------------------------
Le contraste du noir sur une couleur de luminance L vaut (L+0.05)/0.05, celui du
blanc 1.05/(L+0.05). L'un croit avec L, l'autre decroit : le pire cas est leur
croisement, a L ~ 0.179, ou les deux valent 4.58:1. Le meilleur des deux est donc
TOUJOURS >= 4.58:1, quelle que soit la couleur. Un echec de ce test signifie que
`contrast_fg` ne choisit plus le meilleur des deux — pas qu'une couleur est
« impossible ».
/ Black gives (L+0.05)/0.05, white 1.05/(L+0.05); one grows with L, the other
shrinks. The worst case is where they cross (L ~ 0.179), both at 4.58:1. The better
of the two is ALWAYS >= 4.58:1. A failure here means `contrast_fg` no longer picks
the better of the two — not that some colour is "impossible".
"""

import pytest

from BaseBillet.models import Tag

SEUIL_TEXTE = 4.5  # WCAG AA, texte courant / body text

# Douze teintes courantes plus deux gris, dont les quatre que la formule YIQ ratait.
# / Twelve common hues plus two greys, including the four YIQ got wrong.
COULEURS_DE_TAG = [
    "#0dcaf0",  # cyan — le defaut du champ / the field default
    "#e74c3c",  # rouge — YIQ choisissait blanc a 3.82:1
    "#27ae60",  # vert  — YIQ choisissait blanc a 2.87:1
    "#2980b9",  # bleu  — YIQ choisissait blanc a 4.30:1
    "#e93363",  # rose  — YIQ choisissait blanc a 4.10:1
    "#8e44ad",  # violet
    "#e67e22",  # orange
    "#f1c40f",  # jaune
    "#34495e",  # ardoise
    "#1abc9c",  # turquoise
    "#e9b322",  # curcuma
    "#4296cc",  # ocean
    "#4a4a4a",  # gris sombre
    "#808080",  # gris median — proche du pire cas theorique
]


def _luminance_relative(couleur_hexadecimale):
    """
    Luminance relative WCAG 2.1. Recalculee ICI, independamment du modele.
    / WCAG 2.1 relative luminance. Recomputed HERE, independently of the model.

    On ne reutilise PAS Tag._luminance_relative : un test qui appelle la fonction
    qu'il verifie ne verifie rien. Si les deux implementations divergent, c'est
    exactement ce qu'on veut voir.
    / We do NOT reuse the model's helper: a test calling the function it checks
    checks nothing. If the two implementations diverge, that is what we want to see.
    """
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
    """Rapport de contraste WCAG entre deux couleurs. / WCAG contrast ratio."""
    luminances = sorted(
        [_luminance_relative(premiere_couleur), _luminance_relative(seconde_couleur)],
        reverse=True,
    )
    return (luminances[0] + 0.05) / (luminances[1] + 0.05)


@pytest.mark.parametrize("couleur_du_tag", COULEURS_DE_TAG)
def test_l_encre_du_badge_est_lisible_sur_la_couleur_du_lieu(couleur_du_tag):
    """
    Quelle que soit la couleur choisie, l'encre du badge tient >= 4.5:1.
    / Whatever colour is picked, the badge ink holds >= 4.5:1.
    """
    # Tag non sauvegarde : contrast_fg ne lit que self.color, aucun acces base.
    # / Unsaved Tag: contrast_fg only reads self.color, no DB access.
    tag = Tag(name="tag de test", color=couleur_du_tag)

    couleur_de_l_encre = tag.contrast_fg
    rapport_mesure = _rapport_de_contraste(couleur_de_l_encre, couleur_du_tag)

    assert rapport_mesure >= SEUIL_TEXTE, (
        f"Un badge de tag {couleur_du_tag} recoit une encre {couleur_de_l_encre} "
        f"a {rapport_mesure:.2f}:1, il faut >= {SEUIL_TEXTE}:1.\n"
        f"La couleur est SAISIE PAR LE GESTIONNAIRE dans l'admin : il n'a aucun moyen "
        f"de savoir que son choix produit un badge illisible.\n"
        f"contrast_fg doit choisir le MEILLEUR du noir et du blanc, mesure en WCAG "
        f"(luminance linearisee), et non en YIQ (luminosite percue)."
    )


def test_contrast_fg_choisit_toujours_la_meilleure_des_deux_encres():
    """
    contrast_fg ne se contente pas de passer le seuil : il prend le MEILLEUR des deux.

    Ce test est plus fort que le precedent. Une implementation pourrait passer 4.5:1
    partout en choisissant mal sur certaines teintes ou l'autre encre serait bien
    meilleure — ce test l'attrape.
    / Stronger than the one above: an implementation could clear 4.5:1 everywhere
    while still picking the worse ink on some hues. This catches that.
    """
    for couleur_du_tag in COULEURS_DE_TAG:
        tag = Tag(name="tag de test", color=couleur_du_tag)

        contraste_obtenu = _rapport_de_contraste(tag.contrast_fg, couleur_du_tag)
        contraste_du_noir = _rapport_de_contraste("#000000", couleur_du_tag)
        contraste_du_blanc = _rapport_de_contraste("#ffffff", couleur_du_tag)
        meilleur_contraste_possible = max(contraste_du_noir, contraste_du_blanc)

        assert contraste_obtenu == pytest.approx(meilleur_contraste_possible, abs=0.01), (
            f"Sur {couleur_du_tag}, contrast_fg choisit {tag.contrast_fg} "
            f"({contraste_obtenu:.2f}:1) alors que l'autre encre donnerait "
            f"{meilleur_contraste_possible:.2f}:1."
        )
