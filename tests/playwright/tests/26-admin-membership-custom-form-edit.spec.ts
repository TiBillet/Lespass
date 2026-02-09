import { test, expect } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';

/**
 * Test de l'édition des champs custom_form d'une adhésion dans l'admin
 * Test for editing custom_form fields of a membership in the admin
 *
 * Ce test vérifie que :
 * This test verifies that:
 * - Un admin peut accéder à l'interface d'édition des champs personnalisés
 * - An admin can access the custom fields edit interface
 * - Les champs sont correctement affichés avec leurs valeurs actuelles
 * - Fields are correctly displayed with their current values
 * - Les modifications sont sauvegardées et affichées
 * - Modifications are saved and displayed
 * - Les erreurs de validation sont affichées
 * - Validation errors are displayed
 */

test.describe('Admin Membership Custom Form Edit / Édition custom_form adhésion admin', () => {

    test.beforeEach(async ({ page }) => {
        // Connexion en tant qu'admin
        // Login as admin
        await loginAsAdmin(page);
        console.log('✓ Logged in as admin / Connecté en tant qu\'admin');
    });

    test('should edit custom form fields of membership / doit éditer les champs du formulaire personnalisé', async ({ page }) => {

        // Étape 1 : Créer un produit d'adhésion avec des champs personnalisés
        // Step 1: Create a membership product with custom fields
        await test.step('Create membership product with custom fields / Créer produit adhésion avec champs personnalisés', async () => {
            await page.goto('/admin/BaseBillet/product/add/');
            await page.waitForLoadState('networkidle');

            // Nom du produit / Product name
            const productName = `Adhésion Test Edit Form ${Date.now()}`;
            await page.fill('input[name="name"]', productName);

            // Catégorie : Adhésion / Category: Membership
            await page.selectOption('select[name="categorie_article"]', 'A');

            // Description courte / Short description
            await page.fill('input[name="short_description"]', 'Adhésion pour test édition formulaire personnalisé');

            // Ajouter un tarif / Add a price
            const addPriceButton = page.locator('a:has-text("Add another"), button:has-text("Add another")').first();
            await addPriceButton.click();
            await page.waitForTimeout(500);

            await page.fill('input[name="prices-0-name"]', 'Tarif Standard');
            await page.fill('input[name="prices-0-prix"]', '50');
            await page.selectOption('select[name="prices-0-subscription_type"]', 'AN');

            // Cocher "Publier" pour que le produit soit visible
            // Check "Publish" so the product is visible
            await page.check('input[name="publish"]');

            // Sauvegarder le produit / Save the product
            const saveButton = page.locator('button[type="submit"]:has-text("Save"), input[name="_save"]').first();
            await saveButton.click();
            await page.waitForLoadState('networkidle');

            console.log(`✓ Created product: ${productName}`);
        });

        // Étape 2 : Ajouter des champs personnalisés au produit
        // Step 2: Add custom fields to the product
        await test.step('Add custom fields to product / Ajouter champs personnalisés au produit', async () => {
            // On est maintenant sur la page de modification du produit
            // We are now on the product edit page

            // Trouver la section "Form fields" et ajouter des champs
            // Find the "Form fields" section and add fields
            const addFormFieldButton = page.locator('a:has-text("Add another Form Field"), a:has-text("Ajouter un autre")').last();

            // Champ 1 : Texte court (nom) / Field 1: Short text (name)
            await addFormFieldButton.click();
            await page.waitForTimeout(500);

            await page.fill('input[name="form_fields-0-label"]', 'Nom complet');
            await page.selectOption('select[name="form_fields-0-field_type"]', 'ST');
            await page.check('input[name="form_fields-0-required"]');

            // Champ 2 : Sélection simple (ville) / Field 2: Single select (city)
            await addFormFieldButton.click();
            await page.waitForTimeout(500);

            await page.fill('input[name="form_fields-1-label"]', 'Ville');
            await page.selectOption('select[name="form_fields-1-field_type"]', 'SS');
            await page.fill('input[name="form_fields-1-options"]', 'Paris, Lyon, Marseille, Toulouse');

            // Champ 3 : Booléen (newsletter) / Field 3: Boolean (newsletter)
            await addFormFieldButton.click();
            await page.waitForTimeout(500);

            await page.fill('input[name="form_fields-2-label"]', 'S\'abonner à la newsletter');
            await page.selectOption('select[name="form_fields-2-field_type"]', 'BL');

            // Sauvegarder / Save
            const saveButton = page.locator('button[type="submit"]:has-text("Save"), input[name="_save"]').first();
            await saveButton.click();
            await page.waitForLoadState('networkidle');

            console.log('✓ Added 3 custom fields to product');
        });

        // Étape 3 : Créer une adhésion avec des réponses au formulaire personnalisé
        // Step 3: Create a membership with custom form answers
        let membershipUuid = '';
        await test.step('Create membership with custom form answers / Créer adhésion avec réponses formulaire', async () => {
            await page.goto('/admin/BaseBillet/membership/add/');
            await page.waitForLoadState('networkidle');

            // Sélectionner l'utilisateur (admin connecté) / Select user (logged-in admin)
            const userSelect = page.locator('select[name="user"]').first();
            await userSelect.selectOption({ index: 1 }); // Sélectionner le premier utilisateur disponible

            // Sélectionner le produit créé précédemment / Select previously created product
            const priceSelect = page.locator('select[name="price"]').first();
            const options = await priceSelect.locator('option').all();
            if (options.length > 1) {
                await priceSelect.selectOption({ index: options.length - 1 }); // Dernier produit ajouté
            }

            // Remplir les champs custom_form en JSON
            // Fill custom_form fields as JSON
            const customFormData = {
                'nom-complet': 'Jean Dupont',
                'ville': 'Paris',
                's-abonner-a-la-newsletter': true
            };

            const customFormTextarea = page.locator('textarea[name="custom_form"]');
            await customFormTextarea.fill(JSON.stringify(customFormData, null, 2));

            // Sauvegarder / Save
            const saveButton = page.locator('button[type="submit"]:has-text("Save"), input[name="_save"]').first();
            await saveButton.click();
            await page.waitForLoadState('networkidle');

            // Extraire l'UUID depuis l'URL
            // Extract UUID from URL
            const currentUrl = page.url();
            const uuidMatch = currentUrl.match(/\/([a-f0-9-]{36})\//);
            if (uuidMatch) {
                membershipUuid = uuidMatch[1];
                console.log(`✓ Created membership with UUID: ${membershipUuid}`);
            }
        });

        // Étape 4 : Tester l'interface d'édition des champs personnalisés
        // Step 4: Test the custom fields edit interface
        await test.step('Edit custom form fields via HTMX interface / Éditer champs via interface HTMX', async () => {
            // Vérifier que le bouton "Modifier les réponses" est présent
            // Check that "Modify answers" button is present
            const editButton = page.locator('button:has-text("Modifier les réponses"), button:has-text("Modifier")').first();
            await expect(editButton).toBeVisible({ timeout: 5000 });
            console.log('✓ Edit button is visible / Bouton édition visible');

            // Cliquer sur le bouton pour ouvrir le formulaire d'édition
            // Click button to open edit form
            await editButton.click();
            await page.waitForTimeout(1000);

            // Vérifier que le formulaire d'édition est affiché
            // Check that edit form is displayed
            const formContainer = page.locator('#custom-form-edit-container');
            await expect(formContainer).toBeVisible({ timeout: 3000 });
            console.log('✓ Edit form is displayed / Formulaire édition affiché');

            // Vérifier que les champs sont pré-remplis avec les valeurs actuelles
            // Check that fields are pre-filled with current values
            const nomInput = page.locator('input[name="nom-complet"]');
            await expect(nomInput).toHaveValue('Jean Dupont');
            console.log('✓ Name field has correct value / Champ nom a la bonne valeur');

            const villeSelect = page.locator('select[name="ville"]');
            await expect(villeSelect).toHaveValue('Paris');
            console.log('✓ City field has correct value / Champ ville a la bonne valeur');

            // Modifier les valeurs / Modify values
            await nomInput.fill('Marie Martin');
            await villeSelect.selectOption('Lyon');
            console.log('✓ Modified field values / Valeurs modifiées');

            // Sauvegarder les modifications / Save changes
            const saveButton = page.locator('button[type="submit"]:has-text("Enregistrer")').first();
            await saveButton.click();
            await page.waitForTimeout(1000);

            // Vérifier le message de succès / Check success message
            const successMessage = page.locator('text=/modifications.*enregistrées|success/i');
            await expect(successMessage).toBeVisible({ timeout: 3000 });
            console.log('✓ Success message displayed / Message de succès affiché');

            // Vérifier que les nouvelles valeurs sont affichées dans le tableau
            // Check that new values are displayed in the table
            const tableCell = page.locator('td:has-text("Marie Martin")');
            await expect(tableCell).toBeVisible({ timeout: 3000 });
            console.log('✓ New values displayed in table / Nouvelles valeurs affichées');
        });

        // Étape 5 : Tester l'annulation d'édition
        // Step 5: Test edit cancellation
        await test.step('Test cancel edit / Tester annulation édition', async () => {
            // Cliquer à nouveau sur modifier / Click edit again
            const editButton = page.locator('button:has-text("Modifier")').first();
            await editButton.click();
            await page.waitForTimeout(500);

            // Modifier une valeur / Modify a value
            const nomInput = page.locator('input[name="nom-complet"]');
            await nomInput.fill('Test Annulation');

            // Cliquer sur Annuler / Click Cancel
            const cancelButton = page.locator('button:has-text("Annuler")').first();
            await cancelButton.click();
            await page.waitForTimeout(500);

            // Vérifier que la valeur n'a pas changé / Check value hasn't changed
            const tableCell = page.locator('td:has-text("Marie Martin")');
            await expect(tableCell).toBeVisible({ timeout: 3000 });
            console.log('✓ Cancel works correctly / Annulation fonctionne');
        });

        // Étape 6 : Tester la validation des champs obligatoires
        // Step 6: Test required fields validation
        await test.step('Test required fields validation / Tester validation champs obligatoires', async () => {
            // Ouvrir l'édition / Open edit
            const editButton = page.locator('button:has-text("Modifier")').first();
            await editButton.click();
            await page.waitForTimeout(500);

            // Vider un champ obligatoire / Empty a required field
            const nomInput = page.locator('input[name="nom-complet"]');
            await nomInput.fill('');

            // Essayer de sauvegarder / Try to save
            const saveButton = page.locator('button[type="submit"]:has-text("Enregistrer")').first();
            await saveButton.click();
            await page.waitForTimeout(500);

            // Vérifier qu'un message d'erreur est affiché / Check error message is displayed
            const errorMessage = page.locator('text=/obligatoire|required/i');
            await expect(errorMessage).toBeVisible({ timeout: 3000 });
            console.log('✓ Required field validation works / Validation champ obligatoire fonctionne');

            // Annuler / Cancel
            const cancelButton = page.locator('button:has-text("Annuler")').first();
            await cancelButton.click();
            await page.waitForTimeout(500);
        });

        console.log('✅ All tests passed / Tous les tests réussis');
    });
});
