import { test, expect, Page } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';
import { fillStripeCard } from './utils/stripe';

/**
 * TEST: Full E2E cycle — Membership with all dynamic form field types
 * TEST : Cycle E2E complet — Adhésion avec tous les types de champs dynamiques
 *
 * 1. Admin creates a membership product with 6 field types (ST, LT, SS, SR, MS, BL)
 * 2. Public user subscribes, fills the form, pays via Stripe
 * 3. Admin verifies: membership validated, answers displayed, add free field, edit, cancel
 */

// -- Données de test / Test data --

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

const randomId = generateRandomId();
const PRODUCT_NAME = `Adhésion DynForm Test ${randomId}`;
const USER_EMAIL = `jturbeaux+dynform${randomId}@pm.me`;

const FORM_ANSWERS = {
  shortText: 'Douglas Adams',
  longText: 'Écrivain de science-fiction britannique',
  singleSelect: 'Option B',
  radioSelect: 'Radio 2',
  multiSelect: ['Choix A', 'Choix C'],
  boolean: true,
};

// -- Helper : ajouter un champ dynamique dans l'admin inline --
// -- Helper: add a dynamic form field in the admin inline --

async function addFormField(page: Page, fieldData: {
  label: string;
  type: string;
  required: boolean;
  help_text: string;
  order: number;
  options?: string;
}) {
  const section = page.locator('.inline-group').filter({
    has: page.locator('h2:has-text("Dynamic form field")'),
  });
  const addButton = section.locator('a:has-text("Add another")').first();
  await addButton.click();

  const lastRow = section.locator('tr.form-row:not(.empty-form)').last();
  await lastRow.waitFor({ state: 'visible', timeout: 5000 });

  console.log(`✓ Adding field / Ajout du champ : ${fieldData.label}`);

  await lastRow.locator('input[name*="-label"]').fill(fieldData.label);
  await lastRow.locator('select[name*="-field_type"]').selectOption(fieldData.type);

  if (fieldData.required) {
    await lastRow.locator('input[name*="-required"]').check();
  }

  await lastRow.locator('input[name*="-help_text"], textarea[name*="-help_text"]').fill(fieldData.help_text);
  await lastRow.locator('input[name*="-order"]').fill(fieldData.order.toString(), { force: true });

  if (fieldData.options) {
    // Le champ s'appelle "options_csv" (input text, pas textarea)
    // The field is named "options_csv" (text input, not textarea)
    const optionsInput = lastRow.locator('input[name*="-options_csv"]');
    await optionsInput.waitFor({ state: 'visible', timeout: 5000 });
    await optionsInput.fill(fieldData.options);
  }
}


