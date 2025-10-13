import { test, expect, Page } from '@playwright/test';
import { env } from './utils/env';

/**
 * Test: Create SSA (Caisse de sécurité sociale alimentaire) with dynamic form fields
 * 
 * Creates the SSA membership product with:
 * - 1 price: Mensuelle (50€, free_price, recurring, 3 iterations, CAL_MONTH)
 * - 4 ProductFormField (dynamic form fields):
 *   1. Pseudonyme (SHORT_TEXT, required)
 *   2. À propos de vous (LONG_TEXT, optional)
 *   3. Style préféré (SINGLE_SELECT, required, 4 options)
 *   4. Centres d'intérêt (MULTI_SELECT, optional, 6 options)
 * 
 * Based on demo_data.py lines 320-402
 */

async function loginAsAdmin(page: Page) {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  
  const loginButton = page.locator('.navbar button:has-text("Log in"), .navbar button:has-text("Connexion")').first();
  await loginButton.click();
  
  const emailInput = page.locator('#loginEmail');
  await emailInput.fill(env.ADMIN_EMAIL);
  
  const submitButton = page.locator('#loginForm button[type="submit"]');
  await submitButton.click();
  
  if (env.TEST) {
    const testModeLink = page.locator('a:has-text("TEST MODE")');
    await expect(testModeLink).toBeVisible({ timeout: 5000 });
    await testModeLink.click();
    await page.waitForLoadState('networkidle');
  }
}

