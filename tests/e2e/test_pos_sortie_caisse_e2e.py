"""
Tests E2E : Sortie de caisse — parcours complet avec verification DB et solde.
/ E2E tests: Cash withdrawal — full flow with DB verification and balance check.

Session 17 — Fond de caisse et sortie de caisse.

Ce test verifie :
1. Que le formulaire de sortie de caisse est accessible et fonctionnel
2. Que la SortieCaisse est bien creee en base de donnees
3. Que le fond de caisse est modifiable
4. Que le Ticket X reflete le solde correct apres une sortie

/ This test verifies:
1. Cash withdrawal form is accessible and functional
2. SortieCaisse is properly created in the database
3. Cash float is modifiable
4. Ticket X reflects the correct balance after a withdrawal

Prerequis / Prerequisites:
- docker exec lespass_django poetry run python manage.py create_test_pos_data
- Serveur Django actif via Traefik

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/e2e/test_pos_sortie_caisse_e2e.py -v -s
"""

import os
import re
import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e

DEMO_TAGID_CM = os.environ.get("DEMO_TAGID_CM", "A49E8E2A")


def _get_pv_bar_uuid(django_shell):
    """Recupere l'UUID du PV Bar. / Gets the Bar POS UUID."""
    result = django_shell(
        "from laboutik.models import PointDeVente; "
        "pv = PointDeVente.objects.filter(name='Bar').first(); "
        "print(f'uuid={pv.uuid}') if pv else print('NOT_FOUND')"
    )
    match = re.search(r"uuid=(.+)", result)
    if not match:
        pytest.fail(f"PV Bar introuvable: {result}")
    return match.group(1).strip()


def _open_ventes_toutes(page, pv_uuid):
    """Navigue vers le Ticket X (recap en cours, vue toutes).
    / Navigate to Ticket X (current recap, all view).
    """
    page.goto(
        f"/laboutik/caisse/recap-en-cours/"
        f"?vue=toutes&uuid_pv={pv_uuid}&tag_id_cm={DEMO_TAGID_CM}"
    )
    page.wait_for_load_state("networkidle")


def _make_cash_sale(page, pos_page, pv_name="Bar"):
    """Fait une vente especes sur le POS pour alimenter le solde caisse.
    / Makes a cash sale on the POS to feed the cash drawer balance.
    """
    pos_page(page, pv_name)

    # Cliquer sur la tuile Biere / Click the Beer tile
    tile = page.locator("#products .article-container").filter(has_text="Biere").first
    expect(tile).to_be_visible(timeout=10_000)
    tile.click()
    expect(page.locator("#addition-list")).to_contain_text("Biere", timeout=10_000)

    # Valider / Validate
    page.locator("#bt-valider").click()
    expect(page.locator('[data-testid="paiement-moyens"]')).to_be_visible(timeout=10_000)

    # Payer en especes / Pay with cash
    page.locator('[data-testid="paiement-moyens"]').get_by_text("ESPÈCE").click()
    expect(page.locator('[data-testid="paiement-confirmation"]')).to_be_visible(timeout=10_000)
    page.locator("#bt-valider-layer2").click()
    expect(page.locator('[data-testid="paiement-succes"]')).to_be_visible(timeout=15_000)


