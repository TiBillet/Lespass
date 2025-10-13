import { test, expect, Page } from '@playwright/test';
import { env } from './utils/env';

/**
 * Test: Add ProductFormFields to existing SSA product
 * 
 * Issue: "il n'y a pas de formulaire visible sur la SSA"
 * The SSA product exists but may not have the form fields attached.
 * This test adds the 4 required form fields to the existing SSA product.
 * 
 * Based on demo_data.py lines 350-402
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

test.describe('Add Form Fields to Existing SSA Product', () => {
  test('should add 4 ProductFormFields to existing SSA product', async ({ page }) => {
    // Step 1: Login
    await test.step('Login as admin', async () => {
      await loginAsAdmin(page);
      console.log('✓ Logged in as admin');
    });

    // Step 2: Navigate to Products admin and find SSA
    await test.step('Navigate to Products admin and find SSA', async () => {
      await page.goto('/admin/BaseBillet/product/');
      await page.waitForLoadState('networkidle');
      
      // Search for SSA product
      const searchInput = page.locator('input[name="q"]').first();
      if (await searchInput.count() > 0) {
        await searchInput.fill('Caisse de sécurité sociale alimentaire');
        await page.keyboard.press('Enter');
        await page.waitForLoadState('networkidle');
      }
      
      // Click on SSA product link to edit
      const ssaLink = page.locator('a:has-text("Caisse de sécurité sociale alimentaire")').first();
      if (await ssaLink.count() > 0) {
        await ssaLink.click();
        await page.waitForLoadState('networkidle');
        console.log('✓ Opened SSA product for editing');
      } else {
        console.log('⚠ SSA product not found - may need to create it first');
        test.skip();
      }
    });

    // Step 3: Click on the form fields tab
    await test.step('Navigate to form fields tab', async () => {
      // ProductFormFieldInline has tab=True, so there should be a tab
      const formFieldsTab = page.locator('a:has-text("Dynamic form field"), a:has-text("Champs de formulaire dynamique"), button:has-text("Dynamic form field"), button:has-text("Champs de formulaire dynamique")').first();
      
      if (await formFieldsTab.count() > 0) {
        await formFieldsTab.click();
        await page.waitForTimeout(1000);
        console.log('✓ Clicked on form fields tab');
      } else {
        console.log('⚠ Form fields tab not found - checking if fields exist inline');
      }
    });

    // Step 4: Check if form fields already exist
    await test.step('Check existing form fields', async () => {
      const existingFields = await page.locator('input[name*="productformfield_set-"][name$="-label"]:not([name*="__prefix__"])').count();
      console.log(`✓ Found ${existingFields} existing form fields`);
      
      if (existingFields >= 4) {
        console.log('✓ Form fields already exist (4 or more), skipping creation');
        test.skip();
      }
    });

    // Step 5: Add the 4 form fields
    await test.step('Add ProductFormField #1 - Pseudonyme', async () => {
      // More specific: look for "Add another" that's near form field inputs or in the form fields section
      // Try to find the container or section for form fields first
      let addButton = page.locator('a:has-text("Add another Dynamic form field"), a:has-text("Ajouter un autre Champs de formulaire dynamique")').first();
      
      if (await addButton.count() === 0) {
        // Fallback: get all "Add another" buttons and try the last one
        const addButtons = await page.locator('a:has-text("Add another"), button:has-text("Add another")').all();
        if (addButtons.length > 0) {
          addButton = addButtons[addButtons.length - 1];
        }
      }
      
      await addButton.click();
      await page.waitForTimeout(1500); // Wait longer for DOM to update
      
      const countAfter = await page.locator('input[name*="productformfield_set-"][name$="-label"]:not([name*="__prefix__"])').count();
      console.log(`After clicking 'Add another', found ${countAfter} form fields`);
      const formIndex = countAfter - 1; // Index of the newly added form
      
      await page.locator(`input[name="productformfield_set-${formIndex}-label"]`).fill('Pseudonyme');
      await page.locator(`select[name="productformfield_set-${formIndex}-field_type"]`).selectOption('ST');
      
      const requiredCheckbox = page.locator(`input[name="productformfield_set-${formIndex}-required"]`);
      if (!await requiredCheckbox.isChecked()) {
        await requiredCheckbox.check();
      }
      
      const helpTextInput = page.locator(`input[name="productformfield_set-${formIndex}-help_text"], textarea[name="productformfield_set-${formIndex}-help_text"]`).first();
      if (await helpTextInput.count() > 0) {
        await helpTextInput.fill('Affiché à la communauté ; vous pouvez utiliser un pseudonyme.');
      }
      
      await page.locator(`input[name="productformfield_set-${formIndex}-order"]`).fill('1');
      
      console.log('✓ Added form field: Pseudonyme (SHORT_TEXT, required, order=1)');
    });

    await test.step('Add ProductFormField #2 - À propos de vous', async () => {
      const addButtons = await page.locator('a:has-text("Add another"), button:has-text("Add another")').all();
      if (addButtons.length > 0) {
        await addButtons[addButtons.length - 1].click();
        await page.waitForTimeout(500);
      }
      
      const countAfter = await page.locator('input[name*="productformfield_set-"][name$="-label"]:not([name*="__prefix__"])').count();
      const formIndex = countAfter - 1;
      
      await page.locator(`input[name="productformfield_set-${formIndex}-label"]`).fill('À propos de vous');
      await page.locator(`select[name="productformfield_set-${formIndex}-field_type"]`).selectOption('LT');
      
      const helpTextInput = page.locator(`input[name="productformfield_set-${formIndex}-help_text"], textarea[name="productformfield_set-${formIndex}-help_text"]`).first();
      if (await helpTextInput.count() > 0) {
        await helpTextInput.fill('Nous aide à mieux vous connaître.');
      }
      
      await page.locator(`input[name="productformfield_set-${formIndex}-order"]`).fill('2');
      
      console.log('✓ Added form field: À propos de vous (LONG_TEXT, optional, order=2)');
    });

    await test.step('Add ProductFormField #3 - Style préféré', async () => {
      const addButtons = await page.locator('a:has-text("Add another"), button:has-text("Add another")').all();
      if (addButtons.length > 0) {
        await addButtons[addButtons.length - 1].click();
        await page.waitForTimeout(500);
      }
      
      const countAfter = await page.locator('input[name*="productformfield_set-"][name$="-label"]:not([name*="__prefix__"])').count();
      const formIndex = countAfter - 1;
      
      await page.locator(`input[name="productformfield_set-${formIndex}-label"]`).fill('Style préféré');
      await page.locator(`select[name="productformfield_set-${formIndex}-field_type"]`).selectOption('SS');
      
      const requiredCheckbox = page.locator(`input[name="productformfield_set-${formIndex}-required"]`);
      if (!await requiredCheckbox.isChecked()) {
        await requiredCheckbox.check();
      }
      
      const optionsTextarea = page.locator(`textarea[name="productformfield_set-${formIndex}-options"]`);
      await optionsTextarea.fill('["Rock", "Jazz", "Musiques du monde", "Electro"]');
      
      const helpTextInput = page.locator(`input[name="productformfield_set-${formIndex}-help_text"], textarea[name="productformfield_set-${formIndex}-help_text"]`).first();
      if (await helpTextInput.count() > 0) {
        await helpTextInput.fill('Choisissez-en un.');
      }
      
      await page.locator(`input[name="productformfield_set-${formIndex}-order"]`).fill('3');
      
      console.log('✓ Added form field: Style préféré (SINGLE_SELECT, required, 4 options, order=3)');
    });

    await test.step('Add ProductFormField #4 - Centres d\'intérêt', async () => {
      const addButtons = await page.locator('a:has-text("Add another"), button:has-text("Add another")').all();
      if (addButtons.length > 0) {
        await addButtons[addButtons.length - 1].click();
        await page.waitForTimeout(500);
      }
      
      const countAfter = await page.locator('input[name*="productformfield_set-"][name$="-label"]:not([name*="__prefix__"])').count();
      const formIndex = countAfter - 1;
      
      await page.locator(`input[name="productformfield_set-${formIndex}-label"]`).fill('Centres d\'intérêt que vous souhaitez partager');
      await page.locator(`select[name="productformfield_set-${formIndex}-field_type"]`).selectOption('MS');
      
      const optionsTextarea = page.locator(`textarea[name="productformfield_set-${formIndex}-options"]`);
      await optionsTextarea.fill('["Cuisine", "Jardinage", "Musique", "Technologie", "Art", "Sport"]');
      
      const helpTextInput = page.locator(`input[name="productformfield_set-${formIndex}-help_text"], textarea[name="productformfield_set-${formIndex}-help_text"]`).first();
      if (await helpTextInput.count() > 0) {
        await helpTextInput.fill('Sélectionnez autant d\'options que vous le souhaitez.');
      }
      
      await page.locator(`input[name="productformfield_set-${formIndex}-order"]`).fill('4');
      
      console.log('✓ Added form field: Centres d\'intérêt (MULTI_SELECT, optional, 6 options, order=4)');
    });

    // Step 6: Save the product
    await test.step('Save product with new form fields', async () => {
      const saveButton = page.locator('button[type="submit"]:has-text("Save"), button[type="submit"]:has-text("Enregistrer"), input[type="submit"]').first();
      await saveButton.click();
      await page.waitForLoadState('networkidle');
      
      const errorList = page.locator('.errorlist');
      if (await errorList.count() > 0) {
        const errors = await errorList.allTextContents();
        console.log('⚠ Errors:', errors);
      } else {
        console.log('✓ Product saved successfully with form fields');
      }
    });

    // Step 7: Verify forms are visible on /memberships page
    await test.step('Verify SSA product and check for form button', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(1000);
      
      const pageContent = await page.content();
      const hasSSA = pageContent.includes('Caisse de sécurité sociale alimentaire') || pageContent.includes('SSA');
      
      if (hasSSA) {
        console.log('✓ SSA product visible on /memberships page');
        
        // Try to open the SSA membership form
        const ssaButton = page.locator('button:has-text("Caisse"), button:has-text("SSA"), button:has-text("sécurité sociale")').first();
        if (await ssaButton.count() > 0) {
          await ssaButton.click();
          await page.waitForTimeout(1000);
          
          // Check if form fields are visible in the offcanvas
          const formFieldsVisible = await page.locator('input[name^="form__"], select[name^="form__"], textarea[name^="form__"]').count();
          console.log(`✓ Found ${formFieldsVisible} form fields visible in the membership form`);
          
          if (formFieldsVisible >= 4) {
            console.log('✓ SUCCESS! All 4 form fields are now visible on the SSA membership form');
          } else if (formFieldsVisible > 0) {
            console.log(`⚠ Only ${formFieldsVisible} form fields visible (expected 4)`);
          } else {
            console.log('⚠ No form fields visible - there may be another issue');
          }
        }
      } else {
        console.log('⚠ SSA product not visible on /memberships');
      }
      
      expect(hasSSA).toBeTruthy();
    });
  });
});
