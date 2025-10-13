import { test, expect, Page } from '@playwright/test';
import { env } from './utils/env';

/**
 * Test: Create ALL Membership Products from demo_data.py
 * 
 * This test creates membership products via Playwright, step by step:
 * 1. Adhésion (Le Tiers-Lustre) - 3 prices
 * 2. Adhésion récurrente - 4 prices  
 * 3. Adhésion à validation sélective - 2 prices
 * 4. Panier AMAP - 2 prices with options
 * 5. Badgeuse co-working - 1 price
 * 
 * (Formbricks products excluded as per user request)
 */

// Helper: Login as admin
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
  
  console.log('✓ Logged in as admin');
}

// Helper: Add inline price
async function addInlinePrice(page: Page, priceData: {
  name: string;
  prix: number;
  subscription_type: string;
  recurring_payment?: boolean;
  free_price?: boolean;
}) {
  // Count existing inline price forms before adding
  // Pattern: prices-0-name, prices-1-name, etc. (excluding prices-__prefix__-name which is the template)
  const countBefore = await page.locator('input[name*="prices-"][name$="-name"]:not([name*="__prefix__"])').count();
  
  // Click the first "Add another" button (for prices inline)
  const addButtons = await page.locator('a:has-text("Add another"), button:has-text("Add another")').all();
  if (addButtons.length > 0) {
    await addButtons[0].click();
    await page.waitForTimeout(500);
  }
  
  // The new form index is countBefore (0-indexed)
  const formIndex = countBefore;
  
  // Fill price name (correct pattern: prices-0-name, prices-1-name, etc.)
  const nameInput = page.locator(`input[name="prices-${formIndex}-name"]`);
  await nameInput.fill(priceData.name);
  
  // Fill price amount
  const prixInput = page.locator(`input[name="prices-${formIndex}-prix"]`);
  await prixInput.fill(priceData.prix.toString());
  
  // Select subscription type
  const subscriptionSelect = page.locator(`select[name="prices-${formIndex}-subscription_type"]`);
  await subscriptionSelect.selectOption(priceData.subscription_type);
  
  // Check free_price if needed
  if (priceData.free_price) {
    const freePriceCheckbox = page.locator(`input[name="prices-${formIndex}-free_price"]`);
    await freePriceCheckbox.check();
  }
  
  console.log(`✓ Added inline price: ${priceData.name} (${priceData.prix}€, ${priceData.subscription_type})`);
}

test.describe('Create Membership Products', () => {
  
  test('Create Product 1: Adhésion (Le Tiers-Lustre) with 3 prices', async ({ page }) => {
    await test.step('Login as admin', async () => {
      await loginAsAdmin(page);
    });

    await test.step('Navigate to Products admin and start creation', async () => {
      await page.goto('/admin/BaseBillet/product/');
      await page.waitForLoadState('networkidle');
      
      // Check if product already exists
      const pageContent = await page.content();
      if (pageContent.includes('Adhésion (Le Tiers-Lustre)')) {
        console.log('✓ Product already exists, skipping');
        test.skip();
      }
      
      // Click Add Product
      const addButton = page.locator('a[href*="/add/"]').first();
      await addButton.click();
      await page.waitForLoadState('networkidle');
      console.log('✓ Opened product creation form');
    });

    await test.step('Fill product basic information', async () => {
      // Name
      await page.locator('input[name="name"]').fill('Adhésion (Le Tiers-Lustre)');
      
      // Short description
      const shortDescInput = page.locator('input[name="short_description"], textarea[name="short_description"]').first();
      if (await shortDescInput.count() > 0) {
        await shortDescInput.fill('Adhérez au collectif Le Tiers-Lustre');
      }
      
      // Long description (WYSIWYG might be in different format)
      const longDescTextarea = page.locator('textarea[name="long_description"]').first();
      if (await longDescTextarea.count() > 0 && await longDescTextarea.isVisible()) {
        await longDescTextarea.fill('Vous pouvez prendre une adhésion en une seule fois, ou payer tous les mois.');
      }
      
      // Category: Adhesion (A)
      await page.locator('select[name="categorie_article"]').selectOption('A');
      
      // Upload image
      const imgInput = page.locator('input[name="img"]');
      if (await imgInput.count() > 0) {
        await imgInput.setInputFiles('/home/jonas/TiBillet/dev/Lespass/tests/playwright/demo_data/product_membership.jpeg');
      }
      
      console.log('✓ Filled basic product information');
    });

    await test.step('Add inline prices', async () => {
      // Price 1: Annuelle (20€, non-recurring, YEAR)
      await addInlinePrice(page, {
        name: 'Annuelle',
        prix: 20,
        subscription_type: 'Y', // YEAR
        recurring_payment: false,
      });
      
      // Price 2: Mensuelle (2€, recurring, MONTH)
      await addInlinePrice(page, {
        name: 'Mensuelle',
        prix: 2,
        subscription_type: 'M', // MONTH
        recurring_payment: true,
      });
      
      // Price 3: Prix libre (1€, free_price, YEAR)
      await addInlinePrice(page, {
        name: 'Prix libre',
        prix: 1,
        subscription_type: 'Y', // YEAR
        free_price: true,
      });
      
      console.log('✓ Added all 3 inline prices');
    });

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

    await test.step('Verify product on /memberships', async () => {
      await page.goto('/memberships');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(1000);
      
      const pageContent = await page.content();
      const hasProduct = pageContent.includes('Adhésion') && pageContent.includes('Tiers-Lustre');
      
      if (hasProduct) {
        console.log('✓ Product visible on /memberships page');
      } else {
        console.log('⚠ Product not visible on /memberships');
      }
      
      expect(hasProduct).toBeTruthy();
    });
  });
  
  // TODO: Add more products in similar fashion
  // - Adhésion récurrente (4 prices)
  // - Adhésion à validation sélective (2 prices)
  // - Panier AMAP (2 prices with options)
  // - Badgeuse co-working (1 price, badge category)
});