test.describe('Full Membership Dynamic Form Cycle / Cycle complet formulaire dynamique adhésion', () => {

  // ===================================================================
  // ÉTAPE 1 — Admin : créer le produit adhésion avec champs dynamiques
  // STEP 1 — Admin: create membership product with dynamic form fields
  // ===================================================================

  test('Step 1: Admin creates membership product / Étape 1 : Admin crée le produit', async ({ page }) => {

    await test.step('Login as admin / Connexion admin', async () => {
      await loginAsAdmin(page);
    });

    await test.step('Fill product info / Remplir les infos produit', async () => {
      await page.goto('/admin/BaseBillet/product/add/');
      await page.waitForLoadState('networkidle');

      await page.locator('input[name="name"]').fill(PRODUCT_NAME);
      await page.locator('input[name="short_description"]').fill('Test E2E formulaire dynamique complet');
      await page.locator('select[name="categorie_article"]').selectOption('A');
      await page.check('input[name="publish"]');

      console.log(`✓ Product info filled: ${PRODUCT_NAME}`);
    });

    await test.step('Add price inline / Ajouter un tarif', async () => {
      // Un tarif est obligatoire pour sauvegarder un produit adhésion
      // A price is required to save a membership product
      // Scroller vers le bas pour trouver le bouton "Add another" des prix
      // Scroll down to find the "Add another" button for prices
      const addPriceButton = page.locator('a:has-text("Add another"), button:has-text("Add another")').first();
      await addPriceButton.scrollIntoViewIfNeeded();
      await addPriceButton.click();
      await page.waitForTimeout(500);

      // Remplir le tarif gratuit (pattern du test 26)
      // Fill free price (test 26 pattern)
      await page.locator('input[name="prices-0-name"]').fill('Annuelle gratuite');
      await page.locator('input[name="prices-0-prix"]').fill('0');
      // Y = 365 jours (année) — les valeurs réelles sont N, H, D, W, M, O, Y, C, S, L
      // Y = 365 days (year) — actual values are N, H, D, W, M, O, Y, C, S, L
      await page.locator('select[name="prices-0-subscription_type"]').selectOption('Y');

      console.log('✓ Free price added / Tarif gratuit ajouté');
    });

    await test.step('First save (product + price) / Premier enregistrement', async () => {
      // Enregistrer avec "Save and continue editing" pour pouvoir ajouter les champs ensuite
      // Save with "Save and continue editing" to add fields after
      // Le bouton a le name="_continue" et le form="product_form"
      // The button has name="_continue" and form="product_form"
      const saveAndContinue = page.locator('button[name="_continue"]').first();
      await saveAndContinue.click();
      await page.waitForLoadState('networkidle');

      // Vérifier qu'on est bien sur la page d'édition (pas d'erreur)
      // Check we are on the edit page (no error)
      const errorList = page.locator('.errorlist');
      const hasErrors = await errorList.count() > 0;
      if (hasErrors) {
        const errorText = await errorList.first().textContent();
        console.log(`⚠ Errors after save: ${errorText}`);
      }
      expect(hasErrors).toBeFalsy();

      console.log('✓ Product saved with price / Produit enregistré avec tarif');
    });

    await test.step('Add 6 dynamic form fields / Ajouter 6 champs dynamiques', async () => {
      // Ouvrir l'onglet "Dynamic form field"
      // Open the "Dynamic form field" tab
      const tab = page.locator('button:has-text("Dynamic form field"), a:has-text("Dynamic form field")').first();
      if (await tab.count() > 0) {
        await tab.click();
        await page.waitForTimeout(1000);
      }

      // 1. Texte court / Short text (ST)
      await addFormField(page, {
        label: 'Nom complet',
        type: 'ST',
        required: true,
        help_text: 'Votre nom et prénom',
        order: 1,
      });

      // 2. Texte long / Long text (LT)
      await addFormField(page, {
        label: 'Présentation',
        type: 'LT',
        required: false,
        help_text: 'Présentez-vous brièvement',
        order: 2,
      });

      // 3. Select simple / Single select (SS)
      await addFormField(page, {
        label: 'Ville préférée',
        type: 'SS',
        required: true,
        help_text: '',
        order: 3,
        options: 'Option A, Option B, Option C',
      });

      // 4. Radio / Single radio (SR)
      await addFormField(page, {
        label: 'Fréquence souhaitée',
        type: 'SR',
        required: true,
        help_text: '',
        order: 4,
        options: 'Radio 1, Radio 2, Radio 3',
      });

      // 5. Multi-select (MS)
      await addFormField(page, {
        label: "Centres d'intérêt",
        type: 'MS',
        required: false,
        help_text: 'Maintenez Ctrl pour sélectionner plusieurs',
        order: 5,
        options: 'Choix A, Choix B, Choix C',
      });

      // 6. Booléen / Boolean (BL)
      await addFormField(page, {
        label: 'Accepter les conditions',
        type: 'BL',
        required: true,
        help_text: "J'accepte le règlement",
        order: 6,
      });

      console.log('✓ 6 dynamic form fields added / 6 champs dynamiques ajoutés');
    });

    await test.step('Final save / Enregistrement final', async () => {
      // Toujours "Save and continue editing" pour vérifier qu'il n'y a pas d'erreur
      // Always "Save and continue editing" to check for errors
      const saveAndContinue = page.locator('button[name="_continue"]').first();
      await saveAndContinue.click();
      await page.waitForLoadState('networkidle');

      const errorList = page.locator('.errorlist');
      const hasErrors = await errorList.count() > 0;
      if (hasErrors) {
        const errorText = await errorList.first().textContent();
        console.log(`⚠ Errors after final save: ${errorText}`);
      }
      expect(hasErrors).toBeFalsy();
      console.log('✓ Product saved with fields / Produit enregistré avec champs');
    });
  });


  // ===================================================================
  // ÉTAPE 2 — Public : souscrire + paiement Stripe
  // STEP 2 — Public: subscribe + Stripe payment
  // ===================================================================

  test('Step 2: Public subscribes with dynamic form + Stripe / Étape 2 : Souscription publique', async ({ page }) => {

    await test.step('Navigate to memberships / Aller sur la page des adhésions', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('domcontentloaded');
    });

    await test.step('Open membership panel / Ouvrir le panneau d\'adhésion', async () => {
      // Trouver la carte du produit / Find the product card
      const card = page.locator('.card').filter({ hasText: PRODUCT_NAME }).first();
      await expect(card).toBeVisible({ timeout: 10000 });

      const subscribeButton = card.locator('button:has-text("Subscribe"), button:has-text("Adhérer")').first();
      await subscribeButton.click();

      // Attendre l'ouverture du panneau / Wait for panel to open
      await page.waitForSelector('#subscribePanel.show, .offcanvas.show', { state: 'visible', timeout: 10000 });
      console.log('✓ Subscribe panel opened / Panneau ouvert');
    });

    await test.step('Fill user info / Remplir les infos utilisateur', async () => {
      await page.locator('#subscribePanel input[name="email"]').fill(USER_EMAIL);
      await page.locator('#subscribePanel input[name="confirm-email"]').fill(USER_EMAIL);
      await page.locator('#subscribePanel input[name="firstname"]').fill('Douglas');
      await page.locator('#subscribePanel input[name="lastname"]').fill('Adams');
      console.log(`✓ User info filled: ${USER_EMAIL}`);
    });

    await test.step('Select price / Sélectionner le tarif', async () => {
      const priceLabel = page.locator('label:has-text("Annuelle")').first();
      await priceLabel.click();
      console.log('✓ Price selected: Annuelle');
    });

    await test.step('Fill dynamic form fields / Remplir les champs dynamiques', async () => {
      // ST — Texte court / Short text
      const shortTextInput = page.locator('input[name="form__nom-complet"]');
      await shortTextInput.fill(FORM_ANSWERS.shortText);

      // LT — Texte long / Long text
      const longTextInput = page.locator('textarea[name="form__presentation"]');
      await longTextInput.fill(FORM_ANSWERS.longText);

      // SS — Select simple / Single select
      const singleSelect = page.locator('select[name="form__ville-preferee"]');
      await singleSelect.selectOption(FORM_ANSWERS.singleSelect);

      // SR — Radio / Radio buttons
      const radioInput = page.locator(
        `input[name="form__frequence-souhaitee"][value="${FORM_ANSWERS.radioSelect}"]`
      );
      await radioInput.check();

      // MS — Multi-select (checkboxes)
      for (const choice of FORM_ANSWERS.multiSelect) {
        const checkbox = page.locator(
          `input[name="form__centres-dinteret"][value="${choice}"]`
        );
        await checkbox.check();
      }

      // BL — Booléen / Boolean
      const booleanInput = page.locator('input[name="form__accepter-les-conditions"]');
      await booleanInput.check();

      console.log('✓ All 6 dynamic fields filled / 6 champs dynamiques remplis');
    });

    await test.step('Submit and pay via Stripe / Valider et payer', async () => {
      const submitButton = page.locator('#membership-submit');
      await expect(submitButton).toBeEnabled();
      await submitButton.click();

      // Attendre la redirection Stripe / Wait for Stripe redirect
      console.log('Waiting for Stripe... / Attente Stripe...');
      await page.waitForURL(/checkout.stripe.com/, { timeout: 30000 });

      // Remplir la carte Stripe / Fill Stripe card
      await fillStripeCard(page, USER_EMAIL);
      await page.locator('button[type="submit"]').click();
    });

    await test.step('Verify success / Vérifier le succès', async () => {
      // Attendre le retour sur le site / Wait for redirect back
      await page.waitForURL(url => url.hostname.includes('tibillet.localhost'), { timeout: 30000 });

      const successMessage = page.locator('text=/merci|confirmée|succès|success/i');
      await expect(successMessage).toBeVisible({ timeout: 15000 });
      console.log('✓ Membership purchase successful / Achat adhésion réussi');
    });
  });


  // ===================================================================
  // ÉTAPE 3 — Admin : vérifier l'adhésion dans la liste
  // STEP 3 — Admin: verify membership in the list
  // ===================================================================

  test('Step 3: Admin verifies membership / Étape 3 : Admin vérifie l\'adhésion', async ({ page }) => {

    await test.step('Login as admin / Connexion admin', async () => {
      await loginAsAdmin(page);
    });

    await test.step('Check membership in list / Vérifier dans la liste des adhésions', async () => {
      await page.goto('/admin/BaseBillet/membership/');
      await page.waitForLoadState('networkidle');

      // Chercher la ligne avec l'email / Find the row with the email
      const row = page.locator(`tr:has-text("${USER_EMAIL}")`).first();
      await expect(row).toBeVisible({ timeout: 10000 });

      // Vérifier le statut validé (icône check_small)
      // Check validated status (check_small icon)
      const checkIcon = row.locator('span.material-symbols-outlined:has-text("check_small")');
      await expect(checkIcon).toBeVisible({ timeout: 5000 });
      console.log('✓ Membership validated in list / Adhésion validée dans la liste');
    });
  });


  // ===================================================================
  // ÉTAPE 4 — Admin : vérifier les réponses dans la page change
  // STEP 4 — Admin: verify answers in the change page
  // ===================================================================

  test('Step 4: Admin verifies form answers / Étape 4 : Admin vérifie les réponses', async ({ page }) => {

    await test.step('Login and navigate to membership / Connexion et navigation', async () => {
      await loginAsAdmin(page);
      await page.goto('/admin/BaseBillet/membership/');
      await page.waitForLoadState('networkidle');

      // Ouvrir la page change de l'adhésion / Open the membership change page
      const row = page.locator(`tr:has-text("${USER_EMAIL}")`).first();
      await row.locator('a').first().click();
      await page.waitForLoadState('networkidle');
    });

    await test.step('Verify form answers in table / Vérifier les réponses dans le tableau', async () => {
      // Vérifier la présence du tableau des réponses
      // Check the answers table is present
      const customFormSection = page.locator('text=/Custom form answers|Réponses.*formulaire/i');
      await expect(customFormSection).toBeVisible({ timeout: 5000 });

      // Vérifier chaque réponse / Check each answer
      await expect(page.locator(`td:has-text("${FORM_ANSWERS.shortText}")`)).toBeVisible();
      await expect(page.locator(`td:has-text("${FORM_ANSWERS.longText}")`)).toBeVisible();
      await expect(page.locator(`td:has-text("${FORM_ANSWERS.singleSelect}")`)).toBeVisible();
      await expect(page.locator(`td:has-text("${FORM_ANSWERS.radioSelect}")`)).toBeVisible();
      // Multi-select : vérifier que les choix sont présents
      // Multi-select: check choices are present
      for (const choice of FORM_ANSWERS.multiSelect) {
        await expect(page.locator(`td:has-text("${choice}")`)).toBeVisible();
      }
      console.log('✓ All form answers verified / Toutes les réponses vérifiées');
    });
  });


  // ===================================================================
  // ÉTAPE 5 — Admin : ajouter un champ libre
  // STEP 5 — Admin: add a free-form field
  // ===================================================================

  test('Step 5: Admin adds free field / Étape 5 : Admin ajoute un champ libre', async ({ page }) => {

    await test.step('Login and navigate to membership / Connexion et navigation', async () => {
      await loginAsAdmin(page);
      await page.goto('/admin/BaseBillet/membership/');
      await page.waitForLoadState('networkidle');

      const row = page.locator(`tr:has-text("${USER_EMAIL}")`).first();
      await row.locator('a').first().click();
      await page.waitForLoadState('networkidle');
    });

    await test.step('Add free field / Ajouter un champ libre', async () => {
      // Cliquer "Ajouter un champ" / Click "Add a field"
      const addFieldButton = page.locator('[data-testid="custom-form-add-field-btn"]');
      await addFieldButton.click();
      await page.waitForTimeout(1000);

      // Remplir le formulaire d'ajout / Fill the add form
      await page.locator('#new_field_label').fill('Note interne');
      await page.locator('#new_field_value').fill('Adhérent prioritaire');

      // Soumettre / Submit
      const submitButton = page.locator('[data-testid="custom-form-add-submit-btn"]');
      await submitButton.click();
      await page.waitForTimeout(1000);

      // Vérifier le message de succès / Check success message
      const successMsg = page.locator('[data-testid="custom-form-success-msg"]');
      await expect(successMsg).toBeVisible({ timeout: 5000 });

      // Vérifier que le champ est dans le tableau / Check field is in the table
      await expect(page.locator('td:has-text("Note interne")')).toBeVisible();
      await expect(page.locator('td:has-text("Adhérent prioritaire")')).toBeVisible();
      console.log('✓ Free field added / Champ libre ajouté');
    });
  });


  // ===================================================================
  // ÉTAPE 6 — Admin : modifier les réponses existantes
  // STEP 6 — Admin: edit existing answers
  // ===================================================================

  test('Step 6: Admin edits answers / Étape 6 : Admin modifie les réponses', async ({ page }) => {

    await test.step('Login and navigate to membership / Connexion et navigation', async () => {
      await loginAsAdmin(page);
      await page.goto('/admin/BaseBillet/membership/');
      await page.waitForLoadState('networkidle');

      const row = page.locator(`tr:has-text("${USER_EMAIL}")`).first();
      await row.locator('a').first().click();
      await page.waitForLoadState('networkidle');
    });

    await test.step('Edit answers / Modifier les réponses', async () => {
      // Cliquer "Modifier les réponses" / Click "Edit answers"
      const editButton = page.locator('[data-testid="custom-form-edit-btn"]');
      await editButton.click();
      await page.waitForTimeout(1000);

      // Les noms des inputs correspondent aux labels des champs (avec espaces et accents)
      // Input names match field labels (with spaces and accents)
      const nomInput = page.locator('input[name="Nom complet"]');
      await expect(nomInput).toHaveValue(FORM_ANSWERS.shortText);

      // Modifier un champ texte / Edit a text field
      await nomInput.fill('Arthur Dent');

      // Modifier un select / Edit a select
      const villeSelect = page.locator('select[name="Ville préférée"]');
      await villeSelect.selectOption('Option C');

      // Enregistrer / Save
      const saveButton = page.locator('[data-testid="custom-form-save-btn"]');
      await saveButton.click();
      await page.waitForTimeout(1000);

      // Vérifier le succès / Check success
      const successMsg = page.locator('[data-testid="custom-form-success-msg"]');
      await expect(successMsg).toBeVisible({ timeout: 5000 });

      // Vérifier les nouvelles valeurs dans le tableau / Check new values in table
      await expect(page.locator('td:has-text("Arthur Dent")')).toBeVisible();
      await expect(page.locator('td:has-text("Option C")')).toBeVisible();
      console.log('✓ Answers edited successfully / Réponses modifiées avec succès');
    });
  });


  // ===================================================================
  // ÉTAPE 7 — Admin : tester annulation
  // STEP 7 — Admin: test cancellation
  // ===================================================================

  test('Step 7: Admin tests cancel / Étape 7 : Admin teste l\'annulation', async ({ page }) => {

    await test.step('Login and navigate to membership / Connexion et navigation', async () => {
      await loginAsAdmin(page);
      await page.goto('/admin/BaseBillet/membership/');
      await page.waitForLoadState('networkidle');

      const row = page.locator(`tr:has-text("${USER_EMAIL}")`).first();
      await row.locator('a').first().click();
      await page.waitForLoadState('networkidle');
    });

    await test.step('Edit then cancel / Modifier puis annuler', async () => {
      // Cliquer "Modifier les réponses" / Click "Edit answers"
      const editButton = page.locator('[data-testid="custom-form-edit-btn"]');
      await editButton.click();
      await page.waitForTimeout(1000);

      // Modifier un champ / Edit a field
      const nomInput = page.locator('input[name="Nom complet"]');
      await nomInput.fill('Test Annulation');

      // Cliquer "Annuler" / Click "Cancel"
      const cancelButton = page.locator('[data-testid="custom-form-cancel-btn"]');
      await cancelButton.click();
      await page.waitForTimeout(1000);

      // Vérifier que la valeur est toujours "Arthur Dent" (pas modifiée)
      // Check the value is still "Arthur Dent" (not changed)
      await expect(page.locator('td:has-text("Arthur Dent")')).toBeVisible();
      console.log('✓ Cancel works: values unchanged / Annulation OK : valeurs inchangées');
    });
  });
});
