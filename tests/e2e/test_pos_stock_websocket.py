"""
Test E2E : mise à jour stock en temps réel via WebSocket entre 2 onglets POS.
/ E2E test: real-time stock update via WebSocket between 2 POS tabs.

LOCALISATION : tests/e2e/test_pos_stock_websocket.py

Scénario :
1. Ajuster le stock de "Biere" à 10 via django_shell + mettre bloquant
2. Ouvrir 2 onglets POS sur le même point de vente
3. Vendre 5 Biere sur l'onglet 1 → vérifier que l'article n'est pas bloquant
4. Vendre 5 de plus → vérifier badge "Épuisé" + tuile grisée sur les 2 onglets

Prérequis / Prerequisites:
- docker exec lespass_django poetry run python manage.py create_test_pos_data
- Carte primaire tag_id_cm=A49E8E2A
- WebSocket fonctionnel (Daphne ASGI + Redis channel layer)

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/e2e/test_pos_stock_websocket.py -v -s
"""

import os
import re

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sell_articles_especes(page, article_name, quantity=1):
    """Ajoute N articles au panier et paie en espèces.
    / Adds N articles to cart and pays cash.
    """
    tile = page.locator("#products .article-container").filter(has_text=article_name).first
    expect(tile).to_be_visible(timeout=5_000)

    for _ in range(quantity):
        tile.click()
        page.wait_for_timeout(300)

    expect(page.locator("#addition-list")).to_contain_text(article_name, timeout=5_000)

    page.locator("#bt-valider").click()
    expect(page.locator('[data-testid="paiement-moyens"]')).to_be_visible(timeout=10_000)

    page.locator('[data-testid="paiement-moyens"]').get_by_text("ESPÈCE").click()
    expect(page.locator('[data-testid="paiement-confirmation"]')).to_be_visible(timeout=10_000)

    page.locator("#bt-valider-layer2").click()
    expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=15_000)

    page.locator('[data-testid="paiement-succes"] #bt-retour-layer1').click()
    expect(page.locator('[data-testid="paiement-succes"]')).not_to_be_visible(timeout=5_000)


# ===========================================================================
# Test WebSocket stock multi-onglet
# ===========================================================================


