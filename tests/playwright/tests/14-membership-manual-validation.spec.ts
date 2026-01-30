import { test, expect } from '@playwright/test';
import { verifyDbData } from './utils/db';
import { loginAsAdmin } from './utils/auth';
import { env } from './utils/env';
import { fillStripeCard } from './utils/stripe';

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
    let membershipUuid = '';
    
    // Step 1: User requests membership
    await test.step('User request / Demande de l\'utilisateur', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('domcontentloaded');
      
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
              await fillStripeCard(page, userEmail);
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
      // Fetch the membership UUID from DB first
      // Recuperer l'UUID de l'adhesion en base
      const preValidation = await verifyDbData({
          type: 'membership',
          email: userEmail,
          product: 'Adhésion à validation sélective'
      });
      expect(preValidation).not.toBeNull();
      membershipUuid = preValidation?.uuid || '';
      expect(membershipUuid).toBeTruthy();

      await loginAsAdmin(page);

      // Use admin_accept endpoint (reliable for the AW -> AV transition)
      // Utiliser l'endpoint admin_accept (fiable pour passer de AW a AV)
      const cookies = await page.context().cookies();
      const csrfToken = cookies.find(cookie => cookie.name === 'csrftoken')?.value;
      expect(csrfToken).toBeTruthy();
      const acceptResponse = await page.request.post(`/memberships/${membershipUuid}/admin_accept/`, {
          headers: {
              'HX-Request': 'true',
              'X-CSRFToken': csrfToken as string,
              'Referer': `${env.BASE_URL}/admin/`,
          },
      });
      expect(acceptResponse.ok()).toBeTruthy();

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
      // Manual validation sets ADMIN_VALID (AV); payment comes later
      // La validation manuelle met le statut ADMIN_VALID (AV), le paiement vient apres
      expect(dbResult?.membership_status).toBe('AV');

      console.log('✓ DB verification successful: Membership is validated');
    });
  });

});
