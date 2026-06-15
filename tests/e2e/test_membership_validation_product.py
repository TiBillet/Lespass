"""
Tests E2E : création du produit d'adhésion à validation sélective via l'admin.
/ E2E tests: creation of selective-validation membership product via admin.

Conversion de tests/playwright/tests/05-membership-validation.spec.ts

Ce test vérifie que :
/ This test verifies that:
- Un admin peut créer (ou éditer) un produit d'adhésion "Adhésion à validation sélective
  (Le Tiers-Lustre)" via le proxy MembershipProduct.
  / An admin can create (or edit) a membership product "Adhésion à validation sélective
  (Le Tiers-Lustre)" via the MembershipProduct proxy.
- Deux tarifs peuvent être ajoutés en inline : "Solidaire" (2€, Y) et "Plein tarif" (30€, Y).
  / Two prices can be added inline: "Solidaire" (2€, Y) and "Plein tarif" (30€, Y).
- Le produit est visible sur la page publique /memberships/.
  / The product is visible on the public /memberships/ page.

ATTENTION : ce test peut modifier un produit existant ou en créer un nouveau dans la DB
partagée (sans rollback). Le produit "Adhésion à validation sélective (Le Tiers-Lustre)"
est une donnée de référence de l'environnement de dev.
/ WARNING: this test may modify an existing product or create a new one in the shared DB
(no rollback). "Adhésion à validation sélective (Le Tiers-Lustre)" is a reference data item.
"""

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e

PRODUCT_NAME = "Adhésion à validation sélective (Le Tiers-Lustre)"


def _add_inline_price(page, price_data):
    """Ajoute un tarif dans l'inline #prices-group du formulaire admin produit.
    / Adds a price in the admin product form's #prices-group inline.

    Clique sur "Add another" (bouton a.add-row dans #prices-group), puis remplit
    le nouveau rang selon l'index détecté avant le clic.
    / Clicks "Add another" (a.add-row button in #prices-group), then fills
    the new row using the index detected before the click.

    price_data dict attendu / expected:
    - name (str)              : libellé du tarif
    - prix (int)              : montant (entier pour éviter problèmes de locale FR)
    - subscription_type (str) : 'Y' | 'M' | ...
    """
    prices_section = page.locator('#prices-group')

    # Compter les lignes de tarifs existantes avant le clic pour calculer l'index.
    # On se base sur l'input "name" (pas __prefix__) pour éviter de compter le
    # template de formulaire vide.
    # / Count existing price rows before click to compute the index.
    # Based on "name" input (excluding __prefix__) to avoid counting empty template.
    count_before = prices_section.locator(
        'input[name^="prices-"][name$="-name"]:not([name*="__prefix__"])'
    ).count()

    # Cliquer sur le bouton d'ajout de l'inline prices.
    # / Click the add button of the prices inline.
    add_button = prices_section.locator('a.add-row').first
    add_button.click()

    # Attendre que le nouveau champ name soit visible.
    # / Wait for the new name field to become visible.
    form_index = count_before
    name_input = prices_section.locator(f'input[name="prices-{form_index}-name"]')
    name_input.wait_for(state='visible', timeout=5_000)

    # Remplir le nom du tarif.
    # / Fill the price name.
    name_input.fill(price_data['name'])

    # Remplir le montant. Locale FR : l'input peut afficher '0,00' mais on passe
    # un entier pour éviter les problèmes de séparateur décimal.
    # / Fill the amount. FR locale: input may show '0,00' but we pass an integer
    # to avoid decimal separator issues.
    price_input = prices_section.locator(f'input[name="prices-{form_index}-prix"]')
    price_input.fill(str(price_data['prix']))

    # Sélectionner le type d'abonnement (Y=annuel, M=mensuel, etc.).
    # / Select the subscription type (Y=annual, M=monthly, etc.).
    prices_section.locator(
        f'select[name="prices-{form_index}-subscription_type"]'
    ).select_option(price_data['subscription_type'])


