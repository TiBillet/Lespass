import { test, expect } from '@playwright/test';
import { verifyDbData } from './utils/db';

/**
 * TEST: Membership with Free Price
 * TEST : Adhésion à prix libre
 * 
 * Objectives:
 * 1. Purchase a membership at a custom price (Free Price).
 * 2. Verify that the price on Stripe matches the custom price.
 * 3. Verify in database.
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

const userEmail = `jturbeaux+free${generateRandomId()}@pm.me`;
const customPrice = "15"; // 15€

test.describe('Membership Free Price / Adhésion prix libre', () => {

  test('should purchase membership at free price / doit acheter une adhésion à prix libre', async ({ page }) => {
    
    // Step 1: Navigate to memberships
    await page.goto('/memberships/');
    await page.waitForLoadState('networkidle');
    
    // Step 2: Open subscription panel
    const card = page.locator('.card:has-text("Adhésion (Le Tiers-Lustre)")').first();
    await card.locator('button:has-text("Subscribe"), button:has-text("Adhérer")').click();
    await page.waitForSelector('#subscribePanel.show', { state: 'visible' });

    // Step 3: Fill info
    await page.locator('#subscribePanel input[name="email"]').fill(userEmail);
    await page.locator('#subscribePanel input[name="confirm-email"]').fill(userEmail);
    await page.locator('#subscribePanel input[name="firstname"]').fill('Free');
    await page.locator('#subscribePanel input[name="lastname"]').fill('PriceUser');

    // Step 4: Select "Prix Libre" and fill amount
    const priceLabel = page.locator('label:has-text("Prix Libre")').first();
    await priceLabel.click();
    
    const freePriceInput = page.locator('input[name="custom_amount"], input[name^="custom_amount_"], input[name="free_price_amount"], input[id*="custom_amount"]');
    if (await freePriceInput.isVisible()) {
        await freePriceInput.fill(customPrice);
    } else {
        // Search by type or class if name/id not found, but avoiding anti-spam
        await page.locator('input[type="number"]:not(#answer)').fill(customPrice);
    }
    console.log(`✓ Custom price filled: ${customPrice}€`);

    // Step 5: Submit and check Stripe
    await page.locator('#membership-submit').click();
    await page.waitForURL(/checkout.stripe.com/, { timeout: 40000 });
    
    // Check if Stripe shows the correct amount
    // On Stripe Checkout, the amount is usually visible. 
    // We search for the price text (e.g., "15,00")
    await page.waitForLoadState('networkidle');
    const stripeContent = await page.locator('body').innerText();
    const priceRegex = new RegExp(`${customPrice}[.,]00`);
    expect(stripeContent).toMatch(priceRegex);
    console.log(`✓ Stripe shows the correct custom price: ${customPrice}€`);

    // Complete payment
    await page.locator('input#cardNumber').waitFor({ state: 'visible', timeout: 20000 });
    await page.locator('input#cardNumber').fill('4242424242424242');
    await page.locator('input#cardExpiry').fill('12/42');
    await page.locator('input#cardCvc').fill('424');
    await page.locator('button[type="submit"]').click();

    await page.waitForURL(url => url.hostname.includes('tibillet.localhost') || url.hostname.includes('lespass.tibillet.localhost'), { timeout: 60000 });
    console.log('✓ Free price purchase successful / Achat à prix libre réussi');

    // Step 6: DB Verification
    await test.step('Verify free price membership in DB / Vérifier l\'adhésion prix libre en DB', async () => {
      const dbResult = await verifyDbData({
          type: 'membership',
          email: userEmail,
          product: 'Adhésion (Le Tiers-Lustre)'
      });
      
      expect(dbResult).not.toBeNull();
      expect(dbResult?.status).toBe('success');
      expect(dbResult?.valid).toBe(true);
    });
  });

});
