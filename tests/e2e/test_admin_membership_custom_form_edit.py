"""
Tests E2E : edition des champs custom_form d'une adhesion dans l'admin.
/ E2E tests: editing custom_form fields of a membership in the admin.

Conversion de tests/playwright/tests/26-admin-membership-custom-form-edit.spec.ts

Ce test verifie que :
/ This test verifies that:
- Un admin peut acceder a l'interface d'edition des champs personnalises
  / An admin can access the custom fields edit interface
- Les champs sont correctement affiches avec leurs valeurs actuelles
  / Fields are correctly displayed with their current values
- Les modifications sont sauvegardees et affichees
  / Modifications are saved and displayed
- Les erreurs de validation sont affichees
  / Validation errors are displayed

ATTENTION : ce test cree un produit d'adhesion + une adhesion dans la DB de dev
partagee (sans rollback). Les noms sont suffixes d'un id aleatoire pour eviter
les collisions entre sessions de test.
/ WARNING: this test creates a membership product + a membership in the shared dev DB
(no rollback). Names are suffixed with a random id to avoid collisions between test sessions.
"""

import uuid

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


def _add_form_field(page, form_index, label, field_type, required=False, options_csv=None):
    """Ajoute un champ dynamique dans l'inline #form_fields-group.
    / Add a dynamic field in the admin inline #form_fields-group.

    Clique sur "Add another" dans l'inline, puis remplit le nouveau champ.
    L'ordre (champ 'order') est masque (drag & drop) : on ne le remplit pas.
    / Clicks "Add another" in the inline, then fills the new field.
    The 'order' field is hidden (drag & drop): we do not fill it.
    """
    section = page.locator('#form_fields-group')

    # Compter les champs existants avant l'ajout pour determiner l'index
    # / Count existing fields before adding to determine the index
    count_before = section.locator(
        'input[name^="form_fields-"][name$="-label"]:not([name*="__prefix__"])'
    ).count()

    # Cliquer sur le bouton "Add another" de l'inline
    # / Click the "Add another" button of the inline
    add_button = section.locator('a.add-row').first
    add_button.click()

    # Attendre que le nouveau champ label soit visible
    # / Wait for the new label field to be visible
    label_input = section.locator(f'input[name="form_fields-{count_before}-label"]')
    label_input.wait_for(state='visible', timeout=5000)

    label_input.fill(label)
    section.locator(f'select[name="form_fields-{count_before}-field_type"]').select_option(field_type)

    if required:
        # Cocher la case "required" / Check the "required" checkbox
        section.locator(f'input[name="form_fields-{count_before}-required"]').check()

    if options_csv:
        # Les options se saisissent via le champ CSV 'options_csv' (proxy du JSONField).
        # / Options are entered via the 'options_csv' CSV field (JSONField proxy).
        options_input = section.locator(
            f'input[name="form_fields-{count_before}-options_csv"], '
            f'textarea[name="form_fields-{count_before}-options_csv"]'
        ).first
        options_input.fill(options_csv)


