import { test, expect } from '@playwright/test';
import { verifyDbData } from './utils/db';
import { loginAs } from './utils/auth';
import { fillStripeCard } from './utils/stripe';

/**
 * TEST: SSA Membership, Payment and Tokens Verification
 * TEST : Adhesion SSA, Paiement et Verification des Jetons
 *
 * Objectives:
 * 1. Purchase SSA membership (Caisse de securite sociale alimentaire).
 * 2. Login to the account.
 * 3. Verify that tokens (MonaLocalim) are present in the wallet.
 * 4. Verify the sale status in database.
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

const userEmail = `jturbeaux+ssa${generateRandomId()}@pm.me`;

test.describe('SSA Membership and Tokens / Adhesion SSA et Jetons', () => {

  test('should purchase SSA and receive tokens / doit acheter SSA et recevoir des jetons', async ({ page }) => {

    // Step 1: Purchase SSA membership
    await test.step('Purchase SSA membership / Acheter l\'adhesion SSA', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('domcontentloaded');

      // Click the SSA membership button via data-testid (hx-get + offcanvas)
      const ssaButton = page.locator('[data-testid="membership-open-959c70d2-2c14-42aa-96d9-4dd458b575f9"]');
      await ssaButton.click();

      // Wait for the offcanvas to open AND the HTMX form to load inside it
      await page.waitForSelector('#subscribePanel.show', { state: 'visible' });
      await page.waitForSelector('#membership-form', { state: 'visible', timeout: 10000 });

      // Fill info
      await page.locator('#membership-email').fill(userEmail);
      await page.locator('#confirm-email').fill(userEmail);
      await page.locator('input[name="firstname"]').fill('Douglas');
      await page.locator('input[name="lastname"]').fill('Adams');

      // Fill the free price amount (single price, already selected via hidden input)
      const amountInput = page.locator('.custom-amount-input').first();
      await amountInput.fill('10');

      // Submit
      await page.locator('#membership-submit').click();
      console.log('Waiting for Stripe redirection or confirmation message...');

      try {
          await Promise.race([
              page.waitForURL(/checkout.stripe.com/, { timeout: 30000 }),
              page.waitForSelector('text=/demande|reçue|attente|waiting|received/i', { timeout: 30000 })
          ]);

          if (page.url().includes('stripe.com')) {
              console.log('Redirected to Stripe');
              await fillStripeCard(page, userEmail);
              await page.locator('button[type="submit"]').click();
              await Promise.race([
                  page.waitForURL(url => url.hostname.includes('tibillet.localhost'), { timeout: 60000 }),
                  page.waitForSelector('text=/merci|confirmée|succès|success/i', { timeout: 60000 })
              ]);
          } else {
              console.log('Confirmation message shown instead of Stripe redirection');
          }
      } catch (e) {
          console.log('Neither Stripe nor confirmation message appeared.');
          const errorMsg = await page.locator('.alert-danger, .invalid-feedback:visible').allTextContents();
          if (errorMsg.length > 0) {
              console.log('Errors found:', errorMsg.join(' | '));
          }
          const bodyText = await page.locator('body').innerText();
          console.log('Page content (truncated):', bodyText.substring(0, 500));
          throw e;
      }

      await page.waitForURL(url => url.hostname.includes('tibillet.localhost'), { timeout: 30000 });
      console.log('SSA purchase successful');
    });

    // Step 2: Login and check Wallet
    await test.step('Login and check wallet / Se connecter et verifier la tirelire', async () => {
      await loginAs(page, userEmail);

      await page.goto('/my_account/balance/');
      await page.waitForLoadState('domcontentloaded');

      // The token table loads via HTMX with hx-trigger="revealed" (lazy load on scroll)
      // Scroll to the "Currency list" section to trigger the HTMX request
      await page.locator('#detail-monnaies').scrollIntoViewIfNeeded();

      // Wait for the token table to replace the "Loading list" spinner
      await page.locator('table tbody tr td').first().waitFor({ state: 'visible', timeout: 15000 });

      const balanceContent = await page.locator('body').innerText();
      expect(balanceContent).toContain('MonaLocalim');
      expect(balanceContent).toContain('100');

      console.log('Tokens verified in wallet UI');
    });

    // Step 3: DB Verification
    await test.step('Verify tokens and sale in DB / Verifier les jetons et la vente en DB', async () => {
      const dbResult = await verifyDbData({
          type: 'tokens',
          email: userEmail,
          product: 'Caisse de sécurité sociale alimentaire'
      });

      expect(dbResult).not.toBeNull();
      expect(dbResult?.status).toBe('success');
      expect(dbResult?.balance).toBeGreaterThan(0);
      expect(dbResult?.has_wallet).toBe(true);

      console.log(`DB verification for tokens successful (Balance: ${dbResult?.balance})`);
    });
  });

});