class TestPOSStockWebSocket:
    """Vérifie le flux complet WebSocket : vente → broadcast → OOB swap → badge
    mis à jour sur tous les onglets POS connectés.
    / Verifies the full WebSocket flow: sale → broadcast → OOB swap → badge
    updated on all connected POS tabs.
    """

    def test_stock_websocket_multi_onglet(
        self, browser, login_as_admin, django_shell, ensure_pos_data
    ):
        """
        Stock 10, bloquant. Vendre 5 → pas bloquant. Vendre 5 → bloquant + grisé.
        Vérifie sur 2 onglets que le badge "Épuisé" et la classe article-bloquant
        sont propagés via WebSocket.
        """
        demo_tag_id = os.environ.get("DEMO_TAGID_CM", "A49E8E2A")

        # --- Setup : récupérer le PV Bar ---
        # / Get PV Bar UUID
        pv_result = django_shell(
            "from laboutik.models import PointDeVente; "
            "pv = PointDeVente.objects.filter(name='Bar').first(); "
            "print(pv.uuid if pv else 'NOT_FOUND')"
        )
        assert "NOT_FOUND" not in pv_result, "PV Bar introuvable"
        pv_uuid = pv_result.strip()

        # --- Setup : remettre Biere en état propre AVANT tout ---
        # D'abord autoriser la vente (pour ne pas être bloqué),
        # puis ajuster le stock à 10, puis mettre bloquant.
        # / First allow sales (to not be blocked), adjust to 10, then set blocking.
        django_shell(
            "from BaseBillet.models import Product; "
            "from inventaire.models import Stock; "
            "from inventaire.services import StockService; "
            "p = Product.objects.filter(name='Biere').first(); "
            "stock, _ = Stock.objects.get_or_create(product=p, defaults={'quantite': 0, 'unite': 'UN'}); "
            "stock.seuil_alerte = 3; "
            "stock.autoriser_vente_hors_stock = True; "
            "stock.save(); "
            "StockService.ajuster_inventaire(stock=stock, stock_reel=10, motif='Setup WS test'); "
            "stock.refresh_from_db(); "
            "Stock.objects.filter(pk=stock.pk).update(autoriser_vente_hors_stock=False); "
            "stock.refresh_from_db(); "
            "print(f'OK qty={stock.quantite} bloquant={not stock.autoriser_vente_hors_stock}')"
        )

        # --- Ouvrir 2 onglets POS ---
        # Chaque onglet a son propre contexte browser (cookies indépendants)
        # / Each tab has its own browser context (independent cookies)
        from tests.e2e.conftest import BASE_URL

        context1 = browser.new_context(base_url=BASE_URL, ignore_https_errors=True)
        page1 = context1.new_page()
        login_as_admin(page1)
        page1.goto(
            f"/laboutik/caisse/point_de_vente/?uuid_pv={pv_uuid}&tag_id_cm={demo_tag_id}",
            wait_until="domcontentloaded",
        )
        page1.wait_for_load_state("networkidle", timeout=15_000)
        expect(page1.locator("#products .article-container").first).to_be_visible(timeout=10_000)

        context2 = browser.new_context(base_url=BASE_URL, ignore_https_errors=True)
        page2 = context2.new_page()
        login_as_admin(page2)
        page2.goto(
            f"/laboutik/caisse/point_de_vente/?uuid_pv={pv_uuid}&tag_id_cm={demo_tag_id}",
            wait_until="domcontentloaded",
        )
        page2.wait_for_load_state("networkidle", timeout=15_000)
        expect(page2.locator("#products .article-container").first).to_be_visible(timeout=10_000)

        # Attendre que les WebSocket se connectent
        # / Wait for WebSocket connections
        page1.wait_for_timeout(2_000)
        page2.wait_for_timeout(1_000)


        try:
            tile1 = page1.locator("#products .article-container").filter(has_text="Biere").first
            tile2 = page2.locator("#products .article-container").filter(has_text="Biere").first

            # --- Vérification état initial : stock=10, pas bloquant ---
            # / Initial state: stock=10, not blocking
            expect(tile1).to_be_visible(timeout=5_000)
            expect(tile2).to_be_visible(timeout=5_000)

            initial_bloquant = tile1.get_attribute("data-stock-bloquant")
            assert initial_bloquant != "true", (
                f"Biere ne devrait pas être bloquante avec stock=10. "
                f"data-stock-bloquant={initial_bloquant}"
            )

            # --- Phase 1 : Vendre 5 Biere (stock 10 → 5) ---
            # / Phase 1: Sell 5 Biere (stock 10 → 5)
            _sell_articles_especes(page1, "Biere", quantity=5)

            # Attendre le broadcast WebSocket
            # / Wait for WebSocket broadcast
            page1.wait_for_timeout(3_000)
            page2.wait_for_timeout(2_000)

            # Stock=5, seuil=3 → en alerte mais PAS bloquant (stock > 0)
            # / Stock=5, threshold=3 → alert but NOT blocking (stock > 0)
            mid_bloquant = tile2.get_attribute("data-stock-bloquant")
            assert mid_bloquant != "true", (
                f"Biere ne devrait pas être bloquante avec stock=5. "
                f"data-stock-bloquant={mid_bloquant}"
            )

            # --- Phase 2 : Vendre 5 de plus (stock 5 → 0) ---
            # / Phase 2: Sell 5 more (stock 5 → 0)
            _sell_articles_especes(page1, "Biere", quantity=5)

            # Attendre que le badge "Épuisé" apparaisse via WebSocket OOB swap.
            # Le broadcast passe par : on_commit → broadcast_stock_update →
            # channel_layer.group_send → consumer.stock_update → ws.send →
            # htmx ws extension → oobSwap → JS listener.
            # On utilise wait_for_selector qui poll le DOM (pas un sleep fixe).
            # / Wait for "Out of stock" badge via WebSocket OOB swap.
            biere_uuid = tile1.get_attribute("data-uuid")
            badge_selector = f'#stock-badge-{biere_uuid} [data-testid="stock-badge-rupture"]'

            # Onglet 1 : attendre badge "Épuisé" via WebSocket OOB swap
            # wait_for_selector poll le DOM jusqu'à ce que le badge apparaisse
            # / Tab 1: wait for "Out of stock" badge via WebSocket OOB swap
            page1.wait_for_selector(badge_selector, state="visible", timeout=30_000)

            # Onglet 1 : vérifier data-stock-bloquant et classe CSS
            # / Tab 1: check data-stock-bloquant and CSS class
            tile1_bloquant = tile1.get_attribute("data-stock-bloquant")
            tile1_classes = tile1.get_attribute("class") or ""
            assert tile1_bloquant == "true", (
                f"Onglet 1 : data-stock-bloquant devrait être 'true'. "
                f"Valeur={tile1_bloquant}"
            )
            assert "article-bloquant" in tile1_classes, (
                f"Onglet 1 : classe article-bloquant manquante. "
                f"Classes={tile1_classes}"
            )

            # Onglet 2 : vérifier badge "Épuisé" (via WebSocket)
            # / Tab 2: check "Épuisé" badge (via WebSocket)
            badge2 = page2.locator(
                '#stock-badge-' + tile2.get_attribute("data-uuid")
                + ' [data-testid="stock-badge-rupture"]'
            )
            expect(badge2).to_be_visible(timeout=10_000)

            # Onglet 2 : vérifier data-stock-bloquant et classe CSS
            # / Tab 2: check data-stock-bloquant and CSS class
            tile2_bloquant = tile2.get_attribute("data-stock-bloquant")
            tile2_classes = tile2.get_attribute("class") or ""
            assert tile2_bloquant == "true", (
                f"Onglet 2 : data-stock-bloquant devrait être 'true' (WebSocket). "
                f"Valeur={tile2_bloquant}"
            )
            assert "article-bloquant" in tile2_classes, (
                f"Onglet 2 : classe article-bloquant manquante (WebSocket). "
                f"Classes={tile2_classes}"
            )

            # Onglet 2 : vérifier que le clic ne fait rien (pointer-events:none + JS check)
            # / Tab 2: verify click does nothing
            tile2.dispatch_event("click")
            page2.wait_for_timeout(500)
            addition_text = page2.locator("#addition-list").inner_text()
            assert "Biere" not in addition_text, (
                "Clic sur Biere bloquante ne devrait rien ajouter au panier"
            )

        finally:
            # --- Cleanup : remettre le stock à un état sain ---
            # / Cleanup: restore stock to healthy state
            django_shell(
                "from BaseBillet.models import Product; "
                "from inventaire.models import Stock; "
                "from inventaire.services import StockService; "
                "p = Product.objects.filter(name='Biere').first(); "
                "stock = p.stock_inventaire; "
                "stock.autoriser_vente_hors_stock = True; "
                "stock.save(); "
                "StockService.ajuster_inventaire(stock=stock, stock_reel=100, motif='Cleanup WS test'); "
                "print('Cleanup OK')"
            )
            context1.close()
            context2.close()
