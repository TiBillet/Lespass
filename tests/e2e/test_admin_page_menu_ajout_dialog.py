"""
Tests E2E : le menu « + Ajouter un bloc apres » de l'apercu d'une page s'ouvre
dans une <dialog> de l'admin, entiere, hors de l'iframe.
/ E2E tests: the preview's "+ Add a block after" menu opens in an admin
<dialog>, fully visible, outside the iframe.

LOCALISATION : tests/e2e/test_admin_page_menu_ajout_dialog.py

L'iframe d'apercu a la hauteur de son contenu (pages/static/pages/admin/apercu.js).
Une page d'UN seul bloc donne donc une iframe basse : un menu ouvert dedans
serait coupe. Le + de la barre (apercu_page_outils.js) previent l'admin, qui
ouvre #dialog-menu-ajout (blocs_de_la_page.html) et y charge la liste.

Donnees : une page de test a un bloc, creee puis supprimee par la fixture.
/ Data: a one-block test page, created then deleted by the fixture.
"""

import pytest
from playwright.sync_api import expect


# Familles de tests : `make e2e-visible <famille>` (liste : make help, ou pytest.ini).
# / Test families: `make e2e-visible <family>` (list: make help, or pytest.ini).
pytestmark = [pytest.mark.e2e, pytest.mark.admin]

SLUG_DE_LA_PAGE_DE_TEST = "e2e-menu-ajout-dialog"


@pytest.fixture
def page_d_un_seul_bloc(django_shell):
    """
    Cree une page avec UN bloc FAQ, renvoie son pk, puis la supprime.
    / Creates a page with ONE FAQ block, returns its pk, then deletes it.
    """
    code_de_creation = f"""
from pages.models import Bloc, Page
Page.objects.filter(slug="{SLUG_DE_LA_PAGE_DE_TEST}").delete()
page_de_test = Page.objects.create(titre="E2E menu ajout", slug="{SLUG_DE_LA_PAGE_DE_TEST}")
Bloc.objects.create(page=page_de_test, type_bloc=Bloc.FAQ, titre="Question E2E", position=1)
print(page_de_test.pk)
"""
    pk_de_la_page = django_shell(code_de_creation)
    yield pk_de_la_page
    django_shell(
        f'from pages.models import Page; Page.objects.filter(slug="{SLUG_DE_LA_PAGE_DE_TEST}").delete()'
    )


def _ouvrir_le_menu_du_premier_bloc(page, pk_de_la_page):
    """
    Ouvre la fiche Page, clique sur le + du bloc 1 dans l'iframe, et renvoie
    la <dialog> une fois la liste des modeles chargee.
    / Opens the Page form, clicks block 1's "+" in the iframe, returns the dialog.
    """
    page.goto(f"/admin/pages/page/{pk_de_la_page}/change/")
    page.wait_for_load_state("networkidle")

    iframe_d_apercu = page.frame_locator('[data-testid="page-apercu-iframe"]')
    iframe_d_apercu.locator('[data-testid="page-bloc-1-ajouter"]').click()

    dialog_du_menu = page.locator('[data-testid="page-dialog-menu-ajout"]')
    expect(dialog_du_menu).to_be_visible()
    # Les liens sont dans l'ADMIN, pas dans l'iframe.
    # / The links are in the ADMIN document, not in the iframe.
    expect(
        page.locator('[data-testid="page-bloc-1-ajouter-sectioncarte"]')
    ).to_be_visible()
    return dialog_du_menu


