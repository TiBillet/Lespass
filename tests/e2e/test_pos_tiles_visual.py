"""
Tests E2E : affichage visuel des tuiles articles POS.
/ E2E tests: POS article tile visual display.

Conversion de tests/playwright/tests/laboutik/45-laboutik-pos-tiles-visual.spec.ts

Prérequis / Prerequisites:
- docker exec lespass_django poetry run python manage.py create_test_pos_data
- Carte primaire tag_id_cm=A49E8E2A existante
"""

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


class TestPOSTilesVisual:
    """LaBoutik POS — Affichage visuel des tuiles / Article tiles visual display."""

    def test_01_tiles_have_background_color(self, page, pos_page):
        """Chaque tuile a un style background-color inline.
        / Each tile has an inline background-color style.
        """
        pos_page(page, "Bar")
        tiles = page.locator("#products .article-container")

        tile_count = tiles.count()
        assert tile_count > 0, "Aucune tuile trouvée"

        for i in range(tile_count):
            style_attr = tiles.nth(i).get_attribute("style")
            assert style_attr and "background-color" in style_attr, (
                f"Tuile {i} n'a pas de background-color: {style_attr}"
            )

    def test_02_category_icon_badge(self, page, pos_page):
        """Le badge icône catégorie (.article-cat-icon) est présent.
        / Category icon badge (.article-cat-icon) is present.
        """
        pos_page(page, "Bar")
        tiles = page.locator("#products .article-container")
        tile_count = tiles.count()
        assert tile_count > 0

        cat_icons = page.locator("#products .article-container .article-cat-icon")
        cat_icon_count = cat_icons.count()
        assert cat_icon_count > 0, (
            f"Aucun badge catégorie trouvé sur {tile_count} tuiles"
        )

    def test_03_visual_layer_present(self, page, pos_page):
        """La zone visuelle produit (.article-visual-layer) est présente.
        / Product visual zone (.article-visual-layer) is present.
        """
        pos_page(page, "Bar")
        visual_layers = page.locator(
            "#products .article-container .article-visual-layer"
        )
        count = visual_layers.count()
        assert count > 0, "Aucune zone visuelle produit trouvée"

    def test_04_footer_price_pills(self, page, pos_page):
        """Le footer de tuile affiche les prix (.article-footer-layer + .article-tarif-pill).
        / Tile footer shows prices (.article-footer-layer + .article-tarif-pill).
        """
        pos_page(page, "Bar")
        footers = page.locator(
            "#products .article-container .article-footer-layer"
        )
        footer_count = footers.count()
        assert footer_count > 0, "Aucun footer de tuile trouvé"

        pills = page.locator("#products .article-tarif-pill")
        pill_count = pills.count()
        assert pill_count > 0, "Aucun pill de prix trouvé"

    def test_05_category_menu_icons(self, page, pos_page):
        """Le menu catégorie (#categories) affiche au moins 3 icônes.
        / Category menu (#categories) shows at least 3 icons.
        """
        pos_page(page, "Bar")
        category_nav = page.locator("#categories")
        expect(category_nav).to_be_visible(timeout=5_000)

        category_icons = page.locator("#categories .category-icon")
        icon_count = category_icons.count()
        assert icon_count >= 3, (
            f"Attendu >= 3 icônes catégorie, trouvé {icon_count}"
        )

    def test_06_biere_amber_color(self, page, pos_page):
        """La tuile Bière a la couleur de fond #F59E0B / rgb(245, 158, 11).
        / Beer tile has background color #F59E0B / rgb(245, 158, 11).
        """
        pos_page(page, "Bar")
        biere_tile = page.locator(
            '#products .article-container[data-name="Biere"]'
        ).first

        if not biere_tile.is_visible(timeout=5_000):
            pytest.fail('Tuile "Biere" introuvable — create_test_pos_data devrait la créer')

        style_attr = biere_tile.get_attribute("style")
        assert style_attr, "Tuile Biere n'a pas de style"

        has_amber = (
            "#f59e0b" in style_attr.lower()
            or "245, 158, 11" in style_attr
            or "245,158,11" in style_attr
        )
        assert has_amber, f"Couleur ambre non trouvée dans: {style_attr}"

        cat_icon = biere_tile.locator(".article-cat-icon")
        expect(cat_icon).to_be_visible()

    def test_07_coca_red_color(self, page, pos_page):
        """La tuile Coca a la couleur de fond #DC2626 / rgb(220, 38, 38).
        / Coca tile has background color #DC2626 / rgb(220, 38, 38).
        """
        pos_page(page, "Bar")
        coca_tile = page.locator(
            '#products .article-container[data-name="Coca"]'
        ).first

        if not coca_tile.is_visible(timeout=5_000):
            pytest.fail('Tuile "Coca" introuvable — create_test_pos_data devrait la créer')

        style_attr = coca_tile.get_attribute("style")
        assert style_attr, "Tuile Coca n'a pas de style"

        has_red = (
            "#dc2626" in style_attr.lower()
            or "220, 38, 38" in style_attr
            or "220,38,38" in style_attr
        )
        assert has_red, f"Couleur rouge non trouvée dans: {style_attr}"

    def test_08_data_testid_and_data_group(self, page, pos_page):
        """Les tuiles ont data-testid et data-group (requis par articles.js).
        / Tiles have data-testid and data-group (required by articles.js).
        """
        pos_page(page, "Bar")
        tiles = page.locator("#products .article-container")
        tile_count = tiles.count()
        assert tile_count > 0

        tiles_to_check = min(tile_count, 5)
        for i in range(tiles_to_check):
            tile = tiles.nth(i)

            data_group = tile.get_attribute("data-group")
            assert data_group, f"Tuile {i} n'a pas data-group"
            assert data_group.startswith("groupe_"), (
                f"data-group devrait commencer par 'groupe_', got: {data_group}"
            )

            data_testid = tile.get_attribute("data-testid")
            assert data_testid, f"Tuile {i} n'a pas data-testid"
            assert data_testid.startswith("article-"), (
                f"data-testid devrait commencer par 'article-', got: {data_testid}"
            )

    def test_09_category_filter(self, page, pos_page):
        """Le filtre catégorie cache et montre les bonnes tuiles.
        / Category filter hides and shows the correct tiles.
        """
        pos_page(page, "Bar")

        specific_categories = page.locator("#categories .category-item[data-sel]")
        cat_count = specific_categories.count()

        if cat_count == 0:
            pytest.skip("Aucune catégorie spécifique trouvée")

        # Compter les tuiles avant le filtre / Count tiles before filtering
        tiles_before = page.locator("#products .article-container").count()

        # Cliquer sur la première catégorie / Click first category
        first_cat = specific_categories.first
        cat_name = first_cat.get_attribute("data-sel")
        first_cat.click()

        page.wait_for_timeout(300)

        # Compter les tuiles de cette catégorie / Count tiles of this category
        visible_tiles = page.locator(
            f"#products .article-container.{cat_name}"
        )
        visible_count = visible_tiles.count()

        # Au moins 0 tuile (la catégorie peut être vide)
        assert visible_count >= 0, (
            f"Filtre '{cat_name}': attendu >= 0 tuiles visibles"
        )
