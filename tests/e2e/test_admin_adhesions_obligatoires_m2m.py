"""
Tests E2E : adhesions obligatoires M2M sur un tarif (django-unfold).
/ E2E tests: mandatory memberships M2M on a price (django-unfold).

Conversion de tests/playwright/tests/37-admin-adhesions-obligatoires-m2m.spec.ts

Flow :
1. Creer 2 produits adhesion via /admin/BaseBillet/membershipproduct/
   / Create 2 membership products via the membershipproduct proxy
2. Creer un produit reservation gratuite via /admin/BaseBillet/ticketproduct/
   avec categorie FREERES — le signal post_save_Product genere automatiquement
   un tarif gratuit (fix proxys 2026-06-11)
   / Create a free reservation product via ticketproduct — the post_save_Product
   signal auto-creates a free price (proxy-signals fix 2026-06-11)
3. Verifier que l'inline affiche le tarif gratuit auto-cree (prix=0)
   / Verify the inline shows the auto-created free price (price=0)
4. Verifier l'absence de bouton "+" sur le widget M2M adhesions_obligatoires
   / Verify no "+" add button on the M2M adhesions_obligatoires widget
5. Ajouter 2 adhesions via le widget select2 autocomplete de l'inline tarif
   / Add 2 memberships via the select2 autocomplete widget in the price inline
6. Enregistrer et verifier que les 2 adhesions sont persistees
   / Save and verify both memberships are persisted
7. Retirer une adhesion, enregistrer, verifier que seule l'autre reste
   / Remove one membership, save, verify only the other remains

ATTENTION : ce test cree des produits dans la DB de dev partagee (sans rollback).
Les noms sont suffixes d'un identifiant aleatoire pour eviter les collisions.
/ WARNING: this test creates products in the shared dev DB (no rollback).
Names are suffixed with a random id to avoid collisions between test sessions.
"""

import re
import uuid

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


def _create_membership_product(page, name: str, prix: str) -> None:
    """Cree un produit adhesion via le proxy MembershipProduct admin.
    La categorie est fixee par le proxy (champ cache), pas besoin de la selectionner.
    / Create a membership product via the MembershipProduct proxy admin.
    The category is set by the proxy (hidden field), no selectOption needed.
    """
    page.goto('/admin/BaseBillet/membershipproduct/add/')
    page.wait_for_load_state('networkidle')
    page.fill('input[name="name"]', name)

    # Ajouter une ligne de tarif via le bouton "add-row" de l'inline #prices-group
    # / Add a price inline row via the "add-row" button in #prices-group
    prices_section = page.locator('#prices-group')
    add_btn = prices_section.locator('a.add-row').first
    add_btn.scroll_into_view_if_needed()
    add_btn.click()
    page.wait_for_timeout(500)

    page.fill('input[name="prices-0-name"]', 'Tarif annuel')
    page.fill('input[name="prices-0-prix"]', prix)
    # Y = abonnement annuel (365 jours) / Y = annual subscription (365 days)
    page.select_option('select[name="prices-0-subscription_type"]', 'Y')

    # Enregistrer (sans continuer) / Save (without continuing)
    page.locator('button[name="_save"], input[name="_save"]').first.click()
    page.wait_for_load_state('networkidle')


def _add_adhesion_select2(page, adhesion_name: str, uid: str) -> None:
    """Ajoute une adhesion via le widget select2 autocomplete de l'inline tarif.
    / Add a membership via the select2 autocomplete widget in the price inline.

    Select2 multiple genere :
    - Un <select multiple> cache avec name="prices-0-adhesions_obligatoires"
    - Un <span class="select2 ..."> avec un input de recherche
    / Select2 multiple generates:
    - A hidden <select multiple> named "prices-0-adhesions_obligatoires"
    - A visible <span class="select2 ..."> with a search input inside
    """
    # Cliquer sur la zone select2 du champ adhesions_obligatoires pour ouvrir le dropdown
    # / Click the select2 area for adhesions_obligatoires to open the dropdown
    search_area = page.locator(
        '.field-adhesions_obligatoires .select2-selection, '
        '.field-adhesions_obligatoires .select2-container'
    ).first
    search_area.click()
    page.wait_for_timeout(300)

    # L'input de recherche select2 apparait dans le dropdown (dernier .select2-search__field)
    # / The select2 search input appears in the dropdown (last .select2-search__field)
    search_input = page.locator('.select2-search__field').last
    expect(search_input).to_be_visible(timeout=3000)

    # Taper le uid pour declencher la recherche AJAX et filtrer les resultats
    # / Type the uid to trigger the AJAX search and filter the results
    search_input.fill(uid)
    page.wait_for_timeout(1000)  # Attendre la reponse AJAX / Wait for AJAX response

    # Cliquer sur le resultat correspondant / Click the matching result
    option = page.locator('.select2-results__option').filter(has_text=adhesion_name).first
    expect(option).to_be_visible(timeout=5000)
    option.click()
    page.wait_for_timeout(300)

    # Fermer le dropdown pour ne pas bloquer les interactions suivantes
    # / Close the dropdown to avoid blocking subsequent interactions
    page.keyboard.press('Escape')
    page.wait_for_timeout(200)


