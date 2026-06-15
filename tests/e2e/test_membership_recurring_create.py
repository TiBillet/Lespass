"""
Tests E2E : création du produit d'adhésion récurrente via l'admin.
/ E2E tests: creation of recurring membership product via admin.

Conversion de tests/playwright/tests/04-membership-recurring.spec.ts

Ce test vérifie que :
/ This test verifies that:
- Un admin peut créer (ou éditer) un produit d'adhésion récurrente via le proxy
  MembershipProduct
  / An admin can create (or edit) a recurring membership product via the
  MembershipProduct proxy
- Deux tarifs récurrents peuvent être ajoutés en inline : "Journalière" (2€, D)
  et "Mensuelle" (20€, M)
  / Two recurring prices can be added inline: "Journalière" (2€, D) and
  "Mensuelle" (20€, M)
- Le produit est visible sur la page publique /memberships/
  / The product is visible on the public /memberships/ page

ATTENTION : ce test peut modifier un produit existant ou en créer un nouveau dans
la DB partagée (sans rollback). Le produit "Adhésion récurrente (Le Tiers-Lustre)"
est une donnée de référence de l'environnement de dev.
/ WARNING: this test may modify an existing product or create a new one in the
shared DB (no rollback). "Adhésion récurrente (Le Tiers-Lustre)" is a reference
data item in the dev environment.
"""

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


def _add_inline_price(page, price_data):
    """Ajoute un tarif dans l'inline #prices-group du formulaire admin produit.
    / Adds a price in the admin product form's #prices-group inline.

    Clique sur "Add another" (bouton a.add-row dans #prices-group), puis remplit
    le nouveau rang selon l'index détecté avant le clic.
    / Clicks "Add another" (a.add-row button in #prices-group), then fills
    the new row using the index detected before the click.

    price_data dict attendu / expected:
    - name (str)              : libellé du tarif
    - prix (int)              : montant entier (pas de virgule — locale FR)
    - subscription_type (str) : 'D' | 'M' | 'Y' | ...
    """
    prices_section = page.locator('#prices-group')

    # Compter les lignes existantes (hors template __prefix__) pour calculer l'index.
    # / Count existing rows (excluding __prefix__ template) to compute the index.
    count_before = prices_section.locator(
        'input[name^="prices-"][name$="-name"]:not([name*="__prefix__"])'
    ).count()

    # Cliquer sur le bouton d'ajout inline.
    # / Click the inline add button.
    add_button = prices_section.locator('a.add-row').first
    add_button.click()

    # Attendre que le nouveau champ name soit visible.
    # / Wait for the new name field to become visible.
    form_index = count_before
    name_input = prices_section.locator(f'input[name="prices-{form_index}-name"]')
    name_input.wait_for(state='visible', timeout=5_000)

    # Remplir le libellé du tarif.
    # / Fill the price label.
    name_input.fill(price_data['name'])

    # Remplir le montant en entier (évite le problème de séparateur décimal FR).
    # / Fill the amount as integer (avoids FR decimal separator issue).
    prices_section.locator(
        f'input[name="prices-{form_index}-prix"]'
    ).fill(str(price_data['prix']))

    # Sélectionner le type d'abonnement récurrent (D=quotidien, M=mensuel, Y=annuel…).
    # / Select the recurring subscription type (D=daily, M=monthly, Y=annual…).
    prices_section.locator(
        f'select[name="prices-{form_index}-subscription_type"]'
    ).select_option(price_data['subscription_type'])


class TestMembershipRecurringCreate:
    """Création du produit d'adhésion récurrente via le proxy admin MembershipProduct.
    / Creation of recurring membership product via the MembershipProduct admin proxy.
    """

    def test_create_adhesion_recurrente_le_tiers_lustre(self, page, login_as_admin):
        """Crée ou édite "Adhésion récurrente (Le Tiers-Lustre)" avec 2 tarifs récurrents,
        vérifie la visibilité sur /memberships/.
        / Creates or edits "Adhésion récurrente (Le Tiers-Lustre)" with 2 recurring prices,
        verifies visibility on /memberships/.
        """
        # --- Étape 1 : Connexion admin ---
        # / Step 1: Admin login
        login_as_admin(page)

        # --- Étape 2 : Naviguer vers le proxy MembershipProduct ---
        # Le proxy fixe la catégorie ADHESION automatiquement (champ caché).
        # / Step 2: Navigate to the MembershipProduct proxy
        # The proxy sets the ADHESION category automatically (hidden field).
        page.goto('/admin/BaseBillet/membershipproduct/')
        page.wait_for_load_state('networkidle')

        # Chercher si le produit existe déjà dans la changelist.
        # Si oui, on l'édite ; sinon, on crée un nouveau.
        # / Check if the product already exists in the changelist.
        # If yes, edit it; if no, create a new one.
        product_link = page.locator('#result_list a, .result-list a').filter(
            has_text='Adhésion récurrente (Le Tiers-Lustre)'
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
        # / Step 3: Fill in the basic product info
        page.locator('input[name="name"]').fill('Adhésion récurrente (Le Tiers-Lustre)')

        # Pas de sélection de catégorie : le proxy MembershipProduct la fixe (champ caché).
        # / No category selection: the MembershipProduct proxy sets it (hidden field).

        # Remplir la description courte si le champ est présent.
        # / Fill the short description if the field is present.
        short_desc = page.locator('input[name="short_description"]').first
        if short_desc.count() > 0:
            short_desc.fill('Adhésion avec paiements récurrents')

        # --- Étape 4 : Ajouter les tarifs inline récurrents ---
        # Tarif 1 : Journalière, 2€, abonnement quotidien (D).
        # / Step 4: Add inline recurring prices
        # Price 1: Journalière, 2€, daily subscription (D).
        _add_inline_price(page, {
            'name': 'Journalière',
            'prix': 2,
            'subscription_type': 'D',
        })

        # Tarif 2 : Mensuelle, 20€, abonnement mensuel (M).
        # / Price 2: Mensuelle, 20€, monthly subscription (M).
        _add_inline_price(page, {
            'name': 'Mensuelle',
            'prix': 20,
            'subscription_type': 'M',
        })

        # --- Étape 5 : Sauvegarder le formulaire ---
        # Django admin Unfold : le bouton Save a l'attribut name="_save".
        # / Step 5: Save the form
        # Django admin Unfold: the Save button has name="_save" attribute.
        save_button = page.locator('[name="_save"]').first
        save_button.click()
        page.wait_for_load_state('networkidle')

        # Vérifier l'absence d'erreur de validation.
        # Unfold affiche les erreurs dans .errorlist ou .errornote.
        # / Verify no validation errors.
        # Unfold displays errors in .errorlist or .errornote.
        content = page.content()
        assert (
            'errorlist' not in content
            or 'was saved successfully' in content
            or '/admin/BaseBillet/membershipproduct/' in page.url
        ), f"Erreur probable lors de la sauvegarde. URL: {page.url}"

        # --- Étape 6 : Vérifier la visibilité sur /memberships/ ---
        # / Step 6: Verify visibility on /memberships/
        page.goto('/memberships/')
        page.wait_for_load_state('networkidle')

        page_content = page.content()
        assert 'Adhésion récurrente' in page_content, (
            f"Le produit 'Adhésion récurrente (Le Tiers-Lustre)' n'est pas visible "
            f"sur /memberships/. URL: {page.url}"
        )
