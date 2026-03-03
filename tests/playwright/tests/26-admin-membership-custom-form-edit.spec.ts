import { test, expect, Page } from '@playwright/test';
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
 *
 * Prérequis : le test 27 doit avoir été exécuté avant (il crée une adhésion avec custom_form).
 * Prerequisite: test 27 must have been run before (it creates a membership with custom_form).
 */

// -- Helper : ajouter un champ dynamique dans l'admin inline --
// -- Helper: add a dynamic form field in the admin inline --
async function addFormField(page: Page, fieldData: {
    label: string;
    type: string;
    required: boolean;
    options?: string;
}) {
    // Trouver la section inline "Dynamic form field"
    // Find the "Dynamic form field" inline section
    const section = page.locator('.inline-group').filter({
        has: page.locator('h2:has-text("Dynamic form field")'),
    });
    const addButton = section.locator('a:has-text("Add another")').first();
    await addButton.click();

    // Attendre la dernière ligne ajoutée
    // Wait for the last added row
    const lastRow = section.locator('tr.form-row:not(.empty-form)').last();
    await lastRow.waitFor({ state: 'visible', timeout: 5000 });

    console.log(`  ✓ Adding field / Ajout du champ : ${fieldData.label}`);

    await lastRow.locator('input[name*="-label"]').fill(fieldData.label);
    await lastRow.locator('select[name*="-field_type"]').selectOption(fieldData.type);

    if (fieldData.required) {
        await lastRow.locator('input[name*="-required"]').check();
    }

    if (fieldData.options) {
        await lastRow.locator('input[name*="-options"]').fill(fieldData.options);
    }
}

// -- Données de test / Test data --
const randomId = Math.random().toString(36).substring(2, 10);
const PRODUCT_NAME = `Adhésion Test Edit ${randomId}`;
const USER_EMAIL = `jturbeaux+edit${randomId}@pm.me`;

