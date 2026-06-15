"""
Tests E2E : duplication de produit et vérification de l'indépendance.
/ E2E tests: product duplication and independence verification.

Conversion de tests/playwright/tests/25-product-duplication-complex.spec.ts

Ce test vérifie que :
/ This test verifies that:
- Un admin peut créer un produit d'adhésion avec plusieurs tarifs et champs formulaire.
  / An admin can create a membership product with multiple prices and form fields.
- Le produit peut être dupliqué via l'action admin `duplicate_product`.
  / The product can be duplicated via the admin `duplicate_product` action.
- La copie peut être modifiée sans altérer l'original.
  / The copy can be modified without altering the original.
- L'original conserve ses données intactes après modification de la copie.
  / The original retains its data intact after the copy is modified.

ATTENTION : Ce test crée des données persistantes dans la DB de dev (pas de rollback).
Les noms sont suffixés avec un identifiant aléatoire pour éviter les collisions.
/ WARNING: This test creates persistent data in the dev DB (no rollback).
Names are suffixed with a random ID to avoid collisions.
"""

import uuid

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


def _add_inline_price(page, price_data):
    """Ajoute un tarif dans l'inline #prices-group du formulaire admin produit.
    / Adds a price in the admin product form's #prices-group inline.

    Clique sur "a.add-row" dans #prices-group, puis remplit le nouveau rang
    selon l'index détecté avant le clic.
    / Clicks "a.add-row" in #prices-group, then fills the new row using
    the index detected before the click.

    price_data dict attendu / expected:
    - name (str) : libellé du tarif
    - prix (int) : montant (entier pour éviter problème locale FR séparateur décimal)
    - subscription_type (str) : 'Y' | 'M' | ...
    - free_price (bool, optionnel) : prix libre
    """
    prices_section = page.locator('#prices-group')

    # Compter les lignes existantes avant le clic pour calculer l'index.
    # On se base sur l'input "name" (pas __prefix__) pour éviter de compter le
    # template vide.
    # / Count existing rows before click to compute the index.
    # Based on "name" input (excluding __prefix__) to avoid counting the empty template.
    count_before = prices_section.locator(
        'input[name^="prices-"][name$="-name"]:not([name*="__prefix__"])'
    ).count()

    # Cliquer sur le bouton d'ajout de l'inline prices.
    # / Click the add button of the prices inline.
    prices_section.locator('a.add-row').first.click()

    # Attendre que le nouveau champ name soit visible.
    # / Wait for the new name field to become visible.
    form_index = count_before
    name_input = prices_section.locator(f'input[name="prices-{form_index}-name"]')
    name_input.wait_for(state='visible', timeout=5_000)

    # Remplir le nom du tarif.
    # / Fill the price name.
    name_input.fill(price_data['name'])

    # Remplir le montant. Locale FR : passer un entier pour éviter les problèmes
    # de séparateur décimal.
    # / Fill the amount. FR locale: pass integer to avoid decimal separator issues.
    prices_section.locator(
        f'input[name="prices-{form_index}-prix"]'
    ).fill(str(price_data['prix']))

    # Sélectionner le type d'abonnement.
    # / Select the subscription type.
    prices_section.locator(
        f'select[name="prices-{form_index}-subscription_type"]'
    ).select_option(price_data['subscription_type'])

    # Cocher "prix libre" si demandé.
    # / Check "free price" if requested.
    if price_data.get('free_price'):
        checkbox = prices_section.locator(
            f'input[name="prices-{form_index}-free_price"]'
        )
        if checkbox.count() > 0:
            checkbox.check()