def _get_selected_adhesions(page) -> list:
    """Retourne la liste des adhesions selectionnees dans le widget select2.
    / Returns the list of selected memberships in the select2 widget.

    Select2 multiple affiche les items selectionnes dans des
    <li class="select2-selection__choice"> — chacun precede d'un bouton "x".
    / Select2 multiple shows selected items as
    <li class="select2-selection__choice"> — each preceded by a "x" button.
    """
    items = page.locator('.field-adhesions_obligatoires .select2-selection__choice')
    count = items.count()
    names = []
    for i in range(count):
        text = items.nth(i).text_content() or ''
        # Select2 prepend un bouton "×" (suppression) — on le supprime du texte
        # / Select2 prepends a "×" (remove) button — strip it from the text
        cleaned = re.sub(r'^[×✕×x]\s*', '', text).strip()
        if cleaned:
            names.append(cleaned)
    return names


def _remove_adhesion_select2(page, adhesion_name: str) -> None:
    """Retire une adhesion du widget select2 en cliquant sur son bouton de suppression.
    / Remove a membership from the select2 widget by clicking its remove button.
    """
    items = page.locator('.field-adhesions_obligatoires .select2-selection__choice')
    count = items.count()

    for i in range(count):
        text = items.nth(i).text_content() or ''
        if adhesion_name in text:
            # Cliquer sur le bouton "×" de cet item
            # / Click the "×" remove button of this item
            remove_btn = items.nth(i).locator('.select2-selection__choice__remove')
            remove_btn.click()
            page.wait_for_timeout(300)
            # Fermer le dropdown s'il reste ouvert apres la suppression
            # / Close the dropdown if it stays open after removal
            page.keyboard.press('Escape')
            page.wait_for_timeout(200)
            return

    raise AssertionError(
        f'Adhesion "{adhesion_name}" introuvable dans les items selectionnes'
        f' / Membership "{adhesion_name}" not found in selected items'
    )


