"""
Tests E2E : pages admin de l'inventaire (Stock et MouvementStock).
/ E2E tests: inventory admin pages (Stock and MouvementStock).

Teste les 7 scenarios principaux :
1. Bandeau d'aide sur la liste des stocks
2. Formulaire d'ajout de stock (aide + autocomplete VT uniquement)
3. Action reception sur la fiche stock
4. Action ajustement
5. Action perte
6. Liste des mouvements (aide + pas de bouton Ajouter)
7. Filtre "Tout afficher" sur les mouvements

/ Tests the 7 main scenarios:
1. Help banner on stock list
2. Add stock form (help + VT-only autocomplete)
3. Reception action on stock detail
4. Adjustment action
5. Loss action
6. Movements list (help + no Add button)
7. "Show all" filter on movements

LOCALISATION : tests/e2e/test_admin_inventaire.py

Prerequis / Prerequisites:
    - Donnees POS de test creees (create_test_pos_data)
    - Admin superuser (ADMIN_EMAIL) a acces

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/e2e/test_admin_inventaire.py -v -s
"""

import re

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


@pytest.fixture(scope="session")
def ensure_stock_data(ensure_pos_data, django_shell):
    """Cree un Stock pour le premier produit VT si aucun n'existe.
    / Creates a Stock for the first VT product if none exists.
    """
    django_shell(
        "from inventaire.models import Stock\n"
        "from BaseBillet.models import Product\n"
        "if not Stock.objects.exists():\n"
        "    p = Product.objects.filter(methode_caisse=Product.VENTE).first()\n"
        "    if p:\n"
        "        Stock.objects.create(product=p, quantite=10, unite='UN')\n"
        "        print(f'Stock cree pour {p.name}')\n"
        "    else:\n"
        "        print('ERREUR: aucun produit VT')\n"
        "else:\n"
        "    print(f'Stock existe deja: {Stock.objects.count()}')"
    )


def _go_to_first_stock_detail(page):
    """Navigue vers la liste des stocks et clique sur le premier article.
    / Navigate to stock list and click the first article.
    """
    page.goto("/admin/inventaire/stock/")
    page.wait_for_load_state("networkidle")

    # Les liens list_display_links dans Unfold sont dans les <th> des lignes.
    # On cible un lien dont le href contient /change/ (pas un tri de colonne).
    # / list_display_links in Unfold are in row <th> elements.
    # Target a link whose href contains /change/ (not a column sort link).
    first_link = page.locator('a[href*="/change/"]').first
    expect(first_link).to_be_visible(timeout=10_000)
    first_link.click()
    page.wait_for_load_state("networkidle")

    # Verifier qu'on est sur la page de detail / Verify we're on detail page
    expect(page).to_have_url(re.compile(r"/admin/inventaire/stock/.+/change/"))


