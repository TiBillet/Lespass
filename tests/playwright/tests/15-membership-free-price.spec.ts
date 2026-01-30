import { test, expect } from '@playwright/test';
import { verifyDbData } from './utils/db';
import { env } from './utils/env';
import { fillStripeCard } from './utils/stripe';

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
    test.setTimeout(120000);
    const productName = `Adhésion prix libre ${generateRandomId()}`;

    await test.step('Create free price membership via API / Créer adhésion prix libre via API', async () => {
      const productResponse = await page.request.post(`${env.BASE_URL}/api/v2/products/`, {
        headers: {
          Authorization: `Api-Key ${env.API_KEY}`,
          'Content-Type': 'application/json',
        },
        data: {
          '@context': 'https://schema.org',
          '@type': 'Product',
          name: productName,
          category: 'Subscription or membership',
          description: 'Adhésion prix libre créée pour le test E2E.',
          offers: [
            {
              '@type': 'Offer',
              name: 'Prix Libre',
              price: '5.00',
              priceCurrency: 'EUR',
              freePrice: true,
            },
          ],
        },
      });

      expect(productResponse.ok()).toBeTruthy();
    });

    // Step 1: Navigate to memberships
    await page.goto('/memberships/');
    await page.waitForLoadState('domcontentloaded');
    
    // Step 2: Open subscription panel
    const card = page.locator(`.card:has-text("${productName}")`).first();
    await card.locator('button:has-text("Subscribe"), button:has-text("Adhérer")').click();
    await page.waitForSelector('#subscribePanel.show', { state: 'visible' });

    // Step 3: Fill info
    await page.locator('#subscribePanel input[name="email"]').fill(userEmail);
    await page.locator('#subscribePanel input[name="confirm-email"]').fill(userEmail);
    await page.locator('#subscribePanel input[name="firstname"]').fill('Free');
    await page.locator('#subscribePanel input[name="lastname"]').fill('PriceUser');

    // Step 4: Select "Prix Libre" and fill amount
    const priceLabel = page.locator('label:has-text("Prix Libre")').first();
    if (await priceLabel.isVisible()) {
      await priceLabel.click();
    }
    
    const freePriceInput = page.locator('#subscribePanel .custom-amount-input').first();
    if (await freePriceInput.isVisible()) {
      await freePriceInput.fill(customPrice);
    } else {
      // Search by type if class not found
      await page.locator('#subscribePanel input[type="number"]').first().fill(customPrice);
    }
    console.log(`✓ Custom price filled: ${customPrice}€`);

    // Step 5: Submit and check Stripe
    await page.locator('#membership-submit').click();
    console.log('Waiting for Stripe redirection... / Attente de la redirection Stripe...');
    try {
      await page.waitForURL(/checkout.stripe.com/, { timeout: 40000 });
    } catch (e) {
      const errorMsg = await page.locator('.alert-danger, .invalid-feedback:visible').allTextContents();
      if (errorMsg.length > 0) {
        console.log('Errors found:', errorMsg.join(' | '));
      }
      const panelContent = await page.locator('#subscribePanel').innerText();
      console.log('Panel content:', panelContent);
      throw e;
    }
    
    console.log('✓ Redirected to Stripe / Redirection Stripe OK');
    // Check if Stripe shows the correct amount
    // On Stripe Checkout, the amount is usually visible. 
    // We search for the price text (e.g., "15,00")
    await page.waitForSelector('text=/Card information|Informations de carte/i', { timeout: 20000 });
    const stripeContent = await page.locator('body').innerText();
    const priceRegex = new RegExp(`${customPrice}[.,]00`);
    expect(stripeContent).toMatch(priceRegex);
    console.log(`✓ Stripe shows the correct custom price: ${customPrice}€`);

    // Complete payment
    await fillStripeCard(page, userEmail);
    console.log('✓ Stripe form filled / Formulaire Stripe rempli');
    const stripeSubmit = page.locator('button[type="submit"]').first();
    await expect(stripeSubmit).toBeEnabled({ timeout: 20000 });
    await stripeSubmit.click();
    console.log('Waiting for return... / Attente du retour...');

    await page.waitForURL(url => url.hostname.includes('tibillet.localhost') || url.hostname.includes('lespass.tibillet.localhost'), { timeout: 60000 });
    console.log('✓ Free price purchase successful / Achat à prix libre réussi');

    // Step 6: DB Verification
    await test.step('Verify free price membership in DB / Vérifier l\'adhésion prix libre en DB', async () => {
      const dbResult = await verifyDbData({
          type: 'membership',
          email: userEmail,
          product: productName
      });
      
      expect(dbResult).not.toBeNull();
      expect(dbResult?.status).toBe('success');
      expect(dbResult?.membership_status).toBeTruthy();
    });
  });

});
