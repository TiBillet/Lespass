import { test, expect } from '@playwright/test';
import { verifyDbData } from './utils/db';

/**
 * TEST: Anonymous Event Booking with Dynamic Form
 * TEST : Réservation d'événement anonyme avec formulaire dynamique
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

const userEmail = `jturbeaux+form${generateRandomId()}@pm.me`;

test.describe('Anonymous Event with Form / Événement anonyme avec formulaire', () => {

  test('should book a paid event with dynamic form / doit réserver un événement payant avec formulaire dynamique', async ({ page }) => {
    
    // Step 1: Navigate to the event page / Naviguer vers la page de l'événement
    await test.step('Navigate to event / Naviguer vers l\'événement', async () => {
      // Use the identified slug
      await page.goto('/event/journee-apprenante-decouverte-tibillet-270709-0806-79462196/');
      await page.waitForLoadState('networkidle');
      console.log('✓ On event page / Sur la page de l\'événement');
    });

    // Step 2: Start booking / Commencer la réservation
    await test.step('Start booking / Commencer la réservation', async () => {
      const reserveButton = page.locator('button:has-text("book one or more seats"), button:has-text("réserver")').first();
      await reserveButton.click();
      await page.waitForSelector('#bookingPanel.show, .offcanvas.show', { state: 'visible' });
    });

    // Step 3: Fill email and quantities / Remplir l'email et les quantités
    await test.step('Fill email and select quantity / Remplir l\'email et la quantité', async () => {
      const emailInput = page.locator('#bookingPanel input[name="email"], #bookingEmail').first();
      await emailInput.fill(userEmail);

      const confirmEmailInput = page.locator('#bookingPanel input[name="email-confirm"]').first();
      if (await confirmEmailInput.isVisible()) {
        await confirmEmailInput.fill(userEmail);
      }
      
      // Select 1 ticket for "Tarif Soutien" (which is paid)
      // We use evaluate to be sure the web component bs-counter is correctly updated
      await page.evaluate(() => {
          const rows = Array.from(document.querySelectorAll('.js-order'));
          const row = rows.find(r => r.textContent?.includes('Tarif Soutien'));
          const counter = row?.querySelector('bs-counter');
          if (counter) {
              (counter as any).value = 1;
              counter.dispatchEvent(new Event('change', { bubbles: true }));
          }
      });
      
      console.log('✓ Paid ticket quantity set to 1 via JS / Quantité de billets payants fixée à 1 via JS');
      
      // Wait for any calculation to happen
      await page.waitForTimeout(1000);
    });

    // Step 4: Fill dynamic form fields / Remplir les champs du formulaire dynamique
    await test.step('Fill dynamic form / Remplir le formulaire dynamique', async () => {
      // Short text fields
      await page.locator('input[name="form__nom"]').fill('Nom Test');
      await page.locator('input[name="form__prenom"]').fill('Prenom Test');
      await page.locator('input[name="form__telephone"]').fill('0601020304');

      // Multiple select 1 (check some boxes)
      const lieuCheckboxes = page.locator('input[name="form__type-de-lieu"]');
      if (await lieuCheckboxes.count() > 0) {
          await lieuCheckboxes.nth(0).check();
      }

      // Multiple select 2 (Centres d'intérêt)
      const interetCheckboxes = page.locator('input[name="form__centres-dinteret"]');
      if (await interetCheckboxes.count() > 0) {
          await interetCheckboxes.nth(0).check();
      }

      // Single select (dropdown)
      const thematicSelect = page.locator('select[name="form__thematique-principale"]');
      if (await thematicSelect.isVisible()) {
          // Select second option if available
          await thematicSelect.selectOption({ index: 1 });
      }

      // Radio select
      const contactRadios = page.locator('input[name="form__preference-de-contact"]');
      if (await contactRadios.count() > 0) {
          await contactRadios.nth(0).check();
      }

      // Boolean (checkbox)
      const benevoleCheckbox = page.locator('input[name="form__je-veux-etre-benevole"]');
      if (await benevoleCheckbox.isVisible()) {
          await benevoleCheckbox.check();
      }

      // Long text
      const motivationTextarea = page.locator('textarea[name="form__votre-motivation"]');
      if (await motivationTextarea.isVisible()) {
          await motivationTextarea.fill('Je suis très motivé par cette journée apprenante !');
      }

      console.log('✓ Form fields filled / Champs du formulaire remplis');
    });

    // Step 5: Submit and pay / Valider et payer
    await test.step('Submit and Stripe payment / Valider et paiement Stripe', async () => {
      const submitButton = page.locator('#bookingPanel button[type="submit"]:has-text("booking request"), #bookingPanel button[type="submit"]:has-text("réserver")').first();
      
      // We ensure the button is not disabled
      await expect(submitButton).toBeEnabled();
      
      // Wait a bit to ensure all fields are processed by JS if any
      await page.waitForTimeout(1000);
      
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
          const panelContent = await page.locator('#bookingPanel').innerText();
          console.log('Panel content:', panelContent);
          throw e;
      }
      
      // Fill Stripe details
      await page.locator('input#cardNumber').waitFor({ state: 'visible', timeout: 20000 });
      await page.locator('input#cardNumber').fill('4242424242424242');
      await page.locator('input#cardExpiry').fill('12/42');
      await page.locator('input#cardCvc').fill('424');
      
      const billingName = page.locator('input#billingName');
      if (await billingName.count() > 0) {
          await billingName.fill('Douglas Adams');
      }
      
      await page.locator('button[type="submit"]').click();
    });

    // Step 6: Verify success / Vérifier le succès
    await test.step('Verify success / Vérifier le succès', async () => {
      await page.waitForURL(url => url.hostname.includes('tibillet.localhost'), { timeout: 30000 });
      
      const successMessage = page.locator('text=/merci|confirmée|succès|success/i');
      await expect(successMessage).toBeVisible({ timeout: 15000 });
      console.log('✓ Paid booking with form successful / Réservation payante avec formulaire réussie');
    });

    // Step 7: DB Verification / Vérification DB
    await test.step('Verify reservation and form data in database / Vérifier la réservation et les données du formulaire en base', async () => {
        const dbResult = await verifyDbData({
            type: 'reservation',
            email: userEmail,
            event: 'Journée apprenante'
        });
        expect(dbResult).not.toBeNull();
        expect(dbResult?.status).toBe('success');
        
        // Verify custom form data / Vérifier les données du formulaire personnalisé
        const formData = dbResult?.custom_form || {};
        console.log('✓ Form data in DB:', JSON.stringify(formData));
        
        // Check for specific fields (keys are labels if not slugified or based on labels)
        // In the received data, keys seem to be labels: "Nom", "Prénom"
        expect(formData).toHaveProperty('Nom', 'Nom Test');
        expect(formData).toHaveProperty('Prénom', 'Prenom Test');
    });
  });

});