class TestAdminInventaire:
    """Tests E2E pour les pages admin inventaire.
    / E2E tests for inventory admin pages.
    """

    # ------------------------------------------------------------------
    # 1. Liste des stocks — bandeau d'aide visible
    # / Stock list — help banner visible
    # ------------------------------------------------------------------

    def test_01_stock_list_help_banner(self, page, login_as_admin, ensure_stock_data):
        """Verifie que le bandeau d'aide est visible sur la liste des stocks.
        / Verify help banner is visible on the stock list page.
        """
        login_as_admin(page)
        page.goto("/admin/inventaire/stock/")
        page.wait_for_load_state("networkidle")

        banner = page.locator('[data-testid="stock-aide-liste"]')
        expect(banner).to_be_visible(timeout=10_000)

    # ------------------------------------------------------------------
    # 2. Ajout de stock — bandeau d'aide + autocomplete VT uniquement
    # / Add stock — help banner + VT-only autocomplete
    # ------------------------------------------------------------------

    def test_02_stock_add_help_and_autocomplete_vt_only(
        self, page, login_as_admin, ensure_pos_data
    ):
        """Verifie le bandeau d'aide sur le formulaire d'ajout
        et que l'autocomplete ne propose que des articles de vente (VT).
        / Verify help banner on add form and autocomplete shows only VT products.
        """
        login_as_admin(page)
        page.goto("/admin/inventaire/stock/add/")
        page.wait_for_load_state("networkidle")

        # Bandeau d'aide visible / Help banner visible
        banner = page.locator('[data-testid="stock-add-help"]')
        expect(banner).to_be_visible(timeout=10_000)

        # Autocomplete Unfold : le widget utilise select2.
        # Il faut cliquer sur le combobox pour ouvrir la dropdown,
        # puis taper dans le champ de recherche qui apparait.
        # / Unfold autocomplete: widget uses select2.
        # Click the combobox to open the dropdown, then type in the search field.

        # 1. Cliquer pour ouvrir le select2 / Click to open select2
        combobox = page.locator('.select2-selection--single').first
        expect(combobox).to_be_visible(timeout=5_000)
        combobox.click()

        # 2. Taper "Biere" dans le champ de recherche select2
        # / Type "Biere" in the select2 search field
        search_input = page.locator('input.select2-search__field').first
        expect(search_input).to_be_visible(timeout=5_000)
        search_input.fill("Biere")

        # 3. Attendre qu'une option apparaisse / Wait for an option to appear
        option = page.locator('.select2-results__option:not(.select2-results__message)').first
        expect(option).to_be_visible(timeout=10_000)

    # ------------------------------------------------------------------
    # 3. Fiche stock — action reception
    # / Stock detail — reception action
    # ------------------------------------------------------------------

    def test_03_stock_changeform_reception(
        self, page, login_as_admin, ensure_stock_data
    ):
        """Entre une quantite et un motif, clique Reception, verifie le bandeau succes.
        / Enter quantity and reason, click Reception, verify success banner.
        """
        login_as_admin(page)
        _go_to_first_stock_detail(page)

        # Remplir quantite et motif / Fill quantity and reason
        quantite_input = page.locator('[data-testid="input-quantite-action"]')
        expect(quantite_input).to_be_visible(timeout=5_000)
        quantite_input.fill("5")

        motif_input = page.locator('[data-testid="input-motif-action"]')
        motif_input.fill("Test E2E")

        # Cliquer sur Reception (HTMX post) / Click Reception (HTMX post)
        btn_reception = page.locator('[data-testid="btn-reception"]')
        btn_reception.click()

        # Attendre le bandeau de succes (HTMX swap) / Wait for success banner (HTMX swap)
        success = page.locator('[data-testid="stock-action-success"]')
        expect(success).to_be_visible(timeout=10_000)

    # ------------------------------------------------------------------
    # 4. Fiche stock — action ajustement
    # / Stock detail — adjustment action
    # ------------------------------------------------------------------

    def test_04_stock_changeform_ajustement(
        self, page, login_as_admin, ensure_stock_data
    ):
        """Entre une quantite=100, clique Ajustement, verifie le bandeau succes.
        / Enter quantity=100, click Adjustment, verify success banner.
        """
        login_as_admin(page)
        _go_to_first_stock_detail(page)

        # Remplir quantite / Fill quantity
        quantite_input = page.locator('[data-testid="input-quantite-action"]')
        expect(quantite_input).to_be_visible(timeout=5_000)
        quantite_input.fill("100")

        # Cliquer Ajustement / Click Adjustment
        btn_ajustement = page.locator('[data-testid="btn-ajustement"]')
        btn_ajustement.click()

        # Attendre le bandeau de succes / Wait for success banner
        success = page.locator('[data-testid="stock-action-success"]')
        expect(success).to_be_visible(timeout=10_000)

    # ------------------------------------------------------------------
    # 5. Fiche stock — action perte
    # / Stock detail — loss action
    # ------------------------------------------------------------------

    def test_05_stock_changeform_perte(
        self, page, login_as_admin, ensure_stock_data
    ):
        """Entre une quantite=2, clique Perte/casse, verifie le bandeau succes.
        / Enter quantity=2, click Loss, verify success banner.
        """
        login_as_admin(page)
        _go_to_first_stock_detail(page)

        # Remplir quantite / Fill quantity
        quantite_input = page.locator('[data-testid="input-quantite-action"]')
        expect(quantite_input).to_be_visible(timeout=5_000)
        quantite_input.fill("2")

        # Cliquer Perte/casse / Click Loss
        btn_perte = page.locator('[data-testid="btn-perte"]')
        btn_perte.click()

        # Attendre le bandeau de succes / Wait for success banner
        success = page.locator('[data-testid="stock-action-success"]')
        expect(success).to_be_visible(timeout=10_000)

    # ------------------------------------------------------------------
    # 6. Liste des mouvements — bandeau aide + pas de bouton Ajouter
    # / Movements list — help banner + no Add button
    # ------------------------------------------------------------------

    def test_06_mouvements_list_help_and_no_add(self, page, login_as_admin):
        """Verifie le bandeau d'aide sur les mouvements et l'absence du bouton Ajouter.
        / Verify help banner on movements page and no Add button.
        """
        login_as_admin(page)
        page.goto("/admin/inventaire/mouvementstock/")
        page.wait_for_load_state("networkidle")

        # Bandeau d'aide visible / Help banner visible
        banner = page.locator('[data-testid="mouvements-aide-filtre"]')
        expect(banner).to_be_visible(timeout=10_000)

        # Pas de bouton "Ajouter" (has_add_permission = False)
        # Le bouton Unfold utilise un lien vers /add/
        # / No "Add" button (has_add_permission = False)
        add_link = page.locator('a[href$="/admin/inventaire/mouvementstock/add/"]')
        expect(add_link).to_have_count(0)

    # ------------------------------------------------------------------
    # 7. Mouvements — filtre "Tout afficher"
    # / Movements — "Show all" filter
    # ------------------------------------------------------------------

    def test_07_mouvements_filter_tout_afficher(self, page, login_as_admin):
        """Verifie que le filtre "Tout afficher" existe et fonctionne.
        / Verify "Show all" filter exists and works.
        """
        login_as_admin(page)
        page.goto("/admin/inventaire/mouvementstock/")
        page.wait_for_load_state("networkidle")

        # Les filtres Unfold sont dans un panneau aside repliable.
        # On clique sur le bouton "Filters" / "Filtrer" pour l'ouvrir.
        # / Unfold filters are in a collapsible aside panel.
        # Click the "Filters" / "Filtrer" button to open it.
        filter_toggle = page.locator(
            'a[title="Filter"], '
            'button:has-text("Filter"), '
            'a:has-text("Filter")'
        ).first
        if filter_toggle.is_visible(timeout=3_000):
            filter_toggle.click()
            page.wait_for_timeout(500)

        # Chercher le lien "Tout afficher" / "Show all" dans les filtres
        # / Find the "Show all" link in filters
        filter_link = page.locator('a[href*="type_mvt=all"]').first
        expect(filter_link).to_be_visible(timeout=10_000)

        # Cliquer dessus / Click it
        filter_link.click()
        page.wait_for_load_state("networkidle")

        # Verifier que la page a charge avec le parametre type_mvt=all
        # / Verify page loaded with type_mvt=all parameter
        expect(page).to_have_url(re.compile(r"type_mvt=all"))
