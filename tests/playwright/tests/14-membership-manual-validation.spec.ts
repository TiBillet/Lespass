import { test, expect } from '@playwright/test';
import { verifyDbData } from './utils/db';
import { loginAsAdmin } from './utils/auth';

/**
 * TEST: Membership Manual Validation by Admin
 * TEST : Validation Manuelle d'Adhésion par l'Admin
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

const userEmail = `jturbeaux+val${generateRandomId()}@pm.me`;

test.describe('Membership Manual Validation / Validation manuelle d\'adhésion', () => {

  test('should request and approve membership / doit demander et approuver l\'adhésion', async ({ page }) => {
    
    // Step 1: User requests membership
    await test.step('User request / Demande de l\'utilisateur', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('networkidle');
      
      const card = page.locator('.card:has-text("Adhésion à validation sélective")').first();
      await card.locator('button:has-text("Subscribe"), button:has-text("Adhérer")').click();
      await page.waitForSelector('#subscribePanel.show', { state: 'visible' });

      await page.locator('#subscribePanel input[name="email"]').fill(userEmail);
      await page.locator('#subscribePanel input[name="confirm-email"]').fill(userEmail);
      await page.locator('#subscribePanel input[name="firstname"]').fill('Candidate');
      await page.locator('#subscribePanel input[name="lastname"]').fill('User');

      // Select "Solidaire" price (which is manually validated)
      const priceLabel = page.locator('label:has-text("Solidaire")').first();
      await priceLabel.click();

      // Submit
      await page.locator('#membership-submit').click();
      
      // Since manual validation might be optional or based on specific price logic,
      // it might redirect to Stripe even if manual_validation is true (to pay first)
      // or show a message.
      console.log('Waiting for Stripe redirection or confirmation message...');
      await Promise.race([
          page.waitForURL(/checkout.stripe.com/, { timeout: 20000 }).then(() => 'stripe'),
          page.locator('text=/demande|reçue|attente|waiting|received/i').waitFor({ state: 'visible', timeout: 20000 }).then(() => 'message')
      ]).then(async (result) => {
          if (result === 'stripe') {
              console.log('Redirected to Stripe');
              await page.locator('input#cardNumber').waitFor({ state: 'visible' });
              await page.locator('input#cardNumber').fill('4242424242424242');
              await page.locator('input#cardExpiry').fill('12/42');
              await page.locator('input#cardCvc').fill('424');
              await page.locator('button[type="submit"]').click();
              await page.waitForURL(url => url.hostname.includes('tibillet.localhost'), { timeout: 30000 });
          } else {
              console.log('Message shown');
          }
      }).catch(e => {
          console.log('⚠ Neither Stripe nor message appeared. Form might have errors.');
      });
    });

    // Step 2: Admin validates in admin panel
    await test.step('Admin validation / Validation par l\'admin', async () => {
      await loginAsAdmin(page);
      
      // Navigate to membership validation list or use search in admin
      await page.goto('/admin/BaseBillet/membership/');
      await page.waitForLoadState('networkidle');
      
      // Search for the user email
      const searchInput = page.locator('#searchbar, input[name="q"]');
      if (await searchInput.isVisible()) {
          await searchInput.fill(userEmail);
          await page.keyboard.press('Enter');
      }

      // Click on the membership
      await page.waitForLoadState('networkidle');
      const userLink = page.locator('#result_list a, .result-list a').filter({ hasText: userEmail }).first();
      await userLink.click();
      
      // Check the "Valid" checkbox
      const validCheckbox = page.locator('input[name="valid"], input[name="validated"], input[id*="id_valid"]');
      if (await validCheckbox.count() > 0 && !(await validCheckbox.isChecked())) {
          await validCheckbox.check();
      }

      // Save
      await page.locator('button[type="submit"][name="_save"], input[type="submit"][name="_save"], button:has-text("Save")').first().click();
      console.log('✓ Membership approved by admin / Adhésion approuvée par l\'admin');
    });

    // Step 3: DB Verification
    await test.step('Verify validated membership in DB / Vérifier l\'adhésion validée en DB', async () => {
      const dbResult = await verifyDbData({
          type: 'membership',
          email: userEmail,
          product: 'Adhésion à validation sélective'
      });
      
      expect(dbResult).not.toBeNull();
      expect(dbResult?.status).toBe('success');
      // We check for the 'valid' boolean field which we just set in admin
      expect(dbResult?.valid).toBe(true);

      console.log('✓ DB verification successful: Membership is validated');
    });
  });

});