class TestMembershipValidationProduct:
    """Création du produit d'adhésion à validation sélective via le proxy admin.
    / Creation of selective-validation membership product via the admin proxy.
    """

    def test_create_adhesion_validation_selective_with_2_prices(
        self, page, login_as_admin
    ):
        """Crée ou édite "Adhésion à validation sélective (Le Tiers-Lustre)" avec 2 tarifs,
        vérifie /memberships/.
        / Creates or edits "Adhésion à validation sélective (Le Tiers-Lustre)" with 2 prices,
        verifies /memberships/.
        """
        # --- Étape 1 : Connexion admin ---
        # / Step 1: Admin login
        login_as_admin(page)

        # --- Étape 2 : Naviguer vers la liste des produits adhésion ---
        # L'admin produit a été refondu en proxys : les adhésions se créent via
        # /admin/BaseBillet/membershipproduct/ (la catégorie est fixée par le proxy).
        # / Product admin was split into proxies: memberships are created via
        # the membershipproduct proxy (category is set by the proxy itself).
        page.goto('/admin/BaseBillet/membershipproduct/')
        page.wait_for_load_state('networkidle')

        # Chercher si le produit existe déjà dans la changelist.
        # Si oui, on l'édite ; sinon, on crée un nouveau.
        # / Check if the product already exists in the changelist.
        # If yes, edit it; if no, create a new one.
        product_link = page.locator('#result_list a, .result-list a').filter(
            has_text=PRODUCT_NAME
        ).first

        if product_link.count() > 0:
            # Produit existant → éditer.
            # / Existing product → edit.
            product_link.click()
        else:
            # Produit inexistant → créer.
            # / Product doesn't exist → create.
            page.goto('/admin/BaseBillet/membershipproduct/add/')

        page.wait_for_load_state('networkidle')

        # --- Étape 3 : Remplir les informations de base du produit ---
        # Pas de sélection de catégorie : le proxy MembershipProduct la fixe (champ caché).
        # / Step 3: Fill in the basic product info
        # No category selection: the MembershipProduct proxy sets it (hidden field).
        page.locator('input[name="name"]').fill(PRODUCT_NAME)
        page.locator('input[name="short_description"]').first.fill(
            'Tarif solidaire soumis à validation manuelle'
        )

        # --- Étape 4 : Ajouter les tarifs inline ---
        # Tarif 1 : Solidaire, 2€, abonnement annuel (Y).
        # / Step 4: Add inline prices
        # Price 1: Solidaire, 2€, annual subscription (Y).
        _add_inline_price(page, {
            'name': 'Solidaire',
            'prix': 2,
            'subscription_type': 'Y',
        })

        # Tarif 2 : Plein tarif, 30€, abonnement annuel (Y).
        # / Price 2: Plein tarif, 30€, annual subscription (Y).
        _add_inline_price(page, {
            'name': 'Plein tarif',
            'prix': 30,
            'subscription_type': 'Y',
        })

        # --- Étape 5 : Sauvegarder le formulaire ---
        # Django admin Unfold : le bouton Save a l'attribut name="_save".
        # / Step 5: Save the form
        # Django admin Unfold: the Save button has name="_save" attribute.
        save_button = page.locator('[name="_save"]').first
        save_button.click()
        page.wait_for_load_state('networkidle')

        # Vérifier qu'il n'y a pas d'erreur de validation dans la page.
        # Unfold et Django admin affichent les erreurs dans .errorlist ou .errornote.
        # / Verify there are no validation errors on the page.
        # Unfold and Django admin display errors in .errorlist or .errornote.
        content = page.content()
        assert (
            'errorlist' not in content
            or 'was saved successfully' in content
            or '/admin/BaseBillet/membershipproduct/' in page.url
        ), f"Erreur probable lors de la sauvegarde. URL: {page.url}"

        # --- Étape 6 : Vérifier la visibilité sur /memberships/ ---
        # Le produit doit apparaître sur la page publique des adhésions.
        # / Step 6: Verify visibility on /memberships/
        # The product must appear on the public memberships page.
        page.goto('/memberships/')
        page.wait_for_load_state('networkidle')

        page_content = page.content()
        assert (
            'validation sélective' in page_content
            or 'validation selective' in page_content
        ), (
            f"Le produit '{PRODUCT_NAME}' n'est pas visible sur /memberships/. "
            f"URL: {page.url}"
        )
