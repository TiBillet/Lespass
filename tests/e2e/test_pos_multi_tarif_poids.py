"""
Tests E2E : overlay multi-tarif multi-clic + pave numerique poids/mesure.
/ E2E tests: multi-rate overlay multi-click + weight/volume numpad.

LOCALISATION : tests/e2e/test_pos_multi_tarif_poids.py

Teste les 4 articles de fixture :
- Blonde Pression (Pinte + Demi) : multi-clic tarif fixe
- Affiche A4 (Standard + Prix libre) : prix libre montants differents = lignes separees
- Cacahuetes en vrac (12E/kg, stock GR) : pave numerique poids/mesure
- Vin en vrac (8E/L, stock CL) : pave numerique unite CL

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


# ---------------------------------------------------------------------------
# Helpers / Utilitaires
# ---------------------------------------------------------------------------

def _open_overlay(page, article_name):
    """Clique sur une tuile article pour ouvrir l'overlay tarif.
    Attend que l'overlay soit visible.
    / Clicks an article tile to open the rate overlay.
    Waits for the overlay to be visible."""
    tile = page.locator("#products .article-container").filter(has_text=article_name).first
    expect(tile).to_be_visible(timeout=10_000)
    tile.click()
    expect(page.locator('[data-testid="tarif-overlay"]')).to_be_visible(timeout=5_000)


def _close_overlay(page):
    """Ferme l'overlay avec le bouton RETOUR.
    / Closes the overlay with the RETOUR button."""
    page.locator('[data-testid="tarif-btn-retour"]').click()
    expect(page.locator('[data-testid="tarif-overlay"]')).not_to_be_visible(timeout=5_000)


def _count_addition_lines(page):
    """Compte le nombre de lignes dans le panier.
    / Counts the number of lines in the cart."""
    return page.locator("#addition-list .addition-line-grid").count()


def _addition_total_text(page):
    """Recupere le texte du total du panier.
    / Gets the cart total text."""
    return page.locator("#addition-total-display").inner_text()


def _pay_especes_and_return(page):
    """Valider → Especes → Confirmer → Succes → Retour.
    / Validate → Cash → Confirm → Success → Return."""
    page.locator("#bt-valider").click()
    expect(page.locator('[data-testid="paiement-moyens"]')).to_be_visible(timeout=10_000)

    # Cliquer ESPECE / Click CASH
    page.locator('[data-testid="paiement-moyens"]').get_by_text("ESPÈCE").click()
    expect(page.locator('[data-testid="paiement-confirmation"]')).to_be_visible(timeout=10_000)

    # Confirmer / Confirm
    page.locator("#bt-valider-layer2").click()
    expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=15_000)

    # Retour / Return
    page.locator('[data-testid="paiement-succes"] #bt-retour-layer1').click()
    expect(page.locator('[data-testid="paiement-succes"]')).not_to_be_visible(timeout=5_000)


# ===========================================================================
# Test 1 : Multi-clic tarif fixe (Blonde Pression)
# ===========================================================================


class TestOverlayMultiClicFixe:
    """L'overlay reste ouvert apres chaque clic sur un tarif fixe.
    Le panier se met a jour en temps reel.
    / Overlay stays open after each fixed-rate click.
    Cart updates in real time."""

    def test_01_multi_clic_pinte_demi(self, page, pos_page):
        """3 demis + 1 pinte dans l'overlay sans le fermer.
        / 3 half-pints + 1 pint in the overlay without closing it."""
        pos = pos_page(page, "Bar")

        _open_overlay(pos, "Blonde Pression")

        # Cliquer 3x Demi / Click Demi 3 times
        demi_btn = pos.locator('[data-testid="tarif-overlay"]').get_by_text("Demi").first
        for _ in range(3):
            demi_btn.click()

        # Cliquer 1x Pinte / Click Pinte once
        pinte_btn = pos.locator('[data-testid="tarif-overlay"]').get_by_text("Pinte").first
        pinte_btn.click()

        # L'overlay doit toujours etre visible (pas ferme apres le clic)
        # / Overlay must still be visible (not closed after click)
        expect(pos.locator('[data-testid="tarif-overlay"]')).to_be_visible()

        # Fermer l'overlay / Close the overlay
        _close_overlay(pos)

        # Verifier le panier : 2 lignes (Demi x3 + Pinte x1)
        # / Verify cart: 2 lines (Demi x3 + Pinte x1)
        expect(pos.locator("#addition-list")).to_contain_text("Demi")
        expect(pos.locator("#addition-list")).to_contain_text("Pinte")
        # Note : le badge quantite sur la tuile n'est pas mis a jour
        # car l'overlay remplace temporairement #products (le badge n'est
        # plus dans le DOM pendant l'overlay). C'est un comportement attendu.
        # / Note: tile quantity badge is not updated because the overlay
        # temporarily replaces #products (badge not in DOM during overlay).


# ===========================================================================
# Test 2 : Prix libre montants differents (Affiche A4)
# ===========================================================================


class TestOverlayPrixLibreDifferents:
    """Deux saisies de prix libre avec des montants differents creent
    deux lignes separees dans le panier (pas un increment).
    / Two free-price entries with different amounts create
    two separate cart lines (not an increment)."""

    def test_02_prix_libre_deux_montants(self, page, pos_page):
        """Prix libre 10E puis 25E = 2 lignes separees.
        / Free price 10E then 25E = 2 separate lines."""
        pos = pos_page(page, "Bar")

        _open_overlay(pos, "Affiche A4")

        # Trouver le bouton prix libre et son input
        # / Find the free price button and its input
        overlay = pos.locator('[data-testid="tarif-overlay"]')

        # Saisir 10E / Enter 10E
        free_input = overlay.locator('.tarif-free-input').first
        free_input.fill("10")
        overlay.locator('.tarif-free-validate').first.click()

        # L'overlay reste ouvert — saisir 25E / Overlay stays open — enter 25E
        expect(overlay).to_be_visible()
        free_input = overlay.locator('.tarif-free-input').first
        free_input.fill("25")
        overlay.locator('.tarif-free-validate').first.click()

        _close_overlay(pos)

        # Verifier : 2 lignes separees dans le panier, pas 1 ligne x2
        # / Verify: 2 separate lines in the cart, not 1 line x2
        lines_count = _count_addition_lines(pos)
        assert lines_count == 2, f"Attendu 2 lignes, obtenu {lines_count}"


# ===========================================================================
# Test 3 : Pave numerique poids/mesure (Cacahuetes en vrac)
# ===========================================================================


class TestPaveNumeriquePoidsMesure:
    """Le pave numerique permet de saisir un poids et calcule le prix.
    / The numpad allows entering a weight and calculates the price."""

    def test_03_saisie_poids_cacahuetes(self, page, pos_page):
        """Saisir 350g de cacahuetes a 12E/kg = 4,20E.
        / Enter 350g of peanuts at 12E/kg = 4.20E."""
        pos = pos_page(page, "Bar")

        _open_overlay(pos, "Cacahuetes en vrac")

        overlay = pos.locator('[data-testid="tarif-overlay"]')

        # Verifier que le prix de reference est affiche / Check reference price shown
        expect(overlay).to_contain_text("/kg")

        # Taper 350 sur le pave numerique / Type 350 on the numpad
        numpad = overlay.locator('.tarif-numpad-grid').first
        numpad.locator('button:has-text("3")').click()
        numpad.locator('button:has-text("5")').click()
        numpad.locator('button:has-text("0")').click()

        # Verifier le calcul en temps reel : 350 / 1000 * 12.00 = 4.20
        # / Verify real-time calculation: 350 / 1000 * 12.00 = 4.20
        total_display = overlay.locator('.tarif-numpad-total').first
        expect(total_display).to_contain_text("4,20")

        # Cliquer OK / Click OK
        numpad.locator('.tarif-numpad-btn-ok').click()

        # Verifier que le panier contient la ligne avec 350g
        # / Verify cart contains the line with 350g
        expect(pos.locator("#addition-list")).to_contain_text("350g")

        # L'overlay reste ouvert pour une nouvelle pesee
        # / Overlay stays open for a new weighing
        expect(overlay).to_be_visible()

        _close_overlay(pos)

    def test_04_deux_pesees_differentes(self, page, pos_page):
        """Deux pesees (350g + 200g) creent 2 lignes separees.
        / Two weighings (350g + 200g) create 2 separate lines."""
        pos = pos_page(page, "Bar")

        _open_overlay(pos, "Cacahuetes en vrac")

        overlay = pos.locator('[data-testid="tarif-overlay"]')
        numpad = overlay.locator('.tarif-numpad-grid').first

        # Premiere pesee : 350g / First weighing: 350g
        numpad.locator('button:has-text("3")').click()
        numpad.locator('button:has-text("5")').click()
        numpad.locator('button:has-text("0")').click()
        numpad.locator('.tarif-numpad-btn-ok').click()

        # Deuxieme pesee : 200g / Second weighing: 200g
        numpad.locator('button:has-text("2")').click()
        numpad.locator('button:has-text("0")').click()
        numpad.locator('button:has-text("0")').click()
        numpad.locator('.tarif-numpad-btn-ok').click()

        _close_overlay(pos)

        # 2 lignes separees (pas 1 ligne a qty=2)
        # / 2 separate lines (not 1 line with qty=2)
        lines_count = _count_addition_lines(pos)
        assert lines_count == 2, f"Attendu 2 lignes, obtenu {lines_count}"

    def test_05_bouton_c_efface_saisie(self, page, pos_page):
        """Le bouton C efface la saisie en cours.
        / The C button clears the current input."""
        pos = pos_page(page, "Bar")

        _open_overlay(pos, "Cacahuetes en vrac")

        overlay = pos.locator('[data-testid="tarif-overlay"]')
        numpad = overlay.locator('.tarif-numpad-grid').first

        # Taper 42 puis C → revient a 0
        # / Type 42 then C → back to 0
        numpad.locator('button:has-text("4")').click()
        numpad.locator('button:has-text("2")').click()

        value_display = overlay.locator('.tarif-numpad-value').first
        expect(value_display).to_have_text("42")

        numpad.locator('.tarif-numpad-btn-clear').click()
        expect(value_display).to_have_text("0")

        _close_overlay(pos)


# ===========================================================================
# Test 4 : Vin en vrac (unite CL)
# ===========================================================================


class TestPaveNumeriqueCL:
    """Le pave numerique fonctionne aussi en centilitres.
    / The numpad also works in centiliters."""

    def test_06_saisie_volume_vin(self, page, pos_page):
        """Saisir 75cl de vin a 8E/L = 6,00E.
        / Enter 75cl of wine at 8E/L = 6.00E."""
        pos = pos_page(page, "Bar")

        _open_overlay(pos, "Vin en vrac")

        overlay = pos.locator('[data-testid="tarif-overlay"]')

        # Verifier unite et prix de reference / Check unit and reference price
        expect(overlay).to_contain_text("/L")

        numpad = overlay.locator('.tarif-numpad-grid').first

        # Taper 75 / Type 75
        numpad.locator('button:has-text("7")').click()
        numpad.locator('button:has-text("5")').click()

        # Verifier calcul : 75 / 100 * 8.00 = 6.00
        # / Verify calculation: 75 / 100 * 8.00 = 6.00
        total_display = overlay.locator('.tarif-numpad-total').first
        expect(total_display).to_contain_text("6,00")

        numpad.locator('.tarif-numpad-btn-ok').click()

        # Verifier panier / Verify cart
        expect(pos.locator("#addition-list")).to_contain_text("75cl")

        _close_overlay(pos)


# ===========================================================================
# Test 5 : Tuile icone balance
# ===========================================================================


class TestTuileIconeBalance:
    """Les articles au poids affichent l'icone balance et le prix /kg ou /L.
    / Weight-based articles show the balance icon and price /kg or /L."""

    def test_07_tuile_cacahuetes_icone_balance(self, page, pos_page):
        """La tuile Cacahuetes en vrac affiche l'icone balance.
        / The Cacahuetes en vrac tile shows the balance icon."""
        pos = pos_page(page, "Bar")

        tile = pos.locator("#products .article-container").filter(
            has_text="Cacahuetes en vrac"
        ).first
        expect(tile).to_be_visible(timeout=10_000)

        # Verifier l'icone balance / Check balance icon
        balance_icon = tile.locator("i.fa-balance-scale")
        expect(balance_icon).to_be_visible()

        # Verifier le prix de reference /kg / Check reference price /kg
        expect(tile).to_contain_text("/kg")

    def test_08_tuile_vin_vrac_prix_par_litre(self, page, pos_page):
        """La tuile Vin en vrac affiche /L.
        / The Vin en vrac tile shows /L."""
        pos = pos_page(page, "Bar")

        tile = pos.locator("#products .article-container").filter(
            has_text="Vin en vrac"
        ).first
        expect(tile).to_be_visible(timeout=10_000)
        expect(tile).to_contain_text("/L")


# ===========================================================================
# Test 6 : Paiement complet avec poids/mesure
# ===========================================================================


class TestPaiementPoidsMesure:
    """Un paiement complet avec un article au poids cree une LigneArticle
    avec weight_quantity renseigne.
    / A full payment with a weight-based article creates a LigneArticle
    with weight_quantity set."""

    def test_09_paiement_especes_cacahuetes_verifie_db(self, page, pos_page, django_shell):
        """Paiement especes 350g cacahuetes → LigneArticle.weight_quantity=350 en DB.
        / Cash payment 350g peanuts → LigneArticle.weight_quantity=350 in DB."""
        pos = pos_page(page, "Bar")

        _open_overlay(pos, "Cacahuetes en vrac")

        overlay = pos.locator('[data-testid="tarif-overlay"]')
        numpad = overlay.locator('.tarif-numpad-grid').first

        # Saisir 350g / Enter 350g
        numpad.locator('button:has-text("3")').click()
        numpad.locator('button:has-text("5")').click()
        numpad.locator('button:has-text("0")').click()
        numpad.locator('.tarif-numpad-btn-ok').click()

        _close_overlay(pos)

        # Payer en especes / Pay cash
        _pay_especes_and_return(pos)

        # Verifier en DB que weight_quantity = 350 sur la derniere LigneArticle
        # / Verify in DB that weight_quantity = 350 on the last LigneArticle
        result = django_shell(
            "from BaseBillet.models import LigneArticle; "
            "ligne = LigneArticle.objects.filter("
            "  weight_quantity__isnull=False"
            ").order_by('-datetime').first(); "
            "print(f'wq={ligne.weight_quantity},amount={ligne.amount}') if ligne else print('NONE')"
        )
        assert "wq=350" in result, f"weight_quantity attendu 350, obtenu: {result}"
        # 350g x 12E/kg = 4.20E = 420 centimes
        # / 350g x 12E/kg = 4.20E = 420 cents
        assert "amount=420" in result, (
            f"amount attendu 420 (350g x 12E/kg = 4.20E), obtenu: {result}. "
            f"Si amount=1200, le custom_amount n'est pas passe au backend."
        )