test.describe('Admin Membership Custom Form Edit / Édition custom_form adhésion admin', () => {

    test.beforeEach(async ({ page }) => {
        // Connexion en tant qu'admin
        // Login as admin
        await loginAsAdmin(page);
        console.log('✓ Logged in as admin / Connecté en tant qu\'admin');
    });

    test('should edit custom form fields of membership / doit éditer les champs du formulaire personnalisé', async ({ page }) => {

        // Étape 1 : Créer un produit d'adhésion avec un tarif et des champs dynamiques
        // Step 1: Create a membership product with a price and dynamic fields
        await test.step('Create membership product / Créer produit adhésion', async () => {
            await page.goto('/admin/BaseBillet/product/add/');
            await page.waitForLoadState('networkidle');

            // Nom du produit / Product name
            await page.fill('input[name="name"]', PRODUCT_NAME);

            // Catégorie : Adhésion / Category: Membership
            await page.selectOption('select[name="categorie_article"]', 'A');

            // Description courte / Short description
            await page.fill('input[name="short_description"]', 'Test édition custom_form admin');

            // Ajouter un tarif gratuit pour pouvoir créer l'adhésion sans paiement
            // Add a free price to create the membership without payment
            const addPriceButton = page.locator('a:has-text("Add another"), button:has-text("Add another")').first();
            await addPriceButton.scrollIntoViewIfNeeded();
            await addPriceButton.click();
            await page.waitForTimeout(500);

            await page.fill('input[name="prices-0-name"]', 'Gratuit annuel');
            await page.fill('input[name="prices-0-prix"]', '0');
            // Y = 365 jours (année)
            // Y = 365 days (year)
            await page.selectOption('select[name="prices-0-subscription_type"]', 'Y');

            // Cocher "Publier" / Check "Publish"
            await page.check('input[name="publish"]');

            // "Save and continue editing" pour rester sur la page d'édition
            // "Save and continue editing" to stay on the edit page
            const saveAndContinue = page.locator('button[name="_continue"]').first();
            await saveAndContinue.click();
            await page.waitForLoadState('networkidle');

            // Vérifier pas d'erreur / Check no errors
            const errorList = page.locator('.errorlist');
            expect(await errorList.count()).toBe(0);

            console.log(`✓ Created product: ${PRODUCT_NAME}`);
        });

        // Étape 2 : Ajouter des champs dynamiques au produit
        // Step 2: Add dynamic fields to the product
        await test.step('Add custom fields / Ajouter champs personnalisés', async () => {
            // Ouvrir l'onglet "Dynamic form field" (Unfold tabs)
            // Open the "Dynamic form field" tab (Unfold tabs)
            const tab = page.locator('button:has-text("Dynamic form field"), a:has-text("Dynamic form field")').first();
            if (await tab.count() > 0) {
                await tab.click();
                await page.waitForTimeout(1000);
            }

            // Champ 1 : Texte court (nom) — obligatoire
            // Field 1: Short text (name) — required
            await addFormField(page, {
                label: 'Nom complet',
                type: 'ST',
                required: true,
            });

            // Champ 2 : Sélection simple (ville)
            // Field 2: Single select (city)
            await addFormField(page, {
                label: 'Ville',
                type: 'SS',
                required: false,
                options: 'Paris, Lyon, Marseille, Toulouse',
            });

            // Champ 3 : Booléen (newsletter)
            // Field 3: Boolean (newsletter)
            await addFormField(page, {
                label: 'Newsletter',
                type: 'BL',
                required: false,
            });

            // Sauvegarder / Save
            const saveAndContinue = page.locator('button[name="_continue"]').first();
            await saveAndContinue.click();
            await page.waitForLoadState('networkidle');

            const errorList = page.locator('.errorlist');
            expect(await errorList.count()).toBe(0);

            console.log('✓ Added 3 custom fields to product');
        });

        // Étape 3 : Créer une adhésion depuis l'admin
        // Step 3: Create a membership from admin
        await test.step('Create membership via admin / Créer adhésion via admin', async () => {
            await page.goto('/admin/BaseBillet/membership/add/');
            await page.waitForLoadState('networkidle');

            // Remplir le formulaire d'ajout d'adhésion
            // Fill the membership add form
            await page.fill('input[name="email"]', USER_EMAIL);

            // Sélectionner le tarif qu'on vient de créer par son texte
            // Select the price we just created by its text content
            const priceSelect = page.locator('select[name="price"]');
            await priceSelect.waitFor({ state: 'visible', timeout: 5000 });
            // Chercher l'option qui contient le nom du produit
            // Find the option containing the product name
            const allOptions = await priceSelect.locator('option').all();
            let targetValue = '';
            for (const option of allOptions) {
                const text = await option.textContent();
                if (text && text.includes(PRODUCT_NAME)) {
                    targetValue = await option.getAttribute('value') || '';
                    break;
                }
            }
            expect(targetValue).not.toBe('');
            await priceSelect.selectOption(targetValue);

            // Sauvegarder avec "Save and continue editing"
            // Save with "Save and continue editing"
            const saveAndContinue = page.locator('button[name="_continue"]').first();
            await saveAndContinue.click();
            await page.waitForLoadState('networkidle');

            console.log(`✓ Created membership for: ${USER_EMAIL}`);
        });

        // Étape 4 : Injecter des données custom_form via manage.py
        // Step 4: Inject custom_form data via manage.py
        // L'admin ne permet pas de remplir custom_form directement,
        // on utilise le shell Django pour simuler des réponses existantes.
        // The admin doesn't allow filling custom_form directly,
        // we use the Django shell to simulate existing answers.
        await test.step('Inject custom_form data / Injecter données custom_form', async () => {
            // Extraire le PK de l'adhésion depuis l'URL de la page
            // L'URL admin est de la forme /admin/BaseBillet/membership/<pk>/change/
            // Extract the membership PK from the page URL
            // Admin URL is like /admin/BaseBillet/membership/<pk>/change/
            const currentUrl = page.url();
            const pkMatch = currentUrl.match(/\/membership\/(\d+)\/change/);
            expect(pkMatch).not.toBeNull();
            const membershipPk = pkMatch![1];

            // Utiliser manage.py tenant_command shell pour injecter le custom_form
            // Use manage.py tenant_command shell to inject the custom_form
            const { execSync } = require('child_process');
            const shellCmd = `docker exec lespass_django poetry run python /DjangoFiles/manage.py tenant_command shell -s lespass -c "
from BaseBillet.models import Membership
m = Membership.objects.get(pk=${membershipPk})
m.custom_form = {'Nom complet': 'Jean Dupont', 'Ville': 'Paris', 'Newsletter': True}
m.save()
print('OK')
"`;
            const result = execSync(shellCmd, { encoding: 'utf-8', timeout: 15000 });
            expect(result).toContain('OK');

            // Recharger la page pour voir le custom_form
            // Reload the page to see the custom_form
            await page.reload();
            await page.waitForLoadState('networkidle');

            console.log(`✓ Injected custom_form for membership PK: ${membershipPk}`);
        });

        // Étape 5 : Tester l'interface d'édition des champs personnalisés
        // Step 5: Test the custom fields edit interface
        await test.step('Edit custom form fields via HTMX / Éditer champs via HTMX', async () => {
            // Vérifier que le bouton "Modifier les réponses" est présent
            // Check that "Modify answers" button is present
            const editButton = page.locator('[data-testid="custom-form-edit-btn"]');
            await expect(editButton).toBeVisible({ timeout: 5000 });
            console.log('✓ Edit button is visible / Bouton édition visible');

            // Cliquer sur le bouton pour ouvrir le formulaire d'édition
            // Click button to open edit form
            await editButton.click();
            await page.waitForTimeout(1000);

            // Vérifier que le formulaire d'édition est affiché (le container change de contenu via HTMX)
            // Check that edit form is displayed (container content changes via HTMX)
            const nomInput = page.locator('input[name="Nom complet"]');
            await expect(nomInput).toBeVisible({ timeout: 5000 });
            await expect(nomInput).toHaveValue('Jean Dupont');
            console.log('✓ Name field has correct value / Champ nom a la bonne valeur');

            const villeSelect = page.locator('select[name="Ville"]');
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

            // Vérifier le message de succès via data-testid
            // Check success message via data-testid
            const successMessage = page.locator('[data-testid="custom-form-success-msg"]');
            await expect(successMessage).toBeVisible({ timeout: 5000 });
            console.log('✓ Changes saved successfully / Modifications enregistrées');
        });

        // Étape 6 : Tester l'annulation d'édition
        // Step 6: Test edit cancellation
        await test.step('Test cancel edit / Tester annulation édition', async () => {
            // Cliquer à nouveau sur modifier / Click edit again
            const editButton = page.locator('[data-testid="custom-form-edit-btn"]');
            await editButton.click();
            await page.waitForTimeout(1000);

            // Modifier une valeur / Modify a value
            const nomInput = page.locator('input[name="Nom complet"]');
            await expect(nomInput).toBeVisible({ timeout: 3000 });
            await nomInput.fill('Test Annulation');

            // Cliquer sur Annuler / Click Cancel
            const cancelButton = page.locator('button:has-text("Annuler"), button:has-text("Cancel")').first();
            await cancelButton.click();
            await page.waitForTimeout(500);

            // Vérifier que la valeur n'a pas changé (Marie Martin toujours affichée)
            // Check value hasn't changed (Marie Martin still displayed)
            const tableCell = page.locator('text=Marie Martin');
            await expect(tableCell).toBeVisible({ timeout: 3000 });
            console.log('✓ Cancel works correctly / Annulation fonctionne');
        });

        // Étape 7 : Tester la validation des champs obligatoires (HTML native)
        // Step 7: Test required fields validation (HTML native)
        await test.step('Test required fields validation / Tester validation champs obligatoires', async () => {
            // Ouvrir l'édition / Open edit
            const editButton = page.locator('[data-testid="custom-form-edit-btn"]');
            await editButton.click();
            await page.waitForTimeout(1000);

            // Vider un champ obligatoire / Empty a required field
            const nomInput = page.locator('input[name="Nom complet"]');
            await expect(nomInput).toBeVisible({ timeout: 3000 });
            await nomInput.fill('');

            // Essayer de sauvegarder / Try to save
            const saveButton = page.locator('[data-testid="custom-form-save-btn"]');
            await saveButton.click();
            await page.waitForTimeout(500);

            // La validation HTML native empêche la soumission.
            // On vérifie que le formulaire est toujours affiché (pas soumis).
            // HTML native validation prevents submission.
            // We verify the form is still displayed (not submitted).
            await expect(nomInput).toBeVisible({ timeout: 3000 });

            // Vérifier que l'input a l'attribut required
            // Check the input has the required attribute
            const isRequired = await nomInput.getAttribute('required');
            expect(isRequired).not.toBeNull();
            console.log('✓ Required field validation works (HTML native) / Validation champ obligatoire fonctionne (HTML natif)');

            // Annuler / Cancel
            const cancelButton = page.locator('[data-testid="custom-form-cancel-btn"]');
            await cancelButton.click();
            await page.waitForTimeout(500);
        });

        console.log('✅ All tests passed / Tous les tests réussis');
    });
});