class TestAdminAdhesionsObligatoiresM2M:
    """Adhesions obligatoires M2M sur un tarif de type TicketProduct.
    / Mandatory memberships M2M on a TicketProduct price.
    """

    def test_manage_multiple_adhesions_on_a_price(self, page, login_as_admin):
        """Cree 2 adhesions, un produit FREERES, lie les adhesions au tarif auto-cree, verifie.
        / Creates 2 memberships, a FREERES product, links memberships to the auto-created price, verifies.
        """
        # Identifiant unique pour cette session de test (evite les collisions entre runs)
        # / Unique identifier for this test session (avoids collisions between runs)
        uid = uuid.uuid4().hex[:8]

        membership_name_1 = f'Adhesion A {uid}'
        membership_name_2 = f'Adhesion B {uid}'
        free_res_product_name = f'Resa Gratuite AdhTest {uid}'

        # =====================================================================
        # Connexion admin / Admin login
        # =====================================================================
        login_as_admin(page)

        # =====================================================================
        # Etape 1 : Creer le produit adhesion A
        # Step 1: Create membership product A
        # =====================================================================
        _create_membership_product(page, membership_name_1, '10')

        # Verifier l'absence d'erreur de formulaire / Check no form errors
        error_list = page.locator('.errorlist')
        assert error_list.count() == 0, (
            f'Erreurs lors de la creation de l\'adhesion A : {error_list.all_inner_texts()}'
        )

        # =====================================================================
        # Etape 2 : Creer le produit adhesion B
        # Step 2: Create membership product B
        # =====================================================================
        _create_membership_product(page, membership_name_2, '15')

        error_list = page.locator('.errorlist')
        assert error_list.count() == 0, (
            f'Erreurs lors de la creation de l\'adhesion B : {error_list.all_inner_texts()}'
        )

        # =====================================================================
        # Etape 3 : Creer le produit reservation gratuite (proxy TicketProduct)
        # Step 3: Create the free reservation product (TicketProduct proxy)
        #
        # Le tarif gratuit FREERES est auto-cree par post_save_Product — y compris
        # via le proxy TicketProduct (fix signaux proxys 2026-06-11).
        # / The FREERES free price is auto-created by post_save_Product — including
        # through the TicketProduct proxy (proxy-signals fix 2026-06-11).
        # =====================================================================
        page.goto('/admin/BaseBillet/ticketproduct/add/')
        page.wait_for_load_state('networkidle')
        page.fill('input[name="name"]', free_res_product_name)
        page.select_option('select[name="categorie_article"]', 'F')  # F = FREERES

        # Enregistrer et continuer pour rester sur la page de modification
        # / Save and continue editing to stay on the change page
        page.locator('button[name="_continue"], input[name="_continue"]').first.click()
        page.wait_for_load_state('networkidle')

        # L'URL doit pointer vers la page de modification du produit sauvegarde
        # / URL must point to the change page of the saved product
        assert re.search(
            r'/admin/BaseBillet/ticketproduct/[0-9a-f-]+/change/', page.url
        ), f'URL inattendue apres sauvegarde : {page.url}'

        # =====================================================================
        # Etape 4 : Verifier le tarif gratuit auto-cree dans l'inline
        # Step 4: Verify the auto-created free price in the inline
        #
        # prices-0 est le tarif auto-cree par le signal. Son prix doit etre 0.
        # C'est la preuve E2E que le fix des signaux proxys fonctionne.
        # / prices-0 is the price auto-created by the signal. Its price must be 0.
        # This is the E2E proof that the proxy-signals fix works.
        # =====================================================================
        prix_input = page.locator('input[name="prices-0-prix"]')
        expect(prix_input).to_be_attached(timeout=10000)
        # Le prix peut etre affiche "0", "0.00", "0,00", etc.
        # / The price can be displayed as "0", "0.00", "0,00", etc.
        expect(prix_input).to_have_value(re.compile(r'^0([.,]0+)?$'))

        adhesions_select = page.locator('select[name="prices-0-adhesions_obligatoires"]')
        expect(adhesions_select).to_be_attached(timeout=10000)

        # =====================================================================
        # Etape 5 : Verifier l'absence du bouton "+" sur le widget M2M
        # Step 5: Verify there is no "+" add button on the M2M widget
        #
        # Le widget adhesions_obligatoires ne doit pas avoir de bouton "Ajouter +"
        # qui ouvrirait la creation d'une nouvelle adhesion depuis l'inline tarif.
        # / The adhesions_obligatoires widget must not have an "Add +" button
        # that would open membership creation from the price inline.
        # =====================================================================
        add_related_btn = page.locator(
            '#add_id_prices-0-adhesions_obligatoires, '
            '.field-adhesions_obligatoires a.add-related'
        )
        assert add_related_btn.count() == 0, (
            'Le bouton "+" ne devrait pas etre present sur le widget M2M adhesions_obligatoires'
            ' / The "+" button should not be present on the adhesions_obligatoires M2M widget'
        )

        # =====================================================================
        # Etape 6 : Ajouter l'adhesion A via select2
        # Step 6: Add membership A via select2
        # =====================================================================
        _add_adhesion_select2(page, membership_name_1, uid)

        # =====================================================================
        # Etape 7 : Ajouter l'adhesion B via select2
        # Step 7: Add membership B via select2
        # =====================================================================
        _add_adhesion_select2(page, membership_name_2, uid)

        # =====================================================================
        # Etape 8 : Enregistrer et continuer
        # Step 8: Save and continue editing
        # =====================================================================
        page.locator('button[name="_continue"], input[name="_continue"]').first.click()
        page.wait_for_load_state('networkidle')

        assert re.search(
            r'/admin/BaseBillet/ticketproduct/[0-9a-f-]+/change/', page.url
        ), f'URL inattendue apres sauvegarde des adhesions : {page.url}'

        # =====================================================================
        # Etape 9 : Verifier que les 2 adhesions sont persistees
        # Step 9: Verify both memberships are persisted after reload
        # =====================================================================
        selected = _get_selected_adhesions(page)
        assert membership_name_1 in selected, (
            f'L\'adhesion A "{membership_name_1}" n\'est pas dans la selection : {selected}'
        )
        assert membership_name_2 in selected, (
            f'L\'adhesion B "{membership_name_2}" n\'est pas dans la selection : {selected}'
        )

        # =====================================================================
        # Etape 10 : Retirer l'adhesion A
        # Step 10: Remove membership A
        # =====================================================================
        _remove_adhesion_select2(page, membership_name_1)

        # Enregistrer et continuer / Save and continue editing
        page.locator('button[name="_continue"], input[name="_continue"]').first.click()
        page.wait_for_load_state('networkidle')

        assert re.search(
            r'/admin/BaseBillet/ticketproduct/[0-9a-f-]+/change/', page.url
        ), f'URL inattendue apres retrait de l\'adhesion A : {page.url}'

        # =====================================================================
        # Etape 11 : Verifier que seule l'adhesion B reste
        # Step 11: Verify only membership B remains
        # =====================================================================
        selected_final = _get_selected_adhesions(page)
        assert membership_name_1 not in selected_final, (
            f'L\'adhesion A "{membership_name_1}" devrait avoir ete retiree. '
            f'Selection actuelle : {selected_final}'
        )
        assert membership_name_2 in selected_final, (
            f'L\'adhesion B "{membership_name_2}" devrait encore etre presente. '
            f'Selection actuelle : {selected_final}'
        )