class TestMenuAjoutDansUneDialog:
    """Le menu « + » d'une barre s'ouvre dans une <dialog> de l'admin.
    / A bar's "+" menu opens in an admin <dialog>.
    """

    def test_la_dialog_est_entierement_visible_sur_une_page_d_un_bloc(
        self, page, login_as_admin, page_d_un_seul_bloc
    ):
        """Sur une page d'un seul bloc (iframe basse), la dialog tient dans l'ecran.
        / On a one-block page (short iframe), the dialog fits in the viewport.
        """
        login_as_admin(page)
        dialog_du_menu = _ouvrir_le_menu_du_premier_bloc(page, page_d_un_seul_bloc)

        boite_de_la_dialog = dialog_du_menu.bounding_box()
        taille_de_l_ecran = page.viewport_size
        assert boite_de_la_dialog["x"] >= 0
        assert boite_de_la_dialog["y"] >= 0
        assert (
            boite_de_la_dialog["x"] + boite_de_la_dialog["width"]
            <= taille_de_l_ecran["width"]
        )
        assert (
            boite_de_la_dialog["y"] + boite_de_la_dialog["height"]
            <= taille_de_l_ecran["height"]
        )

    def test_la_dialog_est_centree_dans_l_ecran(
        self, page, login_as_admin, page_d_un_seul_bloc
    ):
        """Le centre de la dialog est le centre de l'ecran (a 2 px pres).
        / The dialog's center is the viewport's center (within 2 px).
        """
        login_as_admin(page)
        dialog_du_menu = _ouvrir_le_menu_du_premier_bloc(page, page_d_un_seul_bloc)

        boite_de_la_dialog = dialog_du_menu.bounding_box()
        taille_de_l_ecran = page.viewport_size
        centre_horizontal_de_la_dialog = (
            boite_de_la_dialog["x"] + boite_de_la_dialog["width"] / 2
        )
        centre_vertical_de_la_dialog = (
            boite_de_la_dialog["y"] + boite_de_la_dialog["height"] / 2
        )
        assert abs(centre_horizontal_de_la_dialog - taille_de_l_ecran["width"] / 2) <= 2
        assert abs(centre_vertical_de_la_dialog - taille_de_l_ecran["height"] / 2) <= 2

    def test_le_bouton_de_l_en_tete_ouvre_la_meme_dialog(
        self, page, login_as_admin, page_d_un_seul_bloc
    ):
        """« + Ajouter un bloc en premier » ouvre la dialog, liens en inserer_apres=0.
        / The header button opens the same dialog, links with inserer_apres=0.
        """
        login_as_admin(page)
        page.goto(f"/admin/pages/page/{page_d_un_seul_bloc}/change/")
        page.wait_for_load_state("networkidle")

        page.locator('[data-testid="page-ajouter-en-tete"]').click()

        expect(page.locator('[data-testid="page-dialog-menu-ajout"]')).to_be_visible()
        lien_section_carte = page.locator(
            '[data-testid="page-ajouter-en-tete-sectioncarte"]'
        )
        expect(lien_section_carte).to_be_visible()
        assert "inserer_apres=0" in lien_section_carte.get_attribute("href")

    def test_echap_ferme_la_dialog_et_rend_le_focus_au_bouton(
        self, page, login_as_admin, page_d_un_seul_bloc
    ):
        """Echap ferme la dialog, et le focus revient sur le + dans l'iframe.
        / Escape closes the dialog and focus returns to the "+" in the iframe.
        """
        login_as_admin(page)
        dialog_du_menu = _ouvrir_le_menu_du_premier_bloc(page, page_d_un_seul_bloc)

        page.keyboard.press("Escape")

        expect(dialog_du_menu).to_be_hidden()
        iframe_d_apercu = page.frame_locator('[data-testid="page-apercu-iframe"]')
        expect(
            iframe_d_apercu.locator('[data-testid="page-bloc-1-ajouter"]')
        ).to_be_focused()

    def test_choisir_un_modele_ouvre_la_fiche_bloc_a_la_bonne_place(
        self, page, login_as_admin, page_d_un_seul_bloc
    ):
        """Un clic sur un modele ouvre l'ajout d'un bloc, insere apres le bloc 1.
        / Clicking a model opens the block add form, inserted after block 1.
        """
        login_as_admin(page)
        _ouvrir_le_menu_du_premier_bloc(page, page_d_un_seul_bloc)

        page.locator('[data-testid="page-bloc-1-ajouter-sectioncarte"]').click()
        page.wait_for_url("**/admin/pages/bloc/add/**")

        assert "inserer_apres=1" in page.url