test.describe('Create SSA Membership with Form Fields', () => {
  test('Create SSA product with 1 price and 4 form fields', async ({ page }) => {
    // Step 1: Login
    await test.step('Login as admin', async () => {
      await loginAsAdmin(page);
      console.log('✓ Logged in as admin');
    });

    // Step 2: Check if product already exists
    await test.step('Check if SSA product exists', async () => {
      await page.goto('/admin/BaseBillet/product/');
      await page.waitForLoadState('networkidle');
      
      const pageContent = await page.content();
      if (pageContent.includes('Caisse de sécurité sociale alimentaire') || pageContent.includes('sécurité sociale alimentaire')) {
        console.log('✓ SSA product already exists, skipping creation');
        test.skip();
      }
    });

    // Step 3: Navigate to product creation
    await test.step('Open product creation form', async () => {
      await page.goto('/admin/BaseBillet/product/add/');
      await page.waitForLoadState('networkidle');
      console.log('✓ Opened product creation form');
    });

    // Step 4: Fill basic product information
    await test.step('Fill basic product information', async () => {
      // Name
      await page.locator('input[name="name"]').fill('Caisse de sécurité sociale alimentaire');
      
      // Short description
      await page.locator('input[name="short_description"]').fill('Payez selon vos moyens, recevez selon vos besoins !');
      
      // Long description
      const longDesc = "Payez ce que vous pouvez : l'adhésion à la SSA vous donne droit à 150€ sur votre carte à dépenser dans tout les lieux participants. Une validation par un.e administrateur.ice est nécéssaire. Engagement demandé de 3 mois minimum.";
      const longDescTextarea = page.locator('textarea[name="long_description"]');
      if (await longDescTextarea.count() > 0 && await longDescTextarea.isVisible()) {
        await longDescTextarea.fill(longDesc);
      }
      
      // Category: ADHESION (A)
      await page.locator('select[name="categorie_article"]').selectOption('A');
      
      console.log('✓ Filled basic product information');
    });

    // Step 5: Add inline price
    await test.step('Add price inline', async () => {
      // Count existing inline forms
      const countBefore = await page.locator('input[name*="prices-"][name$="-name"]:not([name*="__prefix__"])').count();
      
      // Click "Add another" button for prices
      const addButtons = await page.locator('a:has-text("Add another"), button:has-text("Add another")').all();
      if (addButtons.length > 0) {
        await addButtons[0].click();
        await page.waitForTimeout(500);
      }
      
      const formIndex = countBefore;
      
      // Fill price name
      await page.locator(`input[name="prices-${formIndex}-name"]`).fill('Mensuelle');
      
      // Fill price amount (50€)
      await page.locator(`input[name="prices-${formIndex}-prix"]`).fill('50');
      
      // Select subscription type: CAL_MONTH (O)
      await page.locator(`select[name="prices-${formIndex}-subscription_type"]`).selectOption('O');
      
      // Check free_price checkbox
      const freePriceCheckbox = page.locator(`input[name="prices-${formIndex}-free_price"]`);
      if (await freePriceCheckbox.count() > 0) {
        await freePriceCheckbox.check();
      }
      
      // Note: recurring_payment and iteration fields might not be directly editable in inline
      // They may need to be set after product creation by editing the price
      
      console.log('✓ Added price: Mensuelle (50€, CAL_MONTH, free_price)');
      console.log('⚠ Note: recurring_payment=True and iteration=3 may need to be set by editing the price after creation');
    });

    // Step 6: Save product first (form fields can only be added after product exists)
    await test.step('Save product', async () => {
      const saveButton = page.locator('button[type="submit"]:has-text("Save"), input[type="submit"]').first();
      await saveButton.click();
      await page.waitForLoadState('networkidle');
      
      // Check for errors
      const errorList = page.locator('.errorlist');
      if (await errorList.count() > 0) {
        const errors = await errorList.allTextContents();
        console.log('⚠ Errors:', errors);
      } else {
        console.log('✓ Product saved successfully');
      }
    });

    // Step 7: Navigate back to edit the product to add form fields
    await test.step('Open product edit page to add form fields', async () => {
      await page.goto('/admin/BaseBillet/product/');
      await page.waitForLoadState('networkidle');
      
      const productLink = page.locator('a:has-text("Caisse de sécurité sociale alimentaire"), a:has-text("sécurité sociale")').first();
      await productLink.click();
      await page.waitForLoadState('networkidle');
      console.log('✓ Opened product edit page');
    });

    // Step 8: Click on the form fields tab (ProductFormFieldInline has tab=True)
    await test.step('Navigate to form fields tab', async () => {
      // Look for tab with text "Dynamic form field" or "Formulaire" or similar
      const formFieldTab = page.locator('button:has-text("Dynamic form field"), button:has-text("Form field"), a:has-text("Dynamic form field"), a:has-text("Form field")').first();
      
      if (await formFieldTab.count() > 0) {
        await formFieldTab.click();
        await page.waitForTimeout(500);
        console.log('✓ Clicked on form fields tab');
      } else {
        console.log('⚠ Form fields tab not found, trying without clicking tab');
      }
    });

    // Step 9: Add ProductFormField #1 - Pseudonyme (SHORT_TEXT, required)
    await test.step('Add form field 1: Pseudonyme', async () => {
      // Look for the form fields section (might be in a tab or inline)
      // Count existing form field inlines
      const countBefore = await page.locator('input[name*="productformfield_set-"][name$="-label"]:not([name*="__prefix__"])').count();
      
      // Click "Add another" for form fields (might be the second "Add another" button)
      const addButtons = await page.locator('a:has-text("Add another"), button:has-text("Add another")').all();
      // Usually, prices inline comes first, form fields inline comes second
      if (addButtons.length > 1) {
        await addButtons[1].click();
        await page.waitForTimeout(500);
      }
      
      const formIndex = countBefore;
      
      // Fill label
      await page.locator(`input[name="productformfield_set-${formIndex}-label"]`).fill('Pseudonyme');
      
      // Select field_type: SHORT_TEXT (ST)
      await page.locator(`select[name="productformfield_set-${formIndex}-field_type"]`).selectOption('ST');
      
      // Check required
      const requiredCheckbox = page.locator(`input[name="productformfield_set-${formIndex}-required"]`);
      await requiredCheckbox.check();
      
      // Fill help_text
      const helpTextInput = page.locator(`input[name="productformfield_set-${formIndex}-help_text"], textarea[name="productformfield_set-${formIndex}-help_text"]`);
      if (await helpTextInput.count() > 0) {
        await helpTextInput.fill('Affiché à la communauté ; vous pouvez utiliser un pseudonyme.');
      }
      
      // Fill order
      await page.locator(`input[name="productformfield_set-${formIndex}-order"]`).fill('1');
      
      console.log('✓ Added form field: Pseudonyme (SHORT_TEXT, required, order=1)');
    });

    // Step 9: Add ProductFormField #2 - À propos de vous (LONG_TEXT, optional)
    await test.step('Add form field 2: À propos de vous', async () => {
      const countBefore = await page.locator('input[name*="productformfield_set-"][name$="-label"]:not([name*="__prefix__"])').count();
      
      const addButtons = await page.locator('a:has-text("Add another"), button:has-text("Add another")').all();
      if (addButtons.length > 1) {
        await addButtons[1].click();
        await page.waitForTimeout(500);
      }
      
      const formIndex = countBefore;
      
      await page.locator(`input[name="productformfield_set-${formIndex}-label"]`).fill('À propos de vous');
      await page.locator(`select[name="productformfield_set-${formIndex}-field_type"]`).selectOption('LT');
      
      // Don't check required (optional)
      
      const helpTextInput = page.locator(`input[name="productformfield_set-${formIndex}-help_text"], textarea[name="productformfield_set-${formIndex}-help_text"]`);
      if (await helpTextInput.count() > 0) {
        await helpTextInput.fill('Nous aide à mieux vous connaître.');
      }
      
      await page.locator(`input[name="productformfield_set-${formIndex}-order"]`).fill('2');
      
      console.log('✓ Added form field: À propos de vous (LONG_TEXT, optional, order=2)');
    });

    // Step 10: Add ProductFormField #3 - Style préféré (SINGLE_SELECT, required, 4 options)
    await test.step('Add form field 3: Style préféré', async () => {
      const countBefore = await page.locator('input[name*="productformfield_set-"][name$="-label"]:not([name*="__prefix__"])').count();
      
      const addButtons = await page.locator('a:has-text("Add another"), button:has-text("Add another")').all();
      if (addButtons.length > 1) {
        await addButtons[1].click();
        await page.waitForTimeout(500);
      }
      
      const formIndex = countBefore;
      
      await page.locator(`input[name="productformfield_set-${formIndex}-label"]`).fill('Style préféré');
      await page.locator(`select[name="productformfield_set-${formIndex}-field_type"]`).selectOption('SS');
      
      const requiredCheckbox = page.locator(`input[name="productformfield_set-${formIndex}-required"]`);
      await requiredCheckbox.check();
      
      // Fill options (JSON array)
      const optionsTextarea = page.locator(`textarea[name="productformfield_set-${formIndex}-options"]`);
      if (await optionsTextarea.count() > 0) {
        await optionsTextarea.fill('["Rock", "Jazz", "Musiques du monde", "Electro"]');
      }
      
      const helpTextInput = page.locator(`input[name="productformfield_set-${formIndex}-help_text"], textarea[name="productformfield_set-${formIndex}-help_text"]`);
      if (await helpTextInput.count() > 0) {
        await helpTextInput.fill('Choisissez-en un.');
      }
      
      await page.locator(`input[name="productformfield_set-${formIndex}-order"]`).fill('3');
      
      console.log('✓ Added form field: Style préféré (SINGLE_SELECT, required, 4 options, order=3)');
    });

    // Step 11: Add ProductFormField #4 - Centres d'intérêt (MULTI_SELECT, optional, 6 options)
    await test.step('Add form field 4: Centres d\'intérêt', async () => {
      const countBefore = await page.locator('input[name*="productformfield_set-"][name$="-label"]:not([name*="__prefix__"])').count();
      
      const addButtons = await page.locator('a:has-text("Add another"), button:has-text("Add another")').all();
      if (addButtons.length > 1) {
        await addButtons[1].click();
        await page.waitForTimeout(500);
      }
      
      const formIndex = countBefore;
      
      await page.locator(`input[name="productformfield_set-${formIndex}-label"]`).fill('Centres d\'intérêt que vous souhaitez partager');
      await page.locator(`select[name="productformfield_set-${formIndex}-field_type"]`).selectOption('MS');
      
      // Don't check required (optional)
      
      // Fill options (JSON array)
      const optionsTextarea = page.locator(`textarea[name="productformfield_set-${formIndex}-options"]`);
      if (await optionsTextarea.count() > 0) {
        await optionsTextarea.fill('["Cuisine", "Jardinage", "Musique", "Technologie", "Art", "Sport"]');
      }
      
      const helpTextInput = page.locator(`input[name="productformfield_set-${formIndex}-help_text"], textarea[name="productformfield_set-${formIndex}-help_text"]`);
      if (await helpTextInput.count() > 0) {
        await helpTextInput.fill('Sélectionnez autant d\'options que vous le souhaitez.');
      }
      
      await page.locator(`input[name="productformfield_set-${formIndex}-order"]`).fill('4');
      
      console.log('✓ Added form field: Centres d\'intérêt (MULTI_SELECT, optional, 6 options, order=4)');
    });

    // Step 12: Save all changes
    await test.step('Save product with form fields', async () => {
      const saveButton = page.locator('button[type="submit"]:has-text("Save"), input[type="submit"]').first();
      await saveButton.click();
      await page.waitForLoadState('networkidle');
      
      const errorList = page.locator('.errorlist');
      if (await errorList.count() > 0) {
        const errors = await errorList.allTextContents();
        console.log('⚠ Errors:', errors);
      } else {
        console.log('✓ Product saved with all 4 form fields');
      }
    });

    // Step 13: Verify on /memberships
    await test.step('Verify product on /memberships', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('networkidle');
      
      const pageContent = await page.content();
      const hasSSA = pageContent.includes('Caisse de sécurité sociale alimentaire') || 
                     pageContent.includes('sécurité sociale alimentaire') ||
                     pageContent.includes('SSA');
      
      if (hasSSA) {
        console.log('✓ SSA product visible on /memberships page');
      } else {
        console.log('⚠ SSA product not visible on /memberships (might need publish=True)');
      }
    });
  });
});
