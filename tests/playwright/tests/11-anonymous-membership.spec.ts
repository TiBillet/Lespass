import { test, expect } from '@playwright/test';
import { verifyDbData } from './utils/db';
import { fillStripeCard } from './utils/stripe';

/**
 * TEST: Anonymous Membership Purchase
 * TEST : Achat d'adhésion anonyme
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

const userEmail = `jturbeaux+adh${generateRandomId()}@pm.me`;

test.describe('Anonymous Membership / Adhésion anonyme', () => {

  test('should purchase a standard membership / doit acheter une adhésion standard', async ({ page }) => {
    
    // Step 1: Navigate to memberships / Naviguer vers les adhésions
    await test.step('Navigate to memberships / Naviguer vers les adhésions', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('domcontentloaded');
      console.log('✓ On memberships page / Sur la page des adhésions');
    });

    // Step 2: Select membership / Sélectionner l'adhésion
    await test.step('Select membership / Sélectionner l\'adhésion', async () => {
      const adhsCard = page.locator('.card:has-text("Adhésion (Le Tiers-Lustre)")').first();
      const subscribeButton = adhsCard.locator('button:has-text("Subscribe"), button:has-text("Adhérer")').first();
      await subscribeButton.click();
      await page.waitForSelector('#subscribePanel.show, .offcanvas.show', { state: 'visible' });
    });

    // Step 3: Fill email / Remplir l'email
    await test.step('Fill user information / Remplir les informations utilisateur', async () => {
      // Find the email inputs inside the offcanvas
      const emailInput = page.locator('#subscribePanel input[name="email"]').first();
      await emailInput.fill(userEmail);

      const confirmEmailInput = page.locator('#subscribePanel input[name="confirm-email"]').first();
      if (await confirmEmailInput.count() > 0) {
          await confirmEmailInput.fill(userEmail);
      }

      const firstnameInput = page.locator('#subscribePanel input[name="firstname"]').first();
      if (await firstnameInput.count() > 0) {
          await firstnameInput.fill('Douglas');
      }

      const lastnameInput = page.locator('#subscribePanel input[name="lastname"]').first();
      if (await lastnameInput.count() > 0) {
          await lastnameInput.fill('Adams');
      }

      console.log(`✓ User information filled for: ${userEmail}`);
    });

    // Step 4: Select price / Sélectionner le tarif
    await test.step('Select price / Sélectionner le tarif', async () => {
      // Look for a label containing "Annuelle"
      const annuelleLabel = page.locator('label:has-text("Annuelle")').first();
      // Click the label directly as the input might be hidden
      await annuelleLabel.click();
      console.log('✓ Annual price selected / Tarif annuel sélectionné');
    });

    // Step 5: Submit and pay / Valider et payer
    await test.step('Submit and Stripe payment / Valider et paiement Stripe', async () => {
      const submitButton = page.locator('#membership-submit');
      await expect(submitButton).toBeEnabled();
      
      await submitButton.click();

      // Wait for Stripe redirection
      console.log('Waiting for Stripe redirection... / Attente de la redirection Stripe...');
      try {
          await page.waitForURL(/checkout.stripe.com/, { timeout: 40000 });
      } catch (e) {
          console.log('⚠ Redirection to Stripe failed. Checking for error messages on page...');
          const errorMsg = await page.locator('.alert-danger, .invalid-feedback:visible').allTextContents();
          if (errorMsg.length > 0) {
              console.log('Errors found:', errorMsg.join(' | '));
          }
          const panelContent = await page.locator('#subscribePanel').innerText();
          console.log('Panel content:', panelContent);
          throw e;
      }
      
      // Fill Stripe details
      await fillStripeCard(page, userEmail);
      await page.locator('button[type="submit"]').click();
    });

    // Step 6: Verify success / Vérifier le succès
    await test.step('Verify success / Vérifier le succès', async () => {
      await page.waitForURL(url => url.hostname.includes('tibillet.localhost'), { timeout: 30000 });
      
      const successMessage = page.locator('text=/merci|confirmée|succès|success/i');
      await expect(successMessage).toBeVisible({ timeout: 15000 });
      console.log('✓ Membership purchase successful / Achat d\'adhésion réussi');
    });

    // Step 7: DB Verification / Vérification DB
    await test.step('Verify membership in database / Vérifier l\'adhésion en base de données', async () => {
        const dbResult = await verifyDbData({
            type: 'membership',
            email: userEmail,
            product: 'Adhésion (Le Tiers-Lustre)'
        });
        expect(dbResult).not.toBeNull();
        expect(dbResult?.status).toBe('success');
        expect(dbResult?.valid).toBe(true);
        console.log(`✓ Membership found and valid for ${userEmail}`);
    });
  });

});
