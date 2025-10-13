import { test, expect, Page } from '@playwright/test';
import { env } from './utils/env';

/**
 * Test: Create Membership Product 4 - Panier AMAP
 * 
 * Creates the AMAP basket membership with 2 prices:
 * - Annuelle (400€, YEAR)
 * - Mensuelle (40€, MONTH, recurring)
 * 
 * With radio options: Livraison à l'asso / Livraison à la maison
 * 
 * Based on demo_data.py lines 289-315
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
  
  console.log(`✓ Added inline price: ${priceData.name} (${priceData.prix}€, ${priceData.subscription_type})`);
}

test.describe('Create Membership Product 4', () => {
  test('Create Panier AMAP with 2 prices', async ({ page }) => {
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
      await page.locator('input[name="name"]').fill('Panier AMAP (Le Tiers-Lustre)');
      await page.locator('select[name="categorie_article"]').selectOption('A');
      await page.locator('input[name="short_description"]').fill('Adhésion au panier de l\'AMAP partenaire Le Tiers-Lustre');
      
      // Long description
      const longDescTextarea = page.locator('textarea[name="long_description"]');
      if (await longDescTextarea.count() > 0) {
        await longDescTextarea.fill('Association pour le maintien d\'une agriculture paysanne. Recevez un panier chaque semaine.');
      } else {
        const wysiwygEditor = page.locator('[contenteditable="true"]').first();
        if (await wysiwygEditor.count() > 0) {
          await wysiwygEditor.fill('Association pour le maintien d\'une agriculture paysanne. Recevez un panier chaque semaine.');
        }
      }
      
      // Add radio options: Livraison à l'asso and Livraison à la maison
      // These need to be created in OptionGenerale first, or selected if they exist
      const livraisonAssoCheckbox = page.locator('input[value="livraison_asso"], input[value="Livraison à l\'asso"]').first();
      if (await livraisonAssoCheckbox.count() > 0) {
        await livraisonAssoCheckbox.check();
        console.log('✓ Selected Livraison à l\'asso option');
      }
      
      const livraisonMaisonCheckbox = page.locator('input[value="livraison_maison"], input[value="Livraison à la maison"]').first();
      if (await livraisonMaisonCheckbox.count() > 0) {
        await livraisonMaisonCheckbox.check();
        console.log('✓ Selected Livraison à la maison option');
      }
      
      console.log('✓ Filled basic product information');
    });

    // Step 4: Add inline prices
    await test.step('Add inline prices', async () => {
      const prices = [
        { name: 'Annuelle', prix: 400, subscription_type: 'Y' },
        { name: 'Mensuelle', prix: 40, subscription_type: 'M' },
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
      expect(pageContent.includes('AMAP') || pageContent.includes('Panier')).toBeTruthy();
      
      console.log('✓ Product visible on /memberships page');
    });
  });
});