class TestAdminMembershipCustomFormEdit:
    """Edition des champs custom_form d'une adhesion dans l'admin.
    / Editing custom_form fields of a membership in the admin.
    """

    def test_edit_custom_form_fields_of_membership(self, page, login_as_admin, django_shell):
        """Cree un produit d'adhesion, injecte un custom_form et teste l'interface d'edition.
        / Creates a membership product, injects a custom_form and tests the edit interface.
        """
        # Identifiant aleatoire pour isoler cette session de test
        # / Random identifier to isolate this test session
        random_id = uuid.uuid4().hex[:8]
        product_name = f'Adhesion Test Edit {random_id}'
        user_email = f'test+edit{random_id}@example.com'

        # --- Connexion admin ---
        # / Admin login
        login_as_admin(page)

        # =====================================================================
        # Etape 1 : Creer un produit d'adhesion avec un tarif
        # Step 1: Create a membership product with a price
        # =====================================================================
        # Les adhesions se creent via le proxy membershipproduct (categorie fixee, champ cache).
        # / Memberships are created via the membershipproduct proxy (category is set, hidden field).
        page.goto('/admin/BaseBillet/membershipproduct/add/')
        page.wait_for_load_state('networkidle')

        # Nom du produit / Product name
        page.fill('input[name="name"]', product_name)

        # Description courte / Short description
        page.fill('input[name="short_description"]', 'Test edition custom_form admin')

        # Ajouter un tarif gratuit pour pouvoir creer l'adhesion sans paiement
        # / Add a free price to create the membership without payment
        # Le bouton "Ajouter" se trouve dans l'inline #prices-group (a.add-row).
        # Le texte varie selon la langue (FR/EN), on cible la classe add-row.
        # / The "Add" button is in the #prices-group inline (a.add-row).
        # Text varies by language (FR/EN), so we target the add-row class.
        prices_section = page.locator('#prices-group')
        add_price_button = prices_section.locator('a.add-row').first
        add_price_button.scroll_into_view_if_needed()
        add_price_button.click()
        page.wait_for_timeout(500)

        page.fill('input[name="prices-0-name"]', 'Gratuit annuel')
        page.fill('input[name="prices-0-prix"]', '0')
        # Y = 365 jours (annee) / Y = 365 days (year)
        page.select_option('select[name="prices-0-subscription_type"]', 'Y')

        # Cocher "Publier" / Check "Publish"
        publish_checkbox = page.locator('input[name="publish"]')
        if publish_checkbox.count() > 0:
            publish_checkbox.check()

        # "Save and continue editing" pour rester sur la page d'edition
        # / "Save and continue editing" to stay on the edit page
        save_and_continue = page.locator('button[name="_continue"]').first
        save_and_continue.click()
        page.wait_for_load_state('networkidle')

        # Verifier pas d'erreur / Check no errors
        error_list = page.locator('.errorlist')
        assert error_list.count() == 0, (
            f'Erreurs lors de la creation du produit : {error_list.all_inner_texts()}'
        )

        # =====================================================================
        # Etape 2 : Ajouter des champs dynamiques au produit
        # Step 2: Add dynamic fields to the product
        # =====================================================================
        # Ouvrir l'onglet de l'inline : ancre #form_fields (activeTab Alpine.js).
        # / Open the inline tab: #form_fields anchor (Alpine.js activeTab).
        tab = page.locator('a[href="#form_fields"]').first
        if page.locator('a[href="#form_fields"]').count() > 0:
            tab.click()
            page.wait_for_timeout(1000)

        # Champ 1 : Texte court (nom) — obligatoire
        # Field 1: Short text (name) — required
        _add_form_field(page, 0, 'Nom complet', 'ST', required=True)

        # Champ 2 : Selection simple (ville)
        # Field 2: Single select (city)
        _add_form_field(page, 1, 'Ville', 'SS', required=False, options_csv='Paris, Lyon, Marseille, Toulouse')

        # Champ 3 : Booleen (newsletter)
        # Field 3: Boolean (newsletter)
        _add_form_field(page, 2, 'Newsletter', 'BL', required=False)

        # Sauvegarder / Save
        save_and_continue = page.locator('button[name="_continue"]').first
        save_and_continue.click()
        page.wait_for_load_state('networkidle')

        error_list = page.locator('.errorlist')
        assert error_list.count() == 0, (
            f'Erreurs lors de l\'ajout des champs : {error_list.all_inner_texts()}'
        )

        # =====================================================================
        # Etape 3 : Creer une adhesion depuis l'admin
        # Step 3: Create a membership from admin
        # =====================================================================
        page.goto('/admin/BaseBillet/membership/add/')
        page.wait_for_load_state('networkidle')

        # Remplir l'email / Fill in the email
        page.fill('input[name="email"]', user_email)

        # Selectionner le tarif qu'on vient de creer par son texte
        # / Select the price we just created by its text content
        price_select = page.locator('select[name="price"]')
        price_select.wait_for(state='visible', timeout=5000)

        # Chercher l'option qui contient le nom du produit
        # / Find the option containing the product name
        all_options = price_select.locator('option').all()
        target_value = ''
        for option in all_options:
            text = option.text_content() or ''
            if product_name in text:
                target_value = option.get_attribute('value') or ''
                break

        assert target_value != '', (
            f'Aucun tarif trouve pour le produit : {product_name}'
        )
        price_select.select_option(target_value)

        # Sauvegarder avec "Save and continue editing"
        # / Save with "Save and continue editing"
        save_and_continue = page.locator('button[name="_continue"]').first
        save_and_continue.click()
        page.wait_for_load_state('networkidle')

        # =====================================================================
        # Etape 4 : Injecter des donnees custom_form via le shell Django
        # Step 4: Inject custom_form data via the Django shell
        # L'admin ne permet pas de remplir custom_form directement,
        # on utilise le shell Django pour simuler des reponses existantes.
        # / The admin doesn't allow filling custom_form directly,
        # we use the Django shell to simulate existing answers.
        # =====================================================================
        # Extraire le PK de l'adhesion depuis l'URL de la page
        # L'URL admin est de la forme /admin/BaseBillet/membership/<pk>/change/
        # / Extract the membership PK from the page URL
        # Admin URL is like /admin/BaseBillet/membership/<pk>/change/
        import re
        current_url = page.url
        pk_match = re.search(r'/membership/(\d+)/change', current_url)
        assert pk_match is not None, (
            f'Impossible de trouver le PK de l\'adhesion dans l\'URL : {current_url}'
        )
        membership_pk = pk_match.group(1)

        # Injecter le custom_form via le shell Django
        # ATTENTION : django_shell echappe les guillemets doubles → code Python avec quotes simples UNIQUEMENT
        # / Inject custom_form via the Django shell
        # WARNING: django_shell escapes double quotes → Python code with single quotes ONLY
        result = django_shell(
            'import json\n'
            'from BaseBillet.models import Membership\n'
            f'm = Membership.objects.get(pk={membership_pk})\n'
            "m.custom_form = {'Nom complet': 'Jean Dupont', 'Ville': 'Paris', 'Newsletter': True}\n"
            'm.save()\n'
            "print('OK')"
        )
        assert 'OK' in result, (
            f'Echec de l\'injection du custom_form : {result}'
        )

        # Recharger la page pour voir le custom_form
        # / Reload the page to see the custom_form
        page.reload()
        page.wait_for_load_state('networkidle')

        # =====================================================================
        # Etape 5 : Tester l'interface d'edition des champs personnalises
        # Step 5: Test the custom fields edit interface
        # =====================================================================
        # Verifier que le bouton "Modifier les reponses" est present
        # / Check that "Modify answers" button is present
        edit_button = page.locator('[data-testid="custom-form-edit-btn"]')
        expect(edit_button).to_be_visible(timeout=5000)

        # Cliquer sur le bouton pour ouvrir le formulaire d'edition
        # / Click button to open edit form
        edit_button.click()
        page.wait_for_timeout(1000)

        # Verifier que le formulaire d'edition est affiche (le container change via HTMX)
        # / Check that edit form is displayed (container content changes via HTMX)
        nom_input = page.locator('input[name="Nom complet"]')
        expect(nom_input).to_be_visible(timeout=5000)
        expect(nom_input).to_have_value('Jean Dupont')

        ville_select = page.locator('select[name="Ville"]')
        expect(ville_select).to_have_value('Paris')

        # Modifier les valeurs / Modify values
        nom_input.fill('Marie Martin')
        ville_select.select_option('Lyon')

        # Sauvegarder les modifications (data-testid : le libelle est traduit, FR ou EN)
        # / Save changes (data-testid: the label is translated, FR or EN)
        save_button = page.locator('[data-testid="custom-form-save-btn"]')
        save_button.click()
        page.wait_for_timeout(1000)

        # Verifier le message de succes via data-testid
        # / Check success message via data-testid
        success_message = page.locator('[data-testid="custom-form-success-msg"]')
        expect(success_message).to_be_visible(timeout=5000)

        # =====================================================================
        # Etape 6 : Tester l'annulation d'edition
        # Step 6: Test edit cancellation
        # =====================================================================
        # Cliquer a nouveau sur modifier / Click edit again
        edit_button = page.locator('[data-testid="custom-form-edit-btn"]')
        edit_button.click()
        page.wait_for_timeout(1000)

        # Modifier une valeur / Modify a value
        nom_input = page.locator('input[name="Nom complet"]')
        expect(nom_input).to_be_visible(timeout=3000)
        nom_input.fill('Test Annulation')

        # Cliquer sur Annuler dans le formulaire d'edition (data-testid cible pour eviter
        # de cliquer sur le bouton "Annuler l'adhesion" du panneau HTMX en tete de page)
        # / Click Cancel in the edit form (targeted data-testid to avoid clicking the
        # "Annuler l'adhesion" button in the HTMX panel at the top of the page)
        cancel_button = page.locator('[data-testid="custom-form-cancel-btn"]')
        cancel_button.click()
        page.wait_for_timeout(500)

        # Verifier que la valeur n'a pas change (Marie Martin toujours affichee)
        # / Check value hasn't changed (Marie Martin still displayed)
        table_cell = page.locator('text=Marie Martin')
        expect(table_cell).to_be_visible(timeout=3000)

        # =====================================================================
        # Etape 7 : Tester la validation des champs obligatoires (HTML natif)
        # Step 7: Test required fields validation (HTML native)
        # =====================================================================
        # Ouvrir l'edition / Open edit
        edit_button = page.locator('[data-testid="custom-form-edit-btn"]')
        edit_button.click()
        page.wait_for_timeout(1000)

        # Vider un champ obligatoire / Empty a required field
        nom_input = page.locator('input[name="Nom complet"]')
        expect(nom_input).to_be_visible(timeout=3000)
        nom_input.fill('')

        # Essayer de sauvegarder / Try to save
        save_button = page.locator('[data-testid="custom-form-save-btn"]')
        save_button.click()
        page.wait_for_timeout(500)

        # La validation HTML native empeche la soumission.
        # On verifie que le formulaire est toujours affiche (pas soumis).
        # / HTML native validation prevents submission.
        # We verify the form is still displayed (not submitted).
        expect(nom_input).to_be_visible(timeout=3000)

        # Verifier que l'input a l'attribut required
        # / Check the input has the required attribute
        is_required = nom_input.get_attribute('required')
        assert is_required is not None, (
            'Le champ "Nom complet" devrait avoir l\'attribut required'
        )

        # Annuler / Cancel
        cancel_button = page.locator('[data-testid="custom-form-cancel-btn"]')
        cancel_button.click()
        page.wait_for_timeout(500)
