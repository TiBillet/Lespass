import { test, expect } from '@playwright/test';
import { loginAs } from './utils/auth';
import { createEvent, createProduct, createReservationApi, createMembershipApi } from './utils/api';

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

  test('should show all memberships and bookings / doit afficher toutes les adhésions et réservations', async ({ page, request }) => {
    const randomId = generateRandomId();
    const eventName = `E2E Summary Event ${randomId}`;
    const productName = `Billets Summary ${randomId}`;
    const membershipProductName = `Adhesion Summary ${randomId}`;
    const membershipPriceName = 'Annuelle';
    const startDate = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();

    let eventSlug = '';
    let priceUuid = '';
    let membershipPriceUuid = '';

    // Step 1: Create a free booking
    await test.step('Create a free booking / Créer une réservation gratuite', async () => {
      const eventResponse = await createEvent({
        request,
        name: eventName,
        startDate,
      });
      expect(eventResponse.ok).toBeTruthy();
      eventSlug = eventResponse.slug || '';

      const productResponse = await createProduct({
        request,
        name: productName,
        description: 'Produit pour test compte utilisateur.',
        category: 'Free booking',
        eventUuid: eventResponse.uuid,
        offers: [
          { name: 'Tarif gratuit', price: '0.00' },
        ],
      });
      expect(productResponse.ok).toBeTruthy();
      priceUuid = productResponse.offers?.[0]?.identifier || '';
      expect(priceUuid).not.toBe('');

      const reservationResponse = await createReservationApi({
        request,
        eventUuid: eventResponse.uuid || '',
        email: userEmail,
        tickets: [{ priceUuid, qty: 1 }],
        confirmed: true,
      });
      expect(reservationResponse.ok).toBeTruthy();
    });

    // Step 2: Login
    await test.step('Login / Connexion', async () => {
      await loginAs(page, userEmail);
    });

    // Step 3: Verify booking in account
    await test.step('Verify booking in account / Vérifier la réservation dans le compte', async () => {
      await page.goto('/my_account/my_reservations/');
      await page.waitForLoadState('domcontentloaded');
      
      const content = await page.locator('body').innerText();
      expect(content).toContain(eventName);
      console.log('✓ Booking found in account / Réservation trouvée dans le compte');
    });

    // Step 4: Purchase a membership (while logged in)
    await test.step('Create membership via API / Creer adhesion via API', async () => {
      const membershipProductResponse = await createProduct({
        request,
        name: membershipProductName,
        description: 'Produit adhesion pour test compte.',
        category: 'Membership',
        offers: [
          { name: membershipPriceName, price: '10.00' },
        ],
      });
      expect(membershipProductResponse.ok).toBeTruthy();
      membershipPriceUuid = membershipProductResponse.offers?.find((offer: any) => offer.name === membershipPriceName)?.identifier || '';
      expect(membershipPriceUuid).not.toBe('');

      const validUntil = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString();
      const membershipResponse = await createMembershipApi({
        request,
        priceUuid: membershipPriceUuid,
        email: userEmail,
        paymentMode: 'FREE',
        validUntil,
      });
      expect(membershipResponse.ok).toBeTruthy();
    });

    // Step 5: Verify membership in account
    await test.step('Verify membership in account / Vérifier l\'adhésion dans le compte', async () => {
      await page.goto('/my_account/membership/');
      await page.waitForLoadState('domcontentloaded');
      
      const content = await page.locator('body').innerText();
      expect(content).toContain(membershipProductName);
      console.log('✓ Membership found in account / Adhésion trouvée dans le compte');
    });
  });

});
