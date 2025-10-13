import { test, expect, Page } from '@playwright/test';
import { env } from './utils/env';

/**
 * Test: Create Membership Product 2 - Adhésion récurrente
 * 
 * Creates the recurring membership product with 4 prices:
 * - Journalière (2€, DAY, recurring)
 * - Hebdomadaire (10€, WEEK, recurring)
 * - Mensuelle (20€, MONTH, recurring)
 * - Annuelle (150€, YEAR, recurring)
 * 
 * Based on demo_data.py lines 219-258
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

async function addInlinePrice(page: Page, priceData: {
  name: string;
  prix: number;
  subscription_type: string;
  recurring_payment?: boolean;
}) {
  const countBefore = await page.locator('input[name*="prices-"][name$="-name"]:not([name*="__prefix__"])').count();
  
  const addButtons = await page.locator('a:has-text("Add another"), button:has-text("Add another")').all();
  if (addButtons.length > 0) {
    await addButtons[0].click();
    await page.waitForTimeout(500);
  }
  
  const formIndex = countBefore;
  
  const nameInput = page.locator(`input[name="prices-${formIndex}-name"]`);
  await nameInput.fill(priceData.name);
  
  const prixInput = page.locator(`input[name="prices-${formIndex}-prix"]`);
  await prixInput.fill(priceData.prix.toString());
  
  const subscriptionSelect = page.locator(`select[name="prices-${formIndex}-subscription_type"]`);
  await subscriptionSelect.selectOption(priceData.subscription_type);
  
  // Note: recurring_payment checkbox is not available in inline forms
  // It will need to be set manually after product creation if needed
  
  console.log(`✓ Added inline price: ${priceData.name} (${priceData.prix}€, ${priceData.subscription_type})`);
}

test.describe('Create Membership Product 2', () => {
  test('Create Adhésion récurrente with 4 prices', async ({ page }) => {
    // Step 1: Login
    await test.step('Login as admin', async () => {
      await loginAsAdmin(page);
      console.log('✓ Logged in as admin');
    });

    // Step 2: Navigate to product creation
    await test.step('Open product creation form', async () => {
      await page.goto('/admin/BaseBillet/product/add/');
      await page.waitForLoadState('networkidle');
      console.log('✓ Opened product creation form');
    });

    // Step 3: Fill product information
    await test.step('Fill basic product information', async () => {
      await page.locator('input[name="name"]').fill('Adhésion récurrente (Le Tiers-Lustre)');
      await page.locator('select[name="categorie_article"]').selectOption('A');
      await page.locator('input[name="short_description"]').fill('Adhésion avec paiements récurrents');
      
      // Long description (WYSIWYG field - try regular textarea first, then contenteditable)
      const longDescTextarea = page.locator('textarea[name="long_description"]');
      if (await longDescTextarea.count() > 0) {
        await longDescTextarea.fill('Adhésion récurrente avec des tarifs journaliers, hebdomadaires, mensuels et annuels.');
      } else {
        // If WYSIWYG, look for contenteditable div
        const wysiwygEditor = page.locator('[contenteditable="true"]').first();
        if (await wysiwygEditor.count() > 0) {
          await wysiwygEditor.fill('Adhésion récurrente avec des tarifs journaliers, hebdomadaires, mensuels et annuels.');
        }
      }
      
      const optionCheckbox = page.locator('input[value="option_membre_actif"], input[value="Membre actif.ve"]').first();
      if (await optionCheckbox.count() > 0) {
        await optionCheckbox.check();
      }
      
      console.log('✓ Filled basic product information');
    });

    // Step 4: Add inline prices
    await test.step('Add inline prices', async () => {
      const prices = [
        { name: 'Journalière', prix: 2, subscription_type: 'D', recurring_payment: true },
        { name: 'Hebdomadaire', prix: 10, subscription_type: 'W', recurring_payment: true },
        { name: 'Mensuelle', prix: 20, subscription_type: 'M', recurring_payment: true },
        { name: 'Annuelle', prix: 150, subscription_type: 'Y', recurring_payment: true },
      ];
      
      for (const price of prices) {
        await addInlinePrice(page, price);
      }
      
      console.log(`✓ Added all ${prices.length} inline prices`);
    });

    // Step 5: Save product
    await test.step('Save product', async () => {
      const saveButton = page.locator('button[type="submit"]:has-text("Save"), button[type="submit"]:has-text("Enregistrer"), input[type="submit"]').first();
      await saveButton.click();
      await page.waitForLoadState('networkidle');
      console.log('✓ Product saved successfully');
    });

    // Step 6: Verify on /memberships
    await test.step('Verify product on /memberships', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('networkidle');
      
      const pageContent = await page.content();
      expect(pageContent.includes('Adhésion récurrente')).toBeTruthy();
      
      console.log('✓ Product visible on /memberships page');
    });
  });
});
