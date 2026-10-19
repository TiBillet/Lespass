"""
Rendu de l'appel a l'action (SECTION / APPEL_ACTION) avec des boutons en plus.
/ Rendering of the call to action with extra buttons.

LOCALISATION : tests/pytest/test_pages_appel_action.py

Les boutons au-dela des deux premiers viennent de `bloc.contenu`, une liste de
{"titre": libelle, "url": lien}. Les trois skins (classic, V2, faire_festival)
les rendent. Un bouton n'est pose que si son lien commence par « http » ou
« / » : `contenu` arrive aussi par l'API, qui ne nettoie pas ces liens.

Pas de base de donnees : un Bloc non enregistre suffit a rendre le gabarit.
/ No database: an unsaved Bloc is enough to render the template.
"""

import pytest
from django.template.loader import render_to_string

from pages.models import Bloc

GABARITS_APPEL_ACTION = [
    "pages/classic/partials/bloc_section_appel_action.html",
    "pages/V2/partials/bloc_section_appel_action.html",
    "pages/faire_festival/partials/bloc_section_appel_action.html",
]


def _appel_action_avec_boutons(contenu):
    """Un appel a l'action avec deux boutons et le `contenu` donne.
    / A call to action with two buttons and the given `contenu`."""
    return Bloc(
        type_bloc=Bloc.SECTION,
        affichage=Bloc.APPEL_ACTION,
        bouton_label="Premier bouton",
        bouton_url="/premier/",
        bouton2_label="Deuxieme bouton",
        bouton2_url="/deuxieme/",
        contenu=contenu,
    )


@pytest.mark.parametrize("gabarit", GABARITS_APPEL_ACTION)
def test_appel_action_rend_les_boutons_supplementaires(gabarit):
    """Les boutons de `contenu` suivent les deux boutons du bloc, dans l'ordre.
    / Extra buttons follow the block's two buttons, in order."""
    bloc = _appel_action_avec_boutons(
        [
            {"titre": "Troisieme bouton", "url": "https://exemple.org/trois/"},
            {"titre": "Quatrieme bouton", "url": "/quatre/"},
        ]
    )

    html = render_to_string(gabarit, {"bloc": bloc})

    assert 'href="https://exemple.org/trois/"' in html
    assert 'href="/quatre/"' in html
    position_premier = html.index("Premier bouton")
    position_troisieme = html.index("Troisieme bouton")
    position_quatrieme = html.index("Quatrieme bouton")
    assert position_premier < position_troisieme < position_quatrieme


@pytest.mark.parametrize("gabarit", GABARITS_APPEL_ACTION)
def test_appel_action_ne_rend_pas_un_bouton_au_lien_dangereux(gabarit):
    """Un lien javascript: ne devient jamais un bouton.
    / A javascript: link never becomes a button."""
    bloc = _appel_action_avec_boutons(
        [
            {"titre": "Bouton piege", "url": "javascript:alert(1)"},
        ]
    )

    html = render_to_string(gabarit, {"bloc": bloc})

    assert "javascript:" not in html
    assert "Bouton piege" not in html


@pytest.mark.parametrize("gabarit", GABARITS_APPEL_ACTION)
def test_appel_action_ne_rend_pas_un_bouton_sans_lien(gabarit):
    """Un element sans lien ne donne pas un bouton qui ne mene nulle part.
    / An item without a link does not give a dead button."""
    bloc = _appel_action_avec_boutons([{"titre": "Bouton sans lien"}])

    html = render_to_string(gabarit, {"bloc": bloc})

    assert "Bouton sans lien" not in html


@pytest.mark.parametrize("gabarit", GABARITS_APPEL_ACTION)
def test_appel_action_rend_des_boutons_venus_seulement_de_contenu(gabarit):
    """Sans bouton 1 ni bouton 2, les boutons de `contenu` s'affichent quand meme.
    / Without buttons 1 and 2, the `contenu` buttons still render."""
    bloc = Bloc(
        type_bloc=Bloc.SECTION,
        affichage=Bloc.APPEL_ACTION,
        contenu=[
            {"titre": "Creer son espace", "url": "https://tibillet.coop/onboard/"},
            {
                "titre": "Documentation",
                "url": "https://tibillet.github.io/documentation_v3/",
            },
        ],
    )

    html = render_to_string(gabarit, {"bloc": bloc})

    assert 'href="https://tibillet.coop/onboard/"' in html
    assert 'href="https://tibillet.github.io/documentation_v3/"' in html
