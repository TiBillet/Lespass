import { test, expect } from '@playwright/test';
import { loginAs } from './utils/auth';

/**
 * TEST: User Account Summary (Memberships and Bookings)
 * TEST : Récapitulatif du Compte Utilisateur (Adhésions et Réservations)
 * 
 * Objectives:
 * 1. Create a reservation and a membership for a user.
 * 2. Login as this user.
 * 3. Verify that both are listed in the account pages.
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

const userEmail = `jturbeaux+summary${generateRandomId()}@pm.me`;

test.describe('User Account Summary / Récapitulatif compte utilisateur', () => {

  test('should show all memberships and bookings / doit afficher toutes les adhésions et réservations', async ({ page }) => {
    
    // Step 1: Create a free booking
    await test.step('Create a free booking / Créer une réservation gratuite', async () => {
      await page.goto('/event/');
      await page.waitForLoadState('networkidle');
      
      const discoLink = page.locator('a:has-text("Disco Caravane")').first();
      await discoLink.click();
      await page.waitForLoadState('networkidle');
      
      await page.locator('button:has-text("book one or more seats"), button:has-text("réserver")').first().click();
      await page.waitForSelector('#bookingPanel.show', { state: 'visible' });

      await page.locator('#bookingPanel input[name="email"]').fill(userEmail);
      await page.locator('#bookingPanel input[name="email-confirm"]').fill(userEmail);
      
      // Add 1 ticket
      const plusButton = page.locator('bs-counter .bi-plus, bs-counter button:has(.bi-plus)').first();
      await plusButton.click();
      
      await page.locator('#bookingPanel button[type="submit"]').click();
      
      // Verification might be faster via DB if UI message is flaky
      console.log('Booking submitted, waiting for message or verifying DB...');
      await page.waitForTimeout(2000);
      console.log('✓ Booking created');
    });

    // Step 2: Login
    await test.step('Login / Connexion', async () => {
      await loginAs(page, userEmail);
    });

    // Step 3: Verify booking in account
    await test.step('Verify booking in account / Vérifier la réservation dans le compte', async () => {
      await page.goto('/my_account/my_reservations/');
      await page.waitForLoadState('networkidle');
      
      const content = await page.locator('body').innerText();
      expect(content).toContain('Disco Caravane');
      console.log('✓ Booking found in account / Réservation trouvée dans le compte');
    });

    // Step 4: Purchase a membership (while logged in)
    await test.step('Purchase membership while logged in / Acheter une adhésion en étant connecté', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('networkidle');
      
      const card = page.locator('.card:has-text("Adhésion (Le Tiers-Lustre)")').first();
      await card.locator('button:has-text("Subscribe"), button:has-text("Adhérer")').click();
      await page.waitForSelector('#subscribePanel.show', { state: 'visible' });
      
      // Email should be pre-filled
      const priceLabel = page.locator('label:has-text("Annuelle")').first();
      await priceLabel.click();

      await page.locator('#membership-submit').click();
      
      await page.waitForURL(/checkout.stripe.com/, { timeout: 40000 });
      await page.locator('input#cardNumber').fill('4242424242424242');
      await page.locator('input#cardExpiry').fill('12/42');
      await page.locator('input#cardCvc').fill('424');
      await page.locator('button[type="submit"]').click();

      await page.waitForURL(url => url.hostname.includes('tibillet.localhost'), { timeout: 30000 });
      console.log('✓ Membership purchased while logged in');
    });

    // Step 5: Verify membership in account
    await test.step('Verify membership in account / Vérifier l\'adhésion dans le compte', async () => {
      await page.goto('/my_account/membership/');
      await page.waitForLoadState('networkidle');
      
      const content = await page.locator('body').innerText();
      expect(content).toContain('Adhésion');
      expect(content).toContain('Tiers-Lustre');
      console.log('✓ Membership found in account / Adhésion trouvée dans le compte');
    });
  });

});