def _add_form_field(page, field_data):
    """Ajoute un champ formulaire dans l'inline #form_fields-group.
    / Adds a form field in the #form_fields-group inline.

    Onglet Unfold de l'inline : ancre #form_fields (activeTab Alpine.js).
    Le champ 'order' est caché (drag & drop), on ne le remplit pas.
    / Unfold inline tab: #form_fields anchor (Alpine.js activeTab).
    The 'order' field is hidden (drag & drop), we do not fill it.

    field_data dict attendu / expected:
    - label (str) : libellé du champ
    - type (str) : type de champ ('ST' = texte court, etc.)
    - required (bool) : champ obligatoire
    - help_text (str) : texte d'aide
    - options (str, optionnel) : valeurs CSV pour les champs avec options
    """
    section = page.locator('#form_fields-group')

    # Compter les champs existants pour calculer l'index.
    # / Count existing fields to compute the index.
    count_before = section.locator(
        'input[name^="form_fields-"][name$="-label"]:not([name*="__prefix__"])'
    ).count()

    # Cliquer sur le bouton d'ajout.
    # / Click the add button.
    section.locator('a.add-row').first.click()

    form_index = count_before
    label_input = section.locator(f'input[name="form_fields-{form_index}-label"]')
    label_input.wait_for(state='visible', timeout=5_000)
    label_input.fill(field_data['label'])

    section.locator(
        f'select[name="form_fields-{form_index}-field_type"]'
    ).select_option(field_data['type'])

    if field_data.get('required'):
        section.locator(
            f'input[name="form_fields-{form_index}-required"]'
        ).check()

    # Le champ help_text peut être input ou textarea selon la config Unfold.
    # / help_text can be input or textarea depending on Unfold config.
    help_locator = section.locator(
        f'input[name="form_fields-{form_index}-help_text"], '
        f'textarea[name="form_fields-{form_index}-help_text"]'
    )
    if help_locator.count() > 0:
        help_locator.first.fill(field_data['help_text'])

    # Remplir les options CSV si présentes.
    # / Fill CSV options if present.
    if field_data.get('options'):
        options_locator = section.locator(
            f'input[name="form_fields-{form_index}-options_csv"], '
            f'textarea[name="form_fields-{form_index}-options_csv"]'
        )
        if options_locator.count() > 0:
            options_locator.first.fill(field_data['options'])


def _get_price_names(page):
    """Lit les noms de tous les tarifs remplis dans l'inline #prices-group.
    / Reads the names of all filled prices in the #prices-group inline.

    Retourne une liste de noms non vides.
    / Returns a list of non-empty names.
    """
    price_inputs = page.locator(
        'input[name*="prices-"][name$="-name"]:not([name*="__prefix__"])'
    )
    count = price_inputs.count()
    names = []
    for i in range(count):
        value = price_inputs.nth(i).input_value()
        if value.strip():
            names.append(value)
    return names


def _get_form_field_labels(page):
    """Lit les labels de tous les champs formulaire dans l'inline #form_fields-group.
    / Reads labels of all form fields in #form_fields-group inline.

    Clique d'abord sur l'onglet Unfold (ancre #form_fields) si présent.
    / First clicks the Unfold tab (#form_fields anchor) if present.

    Retourne une liste de labels non vides.
    / Returns a list of non-empty labels.
    """
    # Cliquer sur l'onglet Unfold si disponible (Alpine.js activeTab).
    # / Click Unfold tab if available (Alpine.js activeTab).
    tab = page.locator('a[href="#form_fields"]').first
    if tab.count() > 0:
        tab.click()
        page.wait_for_timeout(500)

    section = page.locator('#form_fields-group')
    label_inputs = section.locator(
        'input[name^="form_fields-"][name$="-label"]:not([name*="__prefix__"])'
    )
    count = label_inputs.count()
    labels = []
    for i in range(count):
        value = label_inputs.nth(i).input_value()
        if value.strip():
            labels.append(value)
    return labels


