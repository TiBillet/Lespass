import { test, expect } from '@playwright/test';
import { verifyDbData } from './utils/db';
import { loginAs } from './utils/auth';
import { fillStripeCard } from './utils/stripe';

/**
 * TEST: SSA Membership, Payment and Tokens Verification
 * TEST : Adhésion SSA, Paiement et Vérification des Jetons
 * 
 * Objectives:
 * 1. Purchase SSA membership (Caisse de sécurité sociale alimentaire).
 * 2. Login to the account.
 * 3. Verify that tokens (MonaLocalim) are present in the wallet.
 * 4. Verify the sale status in database.
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

const userEmail = `jturbeaux+ssa${generateRandomId()}@pm.me`;

test.describe('SSA Membership and Tokens / Adhésion SSA et Jetons', () => {

  test('should purchase SSA and receive tokens / doit acheter SSA et recevoir des jetons', async ({ page }) => {
    
    // Step 1: Purchase SSA membership
    await test.step('Purchase SSA membership / Acheter l\'adhésion SSA', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('domcontentloaded');
      
      const ssaCard = page.locator('.card:has-text("Caisse de sécurité sociale alimentaire")').first();
      await ssaCard.locator('button:has-text("Subscribe"), button:has-text("Adhérer")').click();
      await page.waitForSelector('#subscribePanel.show', { state: 'visible' });

      // Fill info
      await page.locator('#subscribePanel input[name="email"]').fill(userEmail);
      await page.locator('#subscribePanel input[name="confirm-email"]').fill(userEmail);
      await page.locator('#subscribePanel input[name="firstname"]').fill('Douglas');
      await page.locator('#subscribePanel input[name="lastname"]').fill('Adams');

      // Fill dynamic form field (Pseudonyme)
      const pseudoInput = page.locator('#subscribePanel input[name="form__pseudonyme"]');
      if (await pseudoInput.isVisible()) {
          await pseudoInput.fill('DougSSA');
      }

      // Select Price (1.00€)
      const priceLabel = page.locator('label:has-text("Souscription mensuelle")').first();
      await priceLabel.click();
      
      // Fill amount for free/recurring price if needed
      // Remplir le montant du tarif libre/récurrent si besoin
      const amountInput = page.locator('#subscribePanel .custom-amount-input').first();
      if (await amountInput.isVisible()) {
          await amountInput.fill('10');
          await amountInput.evaluate(el => el.dispatchEvent(new Event('input', { bubbles: true })));
          await amountInput.evaluate(el => el.dispatchEvent(new Event('change', { bubbles: true })));
      }

      // Submit and Pay
      // Since it's a recurring payment, redirection might be different or deferred
      // We also check for validation message in case manual validation was turned on
      await page.locator('#membership-submit').click();
      console.log('Waiting for Stripe redirection or confirmation message... / Attente de la redirection Stripe ou du message de confirmation...');
      
      try {
          // If recurring payment works like standard, it redirects to Stripe
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
          console.log('⚠ Neither Stripe nor confirmation message appeared.');
          const errorMsg = await page.locator('.alert-danger, .invalid-feedback:visible').allTextContents();
          if (errorMsg.length > 0) {
              console.log('Errors found:', errorMsg.join(' | '));
          }
          const panelContent = await page.locator('#subscribePanel').innerText();
          console.log('Panel content:', panelContent);
          throw e;
      }

      await page.waitForURL(url => url.hostname.includes('tibillet.localhost'), { timeout: 30000 });
      console.log('✓ SSA purchase successful / Achat SSA réussi');
    });

    // Step 2: Login and check Wallet
    await test.step('Login and check wallet / Se connecter et vérifier la tirelire', async () => {
      await loginAs(page, userEmail);
      
      await page.goto('/my_account/balance/');
      await page.waitForLoadState('networkidle');

      // Look for MonaLocalim or the reward amount (100)
      // On cherche MonaLocalim ou le montant de la récompense (100)
      const balanceContent = await page.locator('body').innerText();
      expect(balanceContent).toContain('MonaLocalim');
      expect(balanceContent).toContain('100');
      
      console.log('✓ Tokens verified in wallet UI / Jetons vérifiés dans l\'interface');
    });

    // Step 3: DB Verification
    await test.step('Verify tokens and sale in DB / Vérifier les jetons et la vente en DB', async () => {
      const dbResult = await verifyDbData({
          type: 'tokens',
          email: userEmail,
          product: 'Caisse de sécurité sociale alimentaire'
      });
      
      expect(dbResult).not.toBeNull();
      expect(dbResult?.status).toBe('success');
      expect(dbResult?.balance).toBeGreaterThan(0);
      expect(dbResult?.has_wallet).toBe(true);
      
      console.log(`✓ DB verification for tokens successful (Balance: ${dbResult?.balance}) / Vérification DB des jetons réussie`);
    });
  });

});