class TestSortieDeCaisseE2E:
    """Tests E2E complets de la sortie de caisse avec verification en DB.
    / Full E2E tests of cash withdrawal with DB verification."""

    def test_01_fond_de_caisse_modification_et_verification_db(
        self, page, django_shell, login_as_admin, pos_page
    ):
        """
        Modifie le fond de caisse a 100€ via le Ticket X et verifie en DB.
        / Sets cash float to 100€ via Ticket X and verifies in DB.
        """
        # Supprimer les sorties de caisse existantes pour un etat propre
        # / Delete existing cash withdrawals for a clean state
        django_shell(
            "from laboutik.models import SortieCaisse; "
            "SortieCaisse.objects.all().delete(); "
            "print('cleaned')"
        )

        # On a besoin de ventes pour voir la section "Gestion caisse"
        # / We need sales to see the "Cash management" section
        _make_cash_sale(page, pos_page, "Bar")

        pv_uuid = _get_pv_bar_uuid(django_shell)
        _open_ventes_toutes(page, pv_uuid)
        expect(page.locator('[data-testid="recap-solde"]')).to_be_visible(timeout=10_000)

        # Cliquer "Fond de caisse" / Click "Cash float"
        page.locator('[data-testid="btn-fond-de-caisse"]').click()
        expect(page.locator('[data-testid="fond-de-caisse"]')).to_be_visible(timeout=10_000)

        # Saisir 100€ / Enter 100€
        input_montant = page.locator('[data-testid="fond-input-montant"]')
        input_montant.fill("100.00")

        # Enregistrer / Save
        page.locator('[data-testid="fond-btn-enregistrer"]').click()

        # Verifier le message de succes / Verify success message
        expect(page.locator('[data-testid="fond-message-succes"]')).to_be_visible(timeout=10_000)

        # Verifier en DB que le fond vaut 10000 centimes / Verify in DB that float is 10000 cents
        result = django_shell(
            "from laboutik.models import LaboutikConfiguration; "
            "config = LaboutikConfiguration.get_solo(); "
            "print(f'fond={config.fond_de_caisse}')"
        )
        assert "fond=10000" in result, f"Fond de caisse attendu 10000, obtenu: {result}"

    def test_02_vente_especes_puis_sortie_caisse_complete(
        self, page, django_shell, login_as_admin, pos_page
    ):
        """
        Parcours complet :
        1. Fait une vente especes sur le POS
        2. Ouvre le Ticket X et verifie le solde caisse
        3. Fait une sortie de caisse (1 × 5€ = 5€)
        4. Verifie la SortieCaisse en DB (montant, ventilation, note)
        5. Retour au Ticket X : la ligne "Sorties especes" apparait

        / Full flow:
        1. Cash sale on POS
        2. Open Ticket X and check cash balance
        3. Cash withdrawal (1 × 5€ = 5€)
        4. Verify SortieCaisse in DB (amount, breakdown, note)
        5. Back to Ticket X: "Cash withdrawals" row appears
        """
        # Nettoyer les sorties precedentes / Clean previous withdrawals
        django_shell(
            "from laboutik.models import SortieCaisse; "
            "SortieCaisse.objects.all().delete(); "
            "print('cleaned')"
        )

        # Mettre le fond de caisse a 100€ / Set cash float to 100€
        django_shell(
            "from laboutik.models import LaboutikConfiguration; "
            "config = LaboutikConfiguration.get_solo(); "
            "config.fond_de_caisse = 10000; "
            "config.save(); "
            "print('fond=10000')"
        )

        # Etape 1 : Vente especes sur le POS (biere 5€)
        # Si le test_01 a deja fait une vente, celle-ci s'ajoute (pas de rollback E2E).
        # / Step 1: Cash sale on POS (beer 5€)
        _make_cash_sale(page, pos_page, "Bar")

        # Etape 2 : Ouvrir le Ticket X et lire le solde caisse
        # / Step 2: Open Ticket X and read cash balance
        pv_uuid = _get_pv_bar_uuid(django_shell)
        _open_ventes_toutes(page, pv_uuid)

        # Verifier que le solde caisse est affiche / Verify cash balance is shown
        expect(page.locator('[data-testid="recap-solde"]')).to_be_visible(timeout=10_000)

        # Etape 3 : Cliquer "Sortie de caisse" / Step 3: Click "Cash withdrawal"
        page.locator('[data-testid="btn-sortie-de-caisse"]').click()
        expect(page.locator('[data-testid="sortie-de-caisse"]')).to_be_visible(timeout=10_000)

        # Saisir 1 × 5€ via le bouton + (5€ = centimes 500)
        # Le montant de 5€ est <= aux especes encaissees (1 biere = 5€)
        # donc la validation JS laisse passer sans alerte.
        # / Enter 1 × 5€ via + button. 5€ <= cash sales so no JS alert.
        input_5 = page.locator('[data-testid="sortie-input-500"]')
        expect(input_5).to_be_visible(timeout=10_000)
        page.locator('[data-testid="sortie-btn-plus-500"]').click()

        # Verifier que le total JS affiche 5,00 € / Verify JS total shows 5,00 €
        total_affiche = page.locator('[data-testid="sortie-total"]').text_content()
        assert "5,00" in total_affiche, f"Total attendu 5,00 €, obtenu: {total_affiche}"

        # Ajouter une note / Add a note
        page.locator('[data-testid="sortie-textarea-note"]').fill("Test E2E sortie")

        # Soumettre / Submit
        page.locator('[data-testid="sortie-btn-enregistrer"]').click()

        # Ecran de succes / Success screen
        expect(page.locator('[data-testid="sortie-succes"]')).to_be_visible(timeout=10_000)

        # Etape 4 : Verifier en DB / Step 4: Verify in DB
        result_db = django_shell(
            "from laboutik.models import SortieCaisse; "
            "sortie = SortieCaisse.objects.order_by('-datetime').first(); "
            "print("
            "    f'montant={sortie.montant_total}|'"
            "    f'note={sortie.note}|'"
            "    f'ventilation={sortie.ventilation}'"
            ")"
        )
        assert "montant=500" in result_db, f"Montant attendu 500 centimes: {result_db}"
        assert "Test E2E sortie" in result_db, f"Note non trouvee: {result_db}"
        # La ventilation doit contenir 500: 1
        # / Breakdown must contain 500: 1
        assert "'500': 1" in result_db or '"500": 1' in result_db, (
            f"Ventilation 500:1 non trouvee: {result_db}"
        )

        # Etape 5 : Retour au Ticket X et verification du solde
        # / Step 5: Back to Ticket X and balance verification
        page.locator('[data-testid="btn-retour-recap"]').click()
        expect(page.locator('[data-testid="recap-solde"]')).to_be_visible(timeout=10_000)

        # La ligne "Sorties especes" doit etre visible / "Cash withdrawals" row must be visible
        expect(page.locator('[data-testid="recap-sorties-especes"]')).to_be_visible(timeout=10_000)
        sorties_texte = page.locator('[data-testid="recap-sorties-especes"]').text_content()
        assert "5,00" in sorties_texte, (
            f"Sorties especes attendu 5,00 €, obtenu: {sorties_texte}"
        )

    def test_03_boutons_plus_moins_fonctionnent(
        self, page, django_shell, login_as_admin
    ):
        """
        Les boutons + et - incrementent et decrementent la quantite.
        Le bouton - ne descend pas en dessous de 0.
        / + and - buttons increment and decrement the quantity.
        - button does not go below 0.
        """
        login_as_admin(page)
        pv_uuid = _get_pv_bar_uuid(django_shell)

        page.goto(f"/laboutik/caisse/sortie-de-caisse/?uuid_pv={pv_uuid}")
        page.wait_for_load_state("networkidle")

        # Bouton + sur 50€ (centimes 5000) trois fois / Click + on 50€ three times
        for _ in range(3):
            page.locator('[data-testid="sortie-btn-plus-5000"]').click()

        input_50 = page.locator('[data-testid="sortie-input-5000"]')
        assert input_50.input_value() == "3", f"Valeur attendue 3, obtenue: {input_50.input_value()}"

        # Total doit afficher 150,00 € / Total must show 150,00 €
        total = page.locator('[data-testid="sortie-total"]').text_content()
        assert "150,00" in total, f"Total attendu 150,00 €, obtenu: {total}"

        # Bouton - deux fois → 1 / Click - twice → 1
        page.locator('[data-testid="sortie-btn-moins-5000"]').click()
        page.locator('[data-testid="sortie-btn-moins-5000"]').click()
        assert input_50.input_value() == "1", f"Valeur attendue 1, obtenue: {input_50.input_value()}"

        # Bouton - encore → 0, puis encore → reste a 0 (pas de negatif)
        # / Click - again → 0, then again → stays at 0 (no negative)
        page.locator('[data-testid="sortie-btn-moins-5000"]').click()
        assert input_50.input_value() == "0"
        page.locator('[data-testid="sortie-btn-moins-5000"]').click()
        assert input_50.input_value() == "0", "Le bouton - ne doit pas descendre en dessous de 0"

    def test_04_etat_caisse_affiche_dans_formulaire(
        self, page, django_shell, login_as_admin
    ):
        """
        Le formulaire de sortie affiche fond, especes et solde.
        / The withdrawal form displays float, cash sales and balance.
        """
        login_as_admin(page)
        pv_uuid = _get_pv_bar_uuid(django_shell)

        page.goto(f"/laboutik/caisse/sortie-de-caisse/?uuid_pv={pv_uuid}")
        page.wait_for_load_state("networkidle")

        # Le panneau etat caisse est visible / Cash state panel is visible
        expect(page.locator('[data-testid="sortie-etat-caisse"]')).to_be_visible(timeout=10_000)

        # Il contient au moins "Fond"/"Float" et "Solde"/"Balance" (selon langue
        # active du tenant — i18n, cf. PIEGES 9.34).
        # / It contains at least "Fond"/"Float" and "Solde"/"Balance" (depending
        # on tenant's active language — i18n, see PIEGES 9.34).
        etat_texte = page.locator('[data-testid="sortie-etat-caisse"]').text_content()
        assert "Fond" in etat_texte or "Float" in etat_texte, (
            f"'Fond'/'Float' non trouvé dans: {etat_texte}"
        )
        assert "Solde" in etat_texte or "Balance" in etat_texte, (
            f"'Solde'/'Balance' non trouvé dans: {etat_texte}"
        )