class TestProductDuplicationComplex:
    """Duplication de produit d'adhésion et vérification de l'indépendance.
    / Duplication of membership product and independence verification.
    """

    def test_duplicate_product_and_verify_independence(self, page, login_as_admin):
        """Crée un produit avec tarifs et champ formulaire, le duplique,
        modifie la copie, et vérifie que l'original est inchangé.
        / Creates a product with prices and a form field, duplicates it,
        modifies the copy, and verifies the original is unchanged.
        """
        # Identifiant unique pour cette exécution — évite les collisions en DB dev.
        # / Unique ID for this run — avoids collisions in the shared dev DB.
        random_id = uuid.uuid4().hex[:8]
        original_product_name = f'Test Duplication {random_id}'

        # --- Étape 1 : Connexion admin ---
        # / Step 1: Admin login
        login_as_admin(page)

        # --- Étape 2 : Créer le produit d'adhésion avec 3 tarifs ---
        # Les adhésions se créent via le proxy MembershipProduct (catégorie fixée,
        # champ caché).
        # / Step 2: Create the membership product with 3 prices.
        # Memberships are created via MembershipProduct proxy (category is set,
        # hidden field).
        page.goto('/admin/BaseBillet/membershipproduct/add/')
        page.wait_for_load_state('networkidle')

        page.locator('input[name="name"]').fill(original_product_name)
        page.locator('input[name="short_description"]').first.fill(
            'Produit de test pour duplication'
        )

        _add_inline_price(page, {'name': 'Tarif Original 1', 'prix': 10, 'subscription_type': 'Y', 'free_price': True})
        _add_inline_price(page, {'name': 'Tarif Original 2', 'prix': 5, 'subscription_type': 'Y'})
        _add_inline_price(page, {'name': 'Tarif Original 3', 'prix': 20, 'subscription_type': 'M'})

        # Sauvegarder et continuer pour pouvoir ajouter les champs formulaire.
        # Django admin Unfold : bouton "Save and continue editing" = name="_continue".
        # / Save and continue editing to then add form fields.
        # Django admin Unfold: "Save and continue editing" button = name="_continue".
        save_and_continue = page.locator(
            'button[name="_continue"], input[name="_continue"]'
        ).first
        save_and_continue.click()
        page.wait_for_load_state('networkidle')

        # --- Étape 3 : Ajouter un champ formulaire ---
        # L'onglet "form_fields" n'apparaît qu'après le premier enregistrement.
        # / Step 3: Add a form field.
        # The "form_fields" tab only appears after the first save.
        tab = page.locator('a[href="#form_fields"]').first
        if tab.count() > 0:
            tab.click()
            page.wait_for_timeout(800)

        _add_form_field(page, {
            'label': 'Champ Original',
            'type': 'ST',
            'required': True,
            'help_text': 'Texte court',
        })

        # Sauvegarder (bouton _save).
        # / Save (button _save).
        page.locator('[name="_save"]').first.click()
        page.wait_for_load_state('networkidle')

        # --- Étape 4 : Vérifier les données de l'original ---
        # Naviguer via la changelist filtrée pour retrouver le produit.
        # / Step 4: Verify the original's data.
        # Navigate via filtered changelist to find the product.
        import urllib.parse
        page.goto(
            f'/admin/BaseBillet/membershipproduct/?q={urllib.parse.quote(original_product_name)}'
        )
        page.wait_for_load_state('networkidle')

        product_link = page.locator('#result_list a, .result-list a').filter(
            has_text=original_product_name
        ).first
        product_link.click()
        page.wait_for_load_state('networkidle')

        original_prices = _get_price_names(page)
        assert 'Tarif Original 1' in original_prices, (
            f"Tarif Original 1 absent. Prix trouvés: {original_prices}"
        )
        assert 'Tarif Original 2' in original_prices, (
            f"Tarif Original 2 absent. Prix trouvés: {original_prices}"
        )
        assert 'Tarif Original 3' in original_prices, (
            f"Tarif Original 3 absent. Prix trouvés: {original_prices}"
        )

        # Vérifier les labels de champs formulaire si présents.
        # / Check form field labels if present.
        original_form_labels = _get_form_field_labels(page)
        if original_form_labels:
            assert 'Champ Original' in original_form_labels, (
                f"Champ Original absent. Labels: {original_form_labels}"
            )

        # --- Étape 5 : Dupliquer le produit ---
        # La vue duplicate_product redirige vers le referrer (la changelist).
        # On navigue d'abord sur la changelist pour que Referer soit set, puis
        # on crée et clique un lien JavaScript vers l'URL de duplication.
        # / Step 5: Duplicate the product.
        # The duplicate_product view redirects to the referrer (changelist).
        # Navigate to changelist first so Referer is set, then create & click
        # a JS link to the duplicate URL.
        list_url = f'/admin/BaseBillet/membershipproduct/?q={urllib.parse.quote(original_product_name)}'
        page.goto(list_url)
        page.wait_for_load_state('networkidle')

        # Extraire l'UUID du produit depuis le lien d'édition.
        # / Extract the product UUID from the edit link.
        product_row = page.locator('tr').filter(has_text=original_product_name).first
        expect(product_row).to_be_visible(timeout=5_000)

        edit_link = product_row.locator('a').first
        edit_href = edit_link.get_attribute('href')
        assert edit_href, f"Lien d'édition introuvable. product_row visible: {product_row.is_visible()}"

        import re as _re
        match = _re.search(r'/([a-f0-9-]+)/change/', edit_href)
        assert match, f"UUID introuvable dans href: {edit_href}"
        product_id = match.group(1)

        duplicate_url = f'/admin/BaseBillet/membershipproduct/{product_id}/duplicate_product/'

        # Déclencher la duplication depuis la changelist (Referer = liste) et
        # attendre la redirection vers /admin/BaseBillet/membershipproduct/.
        # En Playwright Python, le prédicat url reçoit un objet URL dont on doit
        # extraire le chemin via str() ou la propriété .pathname (non dispo).
        # On compare directement sur la représentation str de l'URL.
        # / Trigger duplication from changelist (Referer = list) and wait for
        # redirect to /admin/BaseBillet/membershipproduct/.
        # In Playwright Python, the url predicate receives a URL object; we compare
        # against its string representation.
        with page.expect_navigation(
            url=lambda u: '/admin/BaseBillet/membershipproduct/' in str(u),
            timeout=15_000,
        ):
            page.evaluate(
                """(url) => {
                    const link = document.createElement('a');
                    link.href = url;
                    link.style.display = 'none';
                    document.body.appendChild(link);
                    link.click();
                }""",
                duplicate_url,
            )

        page.wait_for_load_state('networkidle')

        # --- Étape 6 : Modifier la copie ---
        # Le nom de la copie est suffixé avec " [DUPLICATA]".
        # / Step 6: Modify the copy.
        # The copy's name is suffixed with " [DUPLICATA]".
        page.goto(
            f'/admin/BaseBillet/membershipproduct/?q={urllib.parse.quote(original_product_name)}'
        )
        page.wait_for_load_state('networkidle')

        duplicate_link = page.locator('#result_list a, .result-list a').filter(
            has_text=f'{original_product_name} [DUPLICATA]'
        ).first

        # Vérifier que la copie existe, sinon lister tous les produits présents
        # pour aider au diagnostic.
        # / Verify the copy exists, otherwise list all present products for debug.
        if duplicate_link.count() == 0:
            all_links = page.locator('#result_list a, .result-list a').all()
            found_texts = [lnk.text_content() for lnk in all_links]
            pytest.fail(
                f'Produit dupliqué "{original_product_name} [DUPLICATA]" introuvable. '
                f'Produits présents: {found_texts}'
            )

        duplicate_link.click()
        page.wait_for_load_state('networkidle')

        # Renommer la copie.
        # / Rename the copy.
        page.locator('input[name="name"]').fill(f'{original_product_name} (copie)')

        # Modifier les noms des tarifs : remplacer "Original" par "Dupliqué".
        # PIÈGE 9.6 : ne pas compter par nombre exact, vérifier PAR NOM.
        # Le signal post_save peut ajouter un "Tarif gratuit" auto.
        # / Modify price names: replace "Original" with "Dupliqué".
        # TRAP 9.6: do not count by exact number, check BY NAME.
        # The post_save signal may add a "Tarif gratuit" automatically.
        price_inputs = page.locator(
            'input[name*="prices-"][name$="-name"]:not([name*="__prefix__"])'
        )
        price_count = price_inputs.count()
        for i in range(price_count):
            current_value = price_inputs.nth(i).input_value()
            if 'Original' in current_value:
                new_value = current_value.replace('Original', 'Dupliqué')
                price_inputs.nth(i).fill(new_value)

        # Modifier les labels des champs formulaire dans la copie.
        # / Modify form field labels in the copy.
        tab = page.locator('a[href="#form_fields"]').first
        if tab.count() > 0:
            tab.click()
            page.wait_for_timeout(500)

        section = page.locator('#form_fields-group')
        label_inputs = section.locator(
            'input[name^="form_fields-"][name$="-label"]:not([name*="__prefix__"])'
        )
        label_count = label_inputs.count()
        for i in range(label_count):
            current_value = label_inputs.nth(i).input_value()
            if 'Original' in current_value:
                new_value = current_value.replace('Original', 'Dupliqué')
                label_inputs.nth(i).fill(new_value)

        # Sauvegarder la copie modifiée.
        # / Save the modified copy.
        page.locator('[name="_save"]').first.click()
        page.wait_for_load_state('networkidle')

        # --- Étape 7 : Vérifier que l'original est inchangé ---
        # / Step 7: Verify the original is unchanged.
        page.goto(
            f'/admin/BaseBillet/membershipproduct/?q={urllib.parse.quote(original_product_name)}'
        )
        page.wait_for_load_state('networkidle')

        # Filtrer pour ne trouver que l'original (sans "[DUPLICATA]" ni "copie").
        # / Filter to find only the original (without "[DUPLICATA]" or "copie").
        original_link = page.locator('#result_list a, .result-list a').filter(
            has_text=original_product_name
        ).filter(
            has_not_text='[DUPLICATA]'
        ).filter(
            has_not_text='copie'
        ).first
        original_link.click()
        page.wait_for_load_state('networkidle')

        original_prices_after = _get_price_names(page)
        assert 'Tarif Original 1' in original_prices_after, (
            f"Tarif Original 1 modifié dans l'original ! Prix: {original_prices_after}"
        )
        assert 'Tarif Original 2' in original_prices_after, (
            f"Tarif Original 2 modifié dans l'original ! Prix: {original_prices_after}"
        )
        assert 'Tarif Original 3' in original_prices_after, (
            f"Tarif Original 3 modifié dans l'original ! Prix: {original_prices_after}"
        )
        # Tous les prix de l'original doivent encore contenir "Original".
        # (filtre sur les noms qui ne sont pas vides et pas "Tarif gratuit")
        # / All original prices must still contain "Original".
        # (filter on names that are not empty and not "Tarif gratuit")
        non_auto_prices = [
            p for p in original_prices_after
            if p and 'gratuit' not in p.lower()
        ]
        assert all('Original' in p for p in non_auto_prices), (
            f"Un tarif de l'original a été modifié : {non_auto_prices}"
        )

        original_form_labels_after = _get_form_field_labels(page)
        if original_form_labels_after:
            assert 'Champ Original' in original_form_labels_after, (
                f"Champ Original modifié dans l'original ! Labels: {original_form_labels_after}"
            )
            non_auto_labels = [
                lbl for lbl in original_form_labels_after if lbl
            ]
            assert all('Original' in lbl for lbl in non_auto_labels), (
                f"Un label de l'original a été modifié : {non_auto_labels}"
            )

        # --- Étape 8 : Vérifier que la copie contient bien les modifications ---
        # / Step 8: Verify the copy contains the modifications.
        page.goto(
            f'/admin/BaseBillet/membershipproduct/?q={urllib.parse.quote(original_product_name)}'
        )
        page.wait_for_load_state('networkidle')

        copy_link = page.locator('#result_list a, .result-list a').filter(
            has_text=f'{original_product_name} (copie)'
        ).first
        copy_link.click()
        page.wait_for_load_state('networkidle')

        duplicated_prices = _get_price_names(page)
        assert 'Tarif Dupliqué 1' in duplicated_prices, (
            f"Tarif Dupliqué 1 absent de la copie ! Prix: {duplicated_prices}"
        )
        assert 'Tarif Dupliqué 2' in duplicated_prices, (
            f"Tarif Dupliqué 2 absent de la copie ! Prix: {duplicated_prices}"
        )
        assert 'Tarif Dupliqué 3' in duplicated_prices, (
            f"Tarif Dupliqué 3 absent de la copie ! Prix: {duplicated_prices}"
        )
        # Tous les prix de la copie (hors auto) doivent contenir "Dupliqué".
        # / All copy prices (excluding auto) must contain "Dupliqué".
        non_auto_copy_prices = [
            p for p in duplicated_prices
            if p and 'gratuit' not in p.lower()
        ]
        assert all('Dupliqué' in p for p in non_auto_copy_prices), (
            f"Un tarif de la copie n'a pas été modifié : {non_auto_copy_prices}"
        )

        duplicated_form_labels = _get_form_field_labels(page)
        if duplicated_form_labels:
            assert 'Champ Dupliqué' in duplicated_form_labels, (
                f"Champ Dupliqué absent de la copie ! Labels: {duplicated_form_labels}"
            )
            non_auto_copy_labels = [lbl for lbl in duplicated_form_labels if lbl]
            assert all('Dupliqué' in lbl for lbl in non_auto_copy_labels), (
                f"Un label de la copie n'a pas été modifié : {non_auto_copy_labels}"
            )
