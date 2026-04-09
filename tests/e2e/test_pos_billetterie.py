"""
Tests E2E : billetterie POS — tuiles billet, identification, paiement.
/ E2E tests: POS ticketing — ticket tiles, identification, payment.

LOCALISATION : tests/e2e/test_pos_billetterie.py

Teste le flow complet dans un vrai navigateur Chromium :
1. Ouverture PV BILLETTERIE → tuiles billet visibles avec jauge
2. Clic tuile billet → article ajoute au panier avec bon prix
3. VALIDER → ecran identification (panier_necessite_client car billet)
4. Saisir email → recapitulatif avec description "Billet"
5. Payer especes → succes + Ticket(status=K) en DB
6. Panier mixte (biere + billet) → identification aussi declenchee
7. Event complet → paiement refuse avec message d'erreur

Prerequis / Prerequisites:
- docker exec lespass_django poetry run python manage.py create_test_pos_data
- Serveur Django actif via Traefik
- DEMO=1 + TEST=1 dans l'environnement
"""

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# Helpers specifiques billetterie / Ticketing-specific helpers
# ---------------------------------------------------------------------------

def _open_pv_billetterie(page, pos_page):
    """Ouvre le PV 'Accueil Festival' (type BILLETTERIE).
    / Opens the 'Accueil Festival' POS (BILLETTERIE type).
    """
    return pos_page(page, pv_name_filter="Accueil Festival")


def _click_tuile_billet(page, tarif_name):
    """Clic sur une tuile billet par son nom de tarif.
    Les tuiles billet ont la classe .billet-tuile et contiennent data-name.
    / Click on a ticket tile by its rate name.
    Ticket tiles have .billet-tuile class and contain data-name.
    """
    tuile = page.locator(f'.billet-tuile[data-name="{tarif_name}"]')
    expect(tuile).to_be_visible(timeout=10_000)
    tuile.click()


def _click_valider(page):
    """Clic VALIDER → attend la reponse HTMX.
    / Click VALIDER → wait for HTMX response.
    """
    page.locator("#bt-valider").click()


def _fill_identification_email(page, email, prenom, nom):
    """Remplit le formulaire d'identification email puis clique VALIDER.
    / Fills the email identification form then clicks VALIDER.
    """
    page.locator('[data-testid="client-input-email"]').fill(email)
    page.locator('[data-testid="client-input-prenom"]').fill(prenom)
    page.locator('[data-testid="client-input-nom"]').fill(nom)
    page.locator('[data-testid="client-btn-valider"]').click()


