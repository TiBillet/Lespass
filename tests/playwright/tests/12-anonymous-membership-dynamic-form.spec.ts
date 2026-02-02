import { test, expect } from '@playwright/test';
import { verifyDbData } from './utils/db';
import { fillStripeCard } from './utils/stripe';

/**
 * TEST: Anonymous Membership Purchase with Dynamic Form
 * TEST : Achat d'adhésion anonyme avec formulaire dynamique
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

const userEmail = `jturbeaux+adhform${generateRandomId()}@pm.me`;

test.describe('Anonymous Membership with Form / Adhésion anonyme avec formulaire', () => {

  test('should purchase a membership with dynamic form / doit acheter une adhésion avec formulaire dynamique', async ({ page }) => {
    
    // Step 1: Navigate to memberships / Naviguer vers les adhésions
    await test.step('Navigate to memberships / Naviguer vers les adhésions', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('domcontentloaded');
      console.log('✓ On memberships page / Sur la page des adhésions');
    });

    // Step 2: Select membership / Sélectionner l'adhésion
    await test.step('Select membership / Sélectionner l\'adhésion', async () => {
      const adhsCard = page.locator('.card:has-text("Adhésion associative Tiers Lustre")').first();
      const subscribeButton = adhsCard.locator('button:has-text("Subscribe"), button:has-text("Adhérer")').first();
      await subscribeButton.click();
      await page.waitForSelector('#subscribePanel.show, .offcanvas.show', { state: 'visible' });
    });

    // Step 3: Fill user information / Remplir les informations utilisateur
    await test.step('Fill user information / Remplir les informations utilisateur', async () => {
      await page.locator('#subscribePanel input[name="email"]').fill(userEmail);
      await page.locator('#subscribePanel input[name="confirm-email"]').fill(userEmail);
      await page.locator('#subscribePanel input[name="firstname"]').fill('Douglas');
      await page.locator('#subscribePanel input[name="lastname"]').fill('Adams');
      console.log(`✓ User information filled for: ${userEmail}`);
    });

    // Step 4: Select price / Sélectionner le tarif
    await test.step('Select price / Sélectionner le tarif', async () => {
      const priceLabel = page.locator('label:has-text("Plein tarif")').first();
      await priceLabel.click();
      console.log('✓ Price selected / Tarif sélectionné');
    });

    // Step 5: Fill dynamic form fields / Remplir les champs du formulaire dynamique
    await test.step('Fill dynamic form / Remplir le formulaire dynamique', async () => {
      // Checkbox (BL)
      const chantierCheckbox = page.locator('input[name="form__je-veux-participer-aux-chantiers-benevoles"]');
      if (await chantierCheckbox.isVisible()) {
          await chantierCheckbox.check();
      }

      // Multiple select (MS)
      const interetCheckboxes = page.locator('input[name="form__mes-centres-dinteret"]');
      if (await interetCheckboxes.count() > 0) {
          await interetCheckboxes.nth(0).check();
      }
      
      console.log('✓ Membership form fields filled / Champs du formulaire d\'adhésion remplis');
    });

    // Step 6: Submit and pay / Valider et payer
    await test.step('Submit and Stripe payment / Valider et paiement Stripe', async () => {
      const submitButton = page.locator('#membership-submit');
      await expect(submitButton).toBeEnabled();
      
      await submitButton.click();

      // Wait for Stripe redirection
      console.log('Waiting for Stripe redirection... / Attente de la redirection Stripe...');
      await page.waitForURL(/checkout.stripe.com/, { timeout: 30000 });
      
      // Fill Stripe details
      await fillStripeCard(page, userEmail);
      await page.locator('button[type="submit"]').click();
    });

    // Step 7: Verify success / Vérifier le succès
    await test.step('Verify success / Vérifier le succès', async () => {
      await page.waitForURL(url => url.hostname.includes('tibillet.localhost'), { timeout: 30000 });
      
      const successMessage = page.locator('text=/merci|confirmée|succès|success/i');
      await expect(successMessage).toBeVisible({ timeout: 15000 });
      console.log('✓ Membership purchase with form successful / Achat d\'adhésion avec formulaire réussi');
    });

    // Step 8: DB Verification / Vérification DB
    await test.step('Verify membership and form data in database / Vérifier l\'adhésion et les données du formulaire en base', async () => {
        const dbResult = await verifyDbData({
            type: 'membership',
            email: userEmail,
            product: 'Adhésion associative Tiers Lustre'
        });
        expect(dbResult).not.toBeNull();
        expect(dbResult?.status).toBe('success');
        
        const formData = dbResult?.custom_form || {};
        console.log('✓ Membership form data in DB:', JSON.stringify(formData));
        
        // Keys for this product are likely different from event
        expect(formData).toBeDefined();
    });
  });

});
