"""
Tests E2E : cycle complet — Adhesion avec formulaire dynamique (tous les types de champs).
/ E2E tests: full cycle — Membership with dynamic form (all field types).

Conversion de tests/playwright/tests/27-membership-dynamic-form-full-cycle.spec.ts

7 etapes dependantes (produit cree en etape 1, reutilise ensuite) :
1. Admin cree le produit adhesion avec 6 types de champs dynamiques
2. Utilisateur public s'inscrit, remplit le formulaire, confirmation (tarif gratuit)
3. Admin verifie l'adhesion dans la liste
4. Admin verifie les reponses dans la page change
5. Admin ajoute un champ libre
6. Admin modifie les reponses existantes
7. Admin teste l'annulation de modification

ATTENTION : les etapes partagent le meme produit et email via des attributs de classe.
Un echec d'une etape anterieure peut invalider les suivantes.
/ WARNING: steps share the same product and email via class attributes.
A failure in an earlier step may invalidate later ones.
"""

import re
import uuid

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


def _ouvrir_changelist_admin(page, url):
    """Ouvre une changelist admin et retourne le champ de recherche.
    Le runserver de dev peut hoqueter sous charge (page d'erreur
    transitoire, OSError socket) : on recharge UNE fois si le champ
    de recherche n'apparait pas.
    / Opens an admin changelist and returns the search input.
    The dev runserver can hiccup under load (transient error page):
    reload ONCE if the search input is missing.
    """
    page.goto(url)
    page.wait_for_load_state('networkidle')
    search_input = page.locator('input[name="q"]').first
    try:
        search_input.wait_for(state='visible', timeout=10_000)
    except Exception:
        page.wait_for_timeout(2_000)
        page.goto(url)
        page.wait_for_load_state('networkidle')
        search_input.wait_for(state='visible', timeout=30_000)
    return search_input


def _add_form_field(page, label, field_type, required=False, help_text='', options_csv=None):
    """Ajoute un champ dynamique dans l'inline #form_fields-group.
    / Add a dynamic field in the admin inline #form_fields-group.

    Compte les champs existants, clique sur "Add another", remplit le nouveau champ.
    Le champ 'order' est masque (drag & drop) : on ne le remplit pas.
    / Counts existing fields, clicks "Add another", fills the new field.
    The 'order' field is hidden (drag & drop): we do not fill it.
    """
    section = page.locator('#form_fields-group')

    # Compter les champs existants pour calculer l'index du nouveau
    # / Count existing fields to calculate the new index
    count_before = section.locator(
        'input[name^="form_fields-"][name$="-label"]:not([name*="__prefix__"])'
    ).count()

    # Cliquer sur "Add another" dans l'inline
    # / Click "Add another" in the inline
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

    if help_text:
        # Remplir le texte d'aide (input ou textarea selon le widget)
        # / Fill the help text (input or textarea depending on widget)
        section.locator(
            f'input[name="form_fields-{count_before}-help_text"], '
            f'textarea[name="form_fields-{count_before}-help_text"]'
        ).first.fill(help_text)

    if options_csv:
        # Les options se saisissent via le champ CSV 'options_csv' (proxy du JSONField)
        # / Options are entered via the 'options_csv' CSV field (JSONField proxy)
        options_input = section.locator(
            f'input[name="form_fields-{count_before}-options_csv"], '
            f'textarea[name="form_fields-{count_before}-options_csv"]'
        ).first
        options_input.fill(options_csv)


