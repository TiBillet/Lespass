"""
Tests E2E : Menu Ventes POS (Ticket X, onglets, liste, detail hide/show).
/ E2E tests: POS Sales Menu (Ticket X, tabs, list, detail hide/show).

Prerequis / Prerequisites:
- docker exec lespass_django poetry run python manage.py create_test_pos_data
- Carte primaire tag_id_cm=A49E8E2A
- Serveur Django actif via Traefik
"""

import os
import re
import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e

DEMO_TAGID_CM = os.environ.get("DEMO_TAGID_CM", "A49E8E2A")


class TestMenuVentes:
    """Tests du menu Ventes dans l'interface POS.
    / Tests for the Sales menu in the POS interface."""

    def _get_pv_uuid(self, django_shell):
        """Recupere l'UUID du premier PV (Bar). / Gets first POS UUID (Bar)."""
        result = django_shell(
            "from laboutik.models import PointDeVente; "
            "pv = PointDeVente.objects.filter(name='Bar').first(); "
            "print(f'uuid={pv.uuid}') if pv else print('NOT_FOUND')"
        )
        match = re.search(r"uuid=(.+)", result)
        if not match:
            pytest.fail(f"PV Bar introuvable: {result}")
        return match.group(1).strip()

    def _open_ventes(self, page, django_shell, login_as_admin, vue=""):
        """Navigue directement vers la page Ventes (acces par URL).
        / Navigate directly to the Sales page (URL access).
        """
        login_as_admin(page)
        pv_uuid = self._get_pv_uuid(django_shell)
        url = (
            f"/laboutik/caisse/recap-en-cours/"
            f"?uuid_pv={pv_uuid}&tag_id_cm={DEMO_TAGID_CM}"
        )
        if vue:
            url += f"&vue={vue}"
        page.goto(url)
        page.wait_for_load_state("networkidle")

    def test_01_ticket_x_toutes_caisses(self, page, django_shell, login_as_admin):
        """
        Acces direct au Ticket X, verifie le tableau des totaux.
        / Direct access to Ticket X, verify totals table.
        """
        self._open_ventes(page, django_shell, login_as_admin)
        expect(page.locator('[data-testid="ventes-recap"]')).to_be_visible(timeout=10_000)
        expect(page.locator('[data-testid="recap-totaux-moyen"]')).to_be_visible(timeout=5_000)

    def test_02_onglet_par_moyen(self, page, django_shell, login_as_admin):
        """
        Onglet "Par moyen" via URL directe, verifie le tableau croise.
        / "By method" tab via direct URL, verify cross table.
        """
        self._open_ventes(page, django_shell, login_as_admin, vue="par_moyen")
        expect(page.locator('[data-testid="recap-synthese-operations"]')).to_be_visible(timeout=10_000)

    def test_03_liste_ventes_et_detail_collapse(self, page, django_shell, login_as_admin, ensure_pos_data):
        """
        Liste des ventes → clic sur une ligne → detail collapse sous la ligne
        → re-clic → detail ferme. Pas de perte de scroll.
        / Sales list → click row → detail collapses below row
        → re-click → detail closes. No scroll loss.
        """
        login_as_admin(page)
        pv_uuid = self._get_pv_uuid(django_shell)
        page.goto(
            f"/laboutik/caisse/liste-ventes/"
            f"?uuid_pv={pv_uuid}&tag_id_cm={DEMO_TAGID_CM}"
        )
        page.wait_for_load_state("networkidle")

        # Verifier que le tableau est present / Verify table is present
        expect(page.locator('[data-testid="liste-tableau"]')).to_be_visible(timeout=10_000)

        # Verifier au moins une ligne / Verify at least one row
        premiere_ligne = page.locator('[data-testid^="vente-ligne-"]').first
        expect(premiere_ligne).to_be_visible(timeout=5_000)

        # Cliquer → collapse detail sous la ligne / Click → collapse detail below row
        premiere_ligne.click()
        page.wait_for_timeout(2_000)

        # Le detail collapse doit apparaitre / Collapse detail must appear
        detail_collapse = page.locator('[data-testid="ventes-detail-collapse"]')
        expect(detail_collapse).to_be_visible(timeout=10_000)

        # La ligne est surlignee / Row is highlighted
        expect(page.locator('.ventes-ligne-active')).to_be_visible()

        # Le tableau des articles est visible / Articles table is visible
        expect(page.locator('[data-testid="detail-articles"]')).to_be_visible()

        # Re-clic → ferme le detail / Re-click → close detail
        premiere_ligne.click()
        expect(detail_collapse).not_to_be_visible(timeout=5_000)

    def test_04_navigation_burger_menu_ventes(self, page, pos_page):
        """
        Depuis le POS, ouvrir le burger menu et cliquer VENTES.
        Verifie que la page Ventes s'affiche en plein ecran.
        / From POS, open burger menu and click VENTES.
        Verify the Sales page displays full screen.
        """
        pos_page(page, "Bar")

        # Ouvrir le burger menu / Open burger menu
        page.locator('[data-testid="burger-icon"]').click()
        page.locator('[data-testid="menu-burger"]').wait_for(state="visible", timeout=5_000)

        # Cliquer VENTES / Click VENTES
        page.locator('[data-testid="menu-ventes"]').click()

        # Le Ticket X plein ecran / Full screen Ticket X
        expect(page.locator('[data-testid="ventes-recap"]')).to_be_visible(timeout=10_000)

        # Plus de categories ni de footer (pas dans le DOM de ventes.html)
        # / No categories or footer (not in ventes.html DOM)
        expect(page.locator('[data-testid="caisse-pv-interface"]')).not_to_be_visible()
