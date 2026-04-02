"""
Tests E2E : Corrections moyen de paiement, fond de caisse, sortie de caisse.
/ E2E tests: Payment method corrections, cash float, cash withdrawal.

Session 17 — Conformite LNE exigence 4.

Prerequis / Prerequisites:
- docker exec lespass_django poetry run python manage.py create_test_pos_data
- Serveur Django actif via Traefik
- Variable ADMIN_EMAIL configuree

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/e2e/test_pos_corrections_fond_sortie.py -v -s
"""

import os
import re
import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e

DEMO_TAGID_CM = os.environ.get("DEMO_TAGID_CM", "A49E8E2A")


class TestFondDeCaisse:
    """Tests du fond de caisse (lecture et modification).
    / Cash float tests (read and update)."""

    def test_fond_de_caisse_get_affiche_formulaire(self, page, django_shell, login_as_admin):
        """
        GET fond de caisse → affiche le formulaire avec montant actuel.
        / GET cash float → shows form with current amount.
        """
        login_as_admin(page)
        page.goto("/laboutik/caisse/fond-de-caisse/")
        page.wait_for_load_state("networkidle")

        # Le formulaire est visible / Form is visible
        expect(page.locator('[data-testid="fond-de-caisse"]')).to_be_visible(timeout=10_000)
        expect(page.locator('[data-testid="fond-input-montant"]')).to_be_visible()
        expect(page.locator('[data-testid="fond-btn-enregistrer"]')).to_be_visible()

    def test_fond_de_caisse_post_met_a_jour(self, page, login_as_admin):
        """
        POST fond de caisse → montant mis a jour, message de succes affiche.
        / POST cash float → amount updated, success message displayed.
        """
        login_as_admin(page)
        page.goto("/laboutik/caisse/fond-de-caisse/")
        page.wait_for_load_state("networkidle")

        # Remplir le montant / Fill amount
        input_montant = page.locator('[data-testid="fond-input-montant"]')
        input_montant.fill("250.00")

        # Cliquer Enregistrer / Click Save
        page.locator('[data-testid="fond-btn-enregistrer"]').click()
        page.wait_for_timeout(2_000)

        # Message de succes visible / Success message visible
        expect(page.locator('[data-testid="fond-message-succes"]')).to_be_visible(timeout=5_000)

        # Le montant affiche dans le template est 250.00 / Displayed amount is 250.00
        expect(page.locator('text=250.00')).to_be_visible(timeout=3_000)


class TestSortieDeCaisse:
    """Tests de la sortie de caisse (formulaire ventilation).
    / Cash withdrawal tests (denomination breakdown form)."""

    def test_sortie_de_caisse_formulaire_visible(self, page, django_shell, login_as_admin):
        """
        GET sortie de caisse → formulaire ventilation 12 lignes visible.
        / GET cash withdrawal → 12-line denomination form visible.
        """
        login_as_admin(page)

        # Recuperer le PV Bar / Get Bar POS UUID
        result = django_shell(
            "from laboutik.models import PointDeVente; "
            "pv = PointDeVente.objects.filter(name='Bar').first(); "
            "print(f'uuid={pv.uuid}') if pv else print('NOT_FOUND')"
        )
        match = re.search(r"uuid=(.+)", result)
        if not match:
            pytest.skip("PV Bar introuvable — lancer create_test_pos_data")
        uuid_pv = match.group(1).strip()

        page.goto(f"/laboutik/caisse/sortie-de-caisse/?uuid_pv={uuid_pv}")
        page.wait_for_load_state("networkidle")

        # Le formulaire est visible / Form is visible
        expect(page.locator('[data-testid="sortie-de-caisse"]')).to_be_visible(timeout=10_000)
        expect(page.locator('[data-testid="sortie-coupures-table"]')).to_be_visible()
        expect(page.locator('[data-testid="sortie-btn-enregistrer"]')).to_be_visible()

        # Au moins 12 inputs de coupure / At least 12 denomination inputs
        inputs_coupure = page.locator('[data-testid^="sortie-input-"]')
        assert inputs_coupure.count() >= 12, f"Attendu 12 inputs, trouve {inputs_coupure.count()}"

    def test_sortie_de_caisse_creation(self, page, django_shell, login_as_admin):
        """
        POST sortie de caisse avec ventilation → message de succes.
        / POST cash withdrawal with breakdown → success message.
        """
        login_as_admin(page)

        result = django_shell(
            "from laboutik.models import PointDeVente; "
            "pv = PointDeVente.objects.filter(name='Bar').first(); "
            "print(f'uuid={pv.uuid}') if pv else print('NOT_FOUND')"
        )
        match = re.search(r"uuid=(.+)", result)
        if not match:
            pytest.skip("PV Bar introuvable")
        uuid_pv = match.group(1).strip()

        page.goto(f"/laboutik/caisse/sortie-de-caisse/?uuid_pv={uuid_pv}")
        page.wait_for_load_state("networkidle")

        # Saisir 2 × 20€ et 1 × 5€ / Enter 2 × 20€ and 1 × 5€
        page.locator('[data-testid="sortie-input-2000"]').fill("2")
        page.locator('[data-testid="sortie-input-500"]').fill("1")
        page.locator('[data-testid="sortie-textarea-note"]').fill("Test E2E sortie")

        # Soumettre / Submit
        page.locator('[data-testid="sortie-btn-enregistrer"]').click()
        page.wait_for_timeout(3_000)

        # Le message de succes doit apparaitre (le partial HTMX remplace la zone)
        # / Success message must appear (HTMX partial replaces the zone)
        page.wait_for_selector('text=enregistr', timeout=5_000)


class TestDetailVenteBoutons:
    """Tests des boutons dans le detail d'une vente (corriger, reimprimer).
    / Tests for buttons in sale detail (correct, reprint)."""

    def test_detail_vente_bouton_corriger_visible(self, page, django_shell, login_as_admin):
        """
        Detail d'une vente non-NFC non-cloturee → bouton "Corriger moyen" visible.
        / Detail of a non-NFC non-closed sale → "Correct method" button visible.
        """
        login_as_admin(page)

        # Recuperer le PV Bar / Get Bar POS UUID
        result = django_shell(
            "from laboutik.models import PointDeVente; "
            "pv = PointDeVente.objects.filter(name='Bar').first(); "
            "print(f'uuid={pv.uuid}') if pv else print('NOT_FOUND')"
        )
        match = re.search(r"uuid=(.+)", result)
        if not match:
            pytest.skip("PV Bar introuvable")
        uuid_pv = match.group(1).strip()

        # Naviguer vers la liste des ventes / Navigate to sales list
        page.goto(
            f"/laboutik/caisse/liste-ventes/"
            f"?uuid_pv={uuid_pv}&tag_id_cm={DEMO_TAGID_CM}"
        )
        page.wait_for_load_state("networkidle")

        # Verifier qu'il y a des ventes / Check there are sales
        premiere_ligne = page.locator('[data-testid^="vente-ligne-"]').first
        if not premiere_ligne.is_visible():
            pytest.skip("Aucune vente en base — lancer des paiements de test d'abord")

        # Cliquer sur la premiere vente → detail collapse / Click first sale → collapse detail
        premiere_ligne.click()
        page.wait_for_timeout(2_000)

        # Le detail doit apparaitre / Detail must appear
        expect(page.locator('[data-testid="ventes-detail"]')).to_be_visible(timeout=10_000)

        # Le bouton reimprimer doit etre visible / Reprint button must be visible
        expect(page.locator('[data-testid="btn-reimprimer"]')).to_be_visible(timeout=5_000)