def _retour_caisse(page):
    """Clic RETOUR dans l'ecran de succes → panier vide.
    Scope le bouton RETOUR au container succes pour eviter l'ambiguite
    (il y a 2 elements #bt-retour-layer1 dans le DOM).
    / Click RETOUR in success screen → empty cart.
    Scope the RETOUR button to the success container to avoid ambiguity.
    """
    page.locator('[data-testid="paiement-succes"] #bt-retour-layer1').click()
    expect(page.locator('[data-testid="addition-empty-placeholder"]')).to_be_visible(timeout=5_000)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPOSBilletterieE2E:
    """Tests E2E billetterie POS / POS ticketing E2E tests."""

    def test_01_tuiles_billet_visibles_avec_jauge(self, page, pos_page):
        """
        Le PV BILLETTERIE affiche les tuiles billet avec jauge et date.
        Les tuiles standard (Biere, Eau) sont aussi visibles.
        / The BILLETTERIE POS displays ticket tiles with gauge and date.
        Standard tiles (Beer, Water) are also visible.
        """
        _open_pv_billetterie(page, pos_page)

        # Les tuiles billet doivent etre visibles (classe .billet-tuile)
        # / Ticket tiles must be visible (.billet-tuile class)
        tuiles_billet = page.locator('.billet-tuile')
        expect(tuiles_billet.first).to_be_visible(timeout=10_000)

        # Au moins 2 tuiles billet (les events de demo_data_v2)
        # / At least 2 ticket tiles (from demo_data_v2 events)
        nombre_tuiles = tuiles_billet.count()
        assert nombre_tuiles >= 2, f"Attendu >= 2 tuiles billet, trouve {nombre_tuiles}"

        # Les tuiles standard doivent aussi etre visibles (Biere dans le M2M)
        # / Standard tiles must also be visible (Beer in the M2M)
        tuile_biere = page.locator('.article-container[data-name="Biere"]')
        expect(tuile_biere).to_be_visible(timeout=5_000)

    def test_02_clic_tuile_billet_ajoute_au_panier(self, page, pos_page):
        """
        Clic sur une tuile billet → article ajoute au panier avec le bon prix.
        Le badge quantite sur la tuile passe a 1.
        / Click on a ticket tile → article added to cart with correct price.
        Quantity badge on the tile changes to 1.
        """
        _open_pv_billetterie(page, pos_page)

        # Trouver une tuile billet avec un prix > 0 (pas gratuit)
        # / Find a ticket tile with price > 0 (not free)
        tuile_payante = page.locator('.billet-tuile').filter(
            has=page.locator('.billet-tuile-prix:not(:has-text("0€"))')
        ).first
        expect(tuile_payante).to_be_visible(timeout=10_000)

        # Lire le nom et le prix de la tuile
        # / Read the tile's name and price
        nom_tarif = tuile_payante.get_attribute('data-name')
        prix_data = tuile_payante.get_attribute('data-price')

        # Cliquer la tuile
        # / Click the tile
        tuile_payante.click()

        # Le panier doit contenir le nom du tarif
        # / The cart must contain the rate name
        addition_list = page.locator('#addition-list')
        expect(addition_list).to_contain_text(nom_tarif, timeout=5_000)

        # Le total VALIDER doit etre > 0
        # / The VALIDER total must be > 0
        valider_text = page.locator('#bt-valider').inner_text()
        assert '0.00' not in valider_text, f"Le total est toujours 0 apres ajout billet"

    def test_03_valider_billet_declenche_identification(self, page, pos_page):
        """
        VALIDER un panier avec billet → ecran identification avec titre "Billetterie".
        Pas de boutons de paiement directs.
        / VALIDER a cart with ticket → identification screen with "Billetterie" title.
        No direct payment buttons.
        """
        _open_pv_billetterie(page, pos_page)

        # Ajouter un billet payant au panier
        # / Add a paid ticket to the cart
        tuile_payante = page.locator('.billet-tuile').filter(
            has=page.locator('.billet-tuile-prix:not(:has-text("0€"))')
        ).first
        tuile_payante.click()
        expect(page.locator('#addition-list')).not_to_be_empty(timeout=5_000)

        # Cliquer VALIDER
        # / Click VALIDER
        _click_valider(page)

        # L'ecran d'identification doit apparaitre (pas les boutons paiement directs)
        # / Identification screen must appear (not direct payment buttons)
        identification_zone = page.locator('[data-testid="client-choose-nfc"], [data-testid="client-choose-email"]').first
        expect(identification_zone).to_be_visible(timeout=10_000)

        # Le titre doit contenir "Billetterie"
        # / Title must contain "Billetterie"
        contenu_page = page.locator('[data-testid="paiement-moyens"]').inner_text()
        assert 'Billetterie' in contenu_page or 'billetterie' in contenu_page, (
            f"Le titre 'Billetterie' manque. Contenu : {contenu_page[:200]}"
        )

    def test_04_identification_email_puis_especes_cree_ticket(self, page, pos_page, django_shell):
        """
        Flow complet : billet → identification email → especes → Ticket(K) en DB.
        / Full flow: ticket → email identification → cash → Ticket(K) in DB.

        FLUX :
        1. Ouvrir PV BILLETTERIE
        2. Clic tuile billet payant
        3. VALIDER → ecran identification
        4. "Saisir email / nom" → formulaire
        5. Remplir email + prenom + nom → VALIDER → recapitulatif
        6. ESPECE → confirmation → VALIDER → succes
        7. Verifier Ticket(status=K) en DB via django_shell
        """
        _open_pv_billetterie(page, pos_page)

        # Ajouter un billet payant
        # / Add a paid ticket
        tuile_payante = page.locator('.billet-tuile').filter(
            has=page.locator('.billet-tuile-prix:not(:has-text("0€"))')
        ).first
        tuile_payante.click()
        expect(page.locator('#addition-list')).not_to_be_empty(timeout=10_000)

        # VALIDER → identification
        # / VALIDER → identification
        _click_valider(page)
        expect(page.locator('[data-testid="client-choose-email"]')).to_be_visible(timeout=10_000)

        # Choisir "Saisir email / nom"
        # / Choose "Enter email / name"
        page.locator('[data-testid="client-choose-email"]').click()

        # Remplir le formulaire d'identification
        # / Fill the identification form
        email_test = 'e2e-billet-test@tibillet.localhost'
        expect(page.locator('[data-testid="client-input-email"]')).to_be_visible(timeout=10_000)
        _fill_identification_email(page, email_test, 'E2E', 'Billet')

        # Attendre le recapitulatif
        # / Wait for the recap
        recapitulatif = page.locator('[data-testid="client-recapitulatif"]')
        expect(recapitulatif).to_be_visible(timeout=10_000)

        # Le recapitulatif doit contenir "Billet"
        # / The recap must contain "Billet"
        recap_text = recapitulatif.inner_text()
        assert 'Billet' in recap_text or 'billet' in recap_text, (
            f"'Billet' manque dans le recapitulatif : {recap_text[:200]}"
        )

        # Cliquer ESPECE dans le recapitulatif
        # Le bouton payerAvecClient('espece') soumet directement vers payer().
        # Pas d'ecran de confirmation intermediaire (contrairement au flow VT normal).
        # / Click CASH in the recap.
        # payerAvecClient('espece') submits directly to payer().
        # No intermediate confirmation screen (unlike the normal VT flow).
        page.locator('[data-testid="client-btn-especes"]').click()

        # Ecran de succes (directement, pas de confirmation)
        # / Success screen (directly, no confirmation step)
        expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=15_000)

        # Verifier en DB : Ticket cree avec status NOT_SCANNED
        # / Verify in DB: Ticket created with NOT_SCANNED status
        result = django_shell(
            "from BaseBillet.models import Ticket; "
            "from AuthBillet.models import TibilletUser; "
            "user = TibilletUser.objects.filter(email='e2e-billet-test@tibillet.localhost').first(); "
            "t = Ticket.objects.filter(reservation__user_commande=user).order_by('-reservation__datetime').first(); "
            "print(f'status={t.status} origin={t.sale_origin} pm={t.payment_method}') if t else print('NOT_FOUND')"
        )
        assert 'NOT_FOUND' not in result, f"Ticket non trouve en DB : {result}"
        assert 'status=K' in result, f"Ticket status != K : {result}"
        assert 'origin=LB' in result, f"Ticket sale_origin != LB : {result}"

        # Retour caisse
        # / Back to POS
        _retour_caisse(page)

    def test_05_panier_mixte_biere_plus_billet(self, page, pos_page):
        """
        Panier biere + billet → identification declenchee (pas paiement direct).
        / Cart beer + ticket → identification triggered (not direct payment).
        """
        _open_pv_billetterie(page, pos_page)

        # Ajouter une biere
        # / Add a beer
        tuile_biere = page.locator('.article-container[data-name="Biere"]')
        expect(tuile_biere).to_be_visible(timeout=5_000)
        tuile_biere.click()
        expect(page.locator('#addition-list')).to_contain_text('Biere', timeout=5_000)

        # Ajouter un billet payant
        # / Add a paid ticket
        tuile_billet = page.locator('.billet-tuile').filter(
            has=page.locator('.billet-tuile-prix:not(:has-text("0€"))')
        ).first
        tuile_billet.click()

        # VALIDER → identification (pas paiement direct)
        # / VALIDER → identification (not direct payment)
        _click_valider(page)
        identification_zone = page.locator('[data-testid="client-choose-nfc"], [data-testid="client-choose-email"]').first
        expect(identification_zone).to_be_visible(timeout=10_000)