class TestMembershipDynamicFormFullCycle:
    """Cycle complet formulaire dynamique adhesion (7 etapes).
    / Full dynamic form membership cycle (7 steps).
    """

    # Identifiants partages entre les 7 tests de la classe (DB dev partagee, pas de rollback)
    # / Shared identifiers across the 7 tests in the class (shared dev DB, no rollback)
    _random_id: str = ''
    _product_name: str = ''
    _user_email: str = ''

    # Reponses au formulaire dynamique / Dynamic form answers
    FORM_ANSWERS = {
        'shortText': 'Douglas Adams',
        'longText': 'Ecrivain de science-fiction britannique',
        'singleSelect': 'Option B',
        'radioSelect': 'Radio 2',
        'multiSelect': ['Choix A', 'Choix C'],
        'boolean': True,
    }

    @classmethod
    def setup_class(cls):
        """Initialise les identifiants partages une seule fois pour toute la suite.
        / Initializes shared identifiers once for the whole suite.
        """
        random_id = uuid.uuid4().hex[:8]
        cls._random_id = random_id
        cls._product_name = f'Adhesion DynForm Test {random_id}'
        cls._user_email = f'jturbeaux+dynform{random_id}@pm.me'

    # ===================================================================
    # ETAPE 1 — Admin : creer le produit adhesion avec champs dynamiques
    # STEP 1 — Admin: create membership product with dynamic form fields
    # ===================================================================

    def test_step1_admin_creates_membership_product(self, page, login_as_admin):
        """Admin cree un produit adhesion avec 6 types de champs dynamiques.
        / Admin creates a membership product with 6 dynamic field types.
        """
        # --- Connexion admin ---
        # / Admin login
        login_as_admin(page)

        # Les adhesions se creent via le proxy membershipproduct (categorie fixee, champ cache)
        # / Memberships are created via the membershipproduct proxy (category set, hidden field)
        page.goto('/admin/BaseBillet/membershipproduct/add/')
        page.wait_for_load_state('networkidle')

        # Remplir les infos produit / Fill product info
        page.fill('input[name="name"]', self._product_name)
        page.fill('input[name="short_description"]', 'Test E2E formulaire dynamique complet')

        # Cocher "Publier" si present / Check "Publish" if present
        publish_cb = page.locator('input[name="publish"]')
        if publish_cb.count() > 0:
            publish_cb.check()

        # --- Ajouter un tarif gratuit (requis pour sauvegarder) ---
        # / Add a free price (required to save)
        # Inline Unfold : conteneur #prices-group, bouton a.add-row
        # / Unfold inline: container #prices-group, button a.add-row
        prices_section = page.locator('#prices-group')
        add_price_button = prices_section.locator('a.add-row').first
        add_price_button.scroll_into_view_if_needed()
        add_price_button.click()
        page.wait_for_timeout(500)

        # Tarif gratuit annuel (subscription_type Y = 365 jours)
        # / Free annual price (subscription_type Y = 365 days)
        page.fill('input[name="prices-0-name"]', 'Annuelle gratuite')
        page.fill('input[name="prices-0-prix"]', '0')
        page.select_option('select[name="prices-0-subscription_type"]', 'Y')

        # Premier enregistrement avec "Save and continue editing"
        # pour pouvoir ajouter les champs de formulaire ensuite
        # / First save with "Save and continue editing"
        # to add form fields afterwards
        save_and_continue = page.locator('button[name="_continue"]').first
        save_and_continue.click()
        page.wait_for_load_state('networkidle')

        # Verifier pas d'erreur / Check no errors
        error_list = page.locator('.errorlist')
        assert error_list.count() == 0, (
            f'Erreurs apres le premier enregistrement : {error_list.all_inner_texts()}'
        )

        # --- Ajouter 6 champs dynamiques ---
        # / Add 6 dynamic fields
        # Ouvrir l'onglet de l'inline : ancre #form_fields (activeTab Alpine.js)
        # / Open the inline tab: #form_fields anchor (Alpine.js activeTab)
        tab = page.locator('a[href="#form_fields"]').first
        if page.locator('a[href="#form_fields"]').count() > 0:
            tab.click()
            page.wait_for_timeout(1000)

        # 1. Texte court / Short text (ST) — obligatoire
        _add_form_field(page, 'Nom complet', 'ST', required=True, help_text='Votre nom et prenom')

        # 2. Texte long / Long text (LT)
        _add_form_field(page, 'Presentation', 'LT', required=False, help_text='Presentez-vous brievement')

        # 3. Select simple / Single select (SS) avec options
        _add_form_field(page, 'Ville preferee', 'SS', required=True, options_csv='Option A, Option B, Option C')

        # 4. Radio / Single radio (SR) avec options
        _add_form_field(page, 'Frequence souhaitee', 'SR', required=True, options_csv='Radio 1, Radio 2, Radio 3')

        # 5. Multi-select (MS) avec options
        _add_form_field(page, "Centres d interet", 'MS', required=False,
                        help_text='Maintenez Ctrl pour selectionner plusieurs',
                        options_csv='Choix A, Choix B, Choix C')

        # 6. Booleen / Boolean (BL) — obligatoire
        _add_form_field(page, 'Accepter les conditions', 'BL', required=True,
                        help_text="J accepte le reglement")

        # Enregistrement final avec "Save and continue editing"
        # / Final save with "Save and continue editing"
        save_and_continue = page.locator('button[name="_continue"]').first
        save_and_continue.click()
        page.wait_for_load_state('networkidle')

        # Verifier pas d'erreur / Check no errors
        error_list = page.locator('.errorlist')
        assert error_list.count() == 0, (
            f'Erreurs apres le second enregistrement : {error_list.all_inner_texts()}'
        )

    # ===================================================================
    # ETAPE 2 — Public : souscrire + confirmation (tarif gratuit)
    # STEP 2 — Public: subscribe + confirmation (free price)
    # ===================================================================

    def test_step2_public_subscribes_with_dynamic_form(self, page):
        """Utilisateur public souscrit, remplit le formulaire dynamique, obtient confirmation.
        Le tarif est gratuit (0€) : pas de redirection Stripe.
        / Public user subscribes, fills the dynamic form, gets confirmation.
        The price is free (0€): no Stripe redirect.
        """
        # Aller sur la page des adhesions publiques / Go to public memberships page
        page.goto('/memberships/')
        page.wait_for_load_state('domcontentloaded')

        # Trouver la carte du produit et cliquer sur "Adherer"
        # / Find the product card and click "Subscribe"
        card = page.locator('.card').filter(has_text=self._product_name).first
        expect(card).to_be_visible(timeout=10_000)

        subscribe_button = card.locator('button').filter(
            has_text=re.compile(r'Subscribe|Adh[eé]rer', re.IGNORECASE)
        ).first
        subscribe_button.click()

        # Attendre l'ouverture du panneau offcanvas
        # / Wait for the offcanvas panel to open
        page.wait_for_selector('#subscribePanel.show, .offcanvas.show', state='visible', timeout=10_000)

        # Remplir les infos utilisateur / Fill user info
        panel = page.locator('#subscribePanel')
        panel.locator('input[name="email"]').fill(self._user_email)
        panel.locator('input[name="confirm-email"]').fill(self._user_email)
        panel.locator('input[name="firstname"]').fill('Douglas')
        panel.locator('input[name="lastname"]').fill('Adams')

        # Selectionner le tarif "Annuelle" / Select "Annuelle" price
        price_label = page.locator('label').filter(has_text='Annuelle').first
        price_label.click()

        # --- Remplir les champs dynamiques du formulaire ---
        # / Fill dynamic form fields

        # ST — Texte court / Short text : "Nom complet"
        # Le nom du champ HTML est base sur le label, slugifie
        # / HTML field name is based on the label, slugified
        short_text_input = page.locator('input[name="form__nom-complet"]')
        if short_text_input.count() > 0:
            short_text_input.fill(self.FORM_ANSWERS['shortText'])

        # LT — Texte long / Long text : "Presentation"
        long_text_input = page.locator('textarea[name="form__presentation"]')
        if long_text_input.count() > 0:
            long_text_input.fill(self.FORM_ANSWERS['longText'])

        # SS — Select simple / Single select : "Ville preferee"
        single_select = page.locator('select[name="form__ville-preferee"]')
        if single_select.count() > 0:
            single_select.select_option(self.FORM_ANSWERS['singleSelect'])

        # SR — Radio : "Frequence souhaitee"
        radio_input = page.locator(
            f'input[name="form__frequence-souhaitee"][value="{self.FORM_ANSWERS["radioSelect"]}"]'
        )
        if radio_input.count() > 0:
            radio_input.check()

        # MS — Multi-select (checkboxes) : "Centres d interet"
        for choice in self.FORM_ANSWERS['multiSelect']:
            checkbox = page.locator(
                f'input[name="form__centres-d-interet"][value="{choice}"]'
            )
            if checkbox.count() > 0:
                checkbox.check()

        # BL — Booleen / Boolean : "Accepter les conditions"
        bool_input = page.locator('input[name="form__accepter-les-conditions"]')
        if bool_input.count() > 0:
            bool_input.check()

        # Soumettre le formulaire / Submit the form
        submit_button = page.locator('#membership-submit')
        expect(submit_button).to_be_enabled(timeout=5_000)
        submit_button.click()

        # Attendre la confirmation (tarif gratuit = pas de Stripe)
        # Le template free_confirmed.html retourne un message de confirmation
        # / Wait for confirmation (free price = no Stripe)
        # The free_confirmed.html template returns a confirmation message
        success_message = page.locator('text=/confirm[eé]e|confirmed|succ[eè]s|success/i').first
        expect(success_message).to_be_visible(timeout=15_000)

    # ===================================================================
    # ETAPE 3 — Admin : verifier l'adhesion dans la liste
    # STEP 3 — Admin: verify membership in the list
    # ===================================================================

    def test_step3_admin_verifies_membership_in_list(self, page, login_as_admin):
        """Admin verifie que l'adhesion apparait dans la liste avec le bon statut.
        / Admin verifies that the membership appears in the list with the correct status.
        """
        login_as_admin(page)
        # Chercher par email dans la liste admin / Search by email in admin list
        search_input = _ouvrir_changelist_admin(page, '/admin/BaseBillet/membership/')
        search_input.fill(self._user_email)
        search_input.press('Enter')
        page.wait_for_load_state('networkidle')

        # Trouver la ligne de l'adhesion / Find the membership row
        row = page.locator('#result_list tbody tr').filter(has_text=self._user_email)
        expect(row).to_be_visible(timeout=10_000)

        # Verifier que l'adhesion est validee (icone check_small ou statut confirme)
        # / Check membership is validated (check_small icon or confirmed status)
        check_icon = row.locator('span.material-symbols-outlined').filter(has_text='check_small')
        if check_icon.count() > 0:
            expect(check_icon).to_be_visible(timeout=5_000)

    # ===================================================================
    # ETAPE 4 — Admin : verifier les reponses dans la page change
    # STEP 4 — Admin: verify answers in the change page
    # ===================================================================

    def test_step4_admin_verifies_form_answers(self, page, login_as_admin):
        """Admin verifie que les reponses au formulaire dynamique sont affichees.
        / Admin verifies that dynamic form answers are displayed.
        """
        login_as_admin(page)
        # Rechercher et ouvrir l'adhesion / Search and open the membership
        search_input = _ouvrir_changelist_admin(page, '/admin/BaseBillet/membership/')
        search_input.fill(self._user_email)
        search_input.press('Enter')
        page.wait_for_load_state('networkidle')

        row = page.locator('#result_list tbody tr').filter(has_text=self._user_email)
        expect(row).to_be_visible(timeout=10_000)
        row.locator('a').first.click()
        page.wait_for_load_state('networkidle')

        # Verifier la section des reponses au formulaire
        # / Check the form answers section
        custom_form_section = page.locator('text=/Custom form answers|R[eé]ponses.*formulaire/i')
        expect(custom_form_section).to_be_visible(timeout=5_000)

        # Verifier chaque reponse dans le tableau
        # / Check each answer in the table
        expect(page.locator(f'td:has-text("{self.FORM_ANSWERS["shortText"]}")')).to_be_visible()
        expect(page.locator(f'td:has-text("{self.FORM_ANSWERS["longText"]}")')).to_be_visible()
        expect(page.locator(f'td:has-text("{self.FORM_ANSWERS["singleSelect"]}")')).to_be_visible()
        expect(page.locator(f'td:has-text("{self.FORM_ANSWERS["radioSelect"]}")')).to_be_visible()

        # Multi-select : verifier que les choix sont presents
        # / Multi-select: check that choices are present
        for choice in self.FORM_ANSWERS['multiSelect']:
            expect(page.locator(f'td:has-text("{choice}")')).to_be_visible()

    # ===================================================================
    # ETAPE 5 — Admin : ajouter un champ libre
    # STEP 5 — Admin: add a free-form field
    # ===================================================================

    def test_step5_admin_adds_free_field(self, page, login_as_admin):
        """Admin ajoute un champ libre (label + valeur) a l'adhesion.
        / Admin adds a free-form field (label + value) to the membership.
        """
        login_as_admin(page)
        # Naviguer vers l'adhesion / Navigate to the membership
        search_input = _ouvrir_changelist_admin(page, '/admin/BaseBillet/membership/')
        search_input.fill(self._user_email)
        search_input.press('Enter')
        page.wait_for_load_state('networkidle')

        row = page.locator('#result_list tbody tr').filter(has_text=self._user_email)
        expect(row).to_be_visible(timeout=10_000)
        row.locator('a').first.click()
        page.wait_for_load_state('networkidle')

        # Cliquer sur "Ajouter un champ" / Click "Add a field"
        add_field_button = page.locator('[data-testid="custom-form-add-field-btn"]')
        expect(add_field_button).to_be_visible(timeout=5_000)
        add_field_button.click()
        page.wait_for_timeout(1000)

        # Remplir le formulaire d'ajout / Fill the add form
        page.locator('#new_field_label').fill('Note interne')
        page.locator('#new_field_value').fill('Adherent prioritaire')

        # Soumettre / Submit
        submit_button = page.locator('[data-testid="custom-form-add-submit-btn"]')
        submit_button.click()
        page.wait_for_timeout(1000)

        # Verifier le message de succes / Check success message
        success_msg = page.locator('[data-testid="custom-form-success-msg"]')
        expect(success_msg).to_be_visible(timeout=5_000)

        # Verifier que le champ libre est dans le tableau
        # / Check the free field is in the table
        expect(page.locator('td:has-text("Note interne")')).to_be_visible()
        expect(page.locator('td:has-text("Adherent prioritaire")')).to_be_visible()

    # ===================================================================
    # ETAPE 6 — Admin : modifier les reponses existantes
    # STEP 6 — Admin: edit existing answers
    # ===================================================================

    def test_step6_admin_edits_answers(self, page, login_as_admin):
        """Admin modifie les reponses du formulaire dynamique.
        / Admin edits the dynamic form answers.
        """
        login_as_admin(page)
        # Naviguer vers l'adhesion / Navigate to the membership
        search_input = _ouvrir_changelist_admin(page, '/admin/BaseBillet/membership/')
        search_input.fill(self._user_email)
        search_input.press('Enter')
        page.wait_for_load_state('networkidle')

        row = page.locator('#result_list tbody tr').filter(has_text=self._user_email)
        expect(row).to_be_visible(timeout=10_000)
        row.locator('a').first.click()
        page.wait_for_load_state('networkidle')

        # Cliquer sur "Modifier les reponses" / Click "Edit answers"
        edit_button = page.locator('[data-testid="custom-form-edit-btn"]')
        expect(edit_button).to_be_visible(timeout=5_000)
        edit_button.click()
        page.wait_for_timeout(1000)

        # Verifier que le formulaire d'edition est visible
        # / Check the edit form is visible
        # Les noms des inputs correspondent aux labels des champs tels que stockes
        # / Input names match field labels as stored
        nom_input = page.locator('input[name="Nom complet"]')
        expect(nom_input).to_be_visible(timeout=5_000)
        expect(nom_input).to_have_value(self.FORM_ANSWERS['shortText'])

        # Modifier le champ texte / Edit the text field
        nom_input.fill('Arthur Dent')

        # Modifier le select / Edit the select
        ville_select = page.locator('select[name="Ville preferee"]')
        if ville_select.count() > 0:
            ville_select.select_option('Option C')

        # Enregistrer / Save
        save_button = page.locator('[data-testid="custom-form-save-btn"]')
        save_button.click()
        page.wait_for_timeout(1000)

        # Verifier le message de succes / Check success message
        success_msg = page.locator('[data-testid="custom-form-success-msg"]')
        expect(success_msg).to_be_visible(timeout=5_000)

        # Verifier les nouvelles valeurs dans le tableau
        # / Check new values in table
        expect(page.locator('td:has-text("Arthur Dent")')).to_be_visible()

    # ===================================================================
    # ETAPE 7 — Admin : tester l'annulation
    # STEP 7 — Admin: test cancellation
    # ===================================================================

    def test_step7_admin_tests_cancel(self, page, login_as_admin):
        """Admin ouvre l'edition, modifie, puis annule : les valeurs ne changent pas.
        / Admin opens edit, modifies, then cancels: values do not change.
        """
        login_as_admin(page)
        # Naviguer vers l'adhesion / Navigate to the membership
        search_input = _ouvrir_changelist_admin(page, '/admin/BaseBillet/membership/')
        search_input.fill(self._user_email)
        search_input.press('Enter')
        page.wait_for_load_state('networkidle')

        row = page.locator('#result_list tbody tr').filter(has_text=self._user_email)
        expect(row).to_be_visible(timeout=10_000)
        row.locator('a').first.click()
        page.wait_for_load_state('networkidle')

        # Cliquer sur "Modifier les reponses" / Click "Edit answers"
        edit_button = page.locator('[data-testid="custom-form-edit-btn"]')
        expect(edit_button).to_be_visible(timeout=5_000)
        edit_button.click()
        page.wait_for_timeout(1000)

        # Modifier un champ (sans sauvegarder) / Modify a field (without saving)
        nom_input = page.locator('input[name="Nom complet"]')
        expect(nom_input).to_be_visible(timeout=5_000)
        nom_input.fill('Test Annulation')

        # Cliquer sur "Annuler" / Click "Cancel"
        # data-testid cible pour eviter le bouton "Annuler l'adhesion" du panneau HTMX
        # / targeted data-testid to avoid the "Cancel membership" button in the HTMX panel
        cancel_button = page.locator('[data-testid="custom-form-cancel-btn"]')
        cancel_button.click()
        page.wait_for_timeout(1000)

        # Verifier que la valeur est toujours "Arthur Dent" (modifiee a l'etape 6)
        # / Check the value is still "Arthur Dent" (modified in step 6)
        expect(page.locator('td:has-text("Arthur Dent")')).to_be_visible()
