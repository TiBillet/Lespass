import { test, expect } from '@playwright/test';
import { createEvent, createProduct, createMembershipApi } from './utils/api';
import { loginAs } from './utils/auth';

/**
 * TEST: Adhesion obligatoire on event booking form
 * TEST : Adhesion obligatoire sur le formulaire de reservation d'un event
 *
 * Flow :
 * 1. API: Create membership product + ticket product with adhesion required + event
 * 2. Login, go to event page -> verify "Suscribe to access this rate." is shown
 * 3. API: Create FREE membership for the user
 * 4. Reload event page -> verify bs-counter is visible (user can book)
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

test.describe('Adhesion obligatoire on event / Adhesion obligatoire sur event', () => {
  const randomId = generateRandomId();
  const membershipProductName = `Adhesion Event Test ${randomId}`;
  const ticketProductName = `Billet Adh Required ${randomId}`;
  const eventName = `Event Adh Test ${randomId}`;
  const userEmail = `testadh+${randomId}@pm.me`;

  let membershipProductUuid: string;
  let membershipPriceUuid: string;
  let ticketPriceUuid: string;
  let eventSlug: string;

  test('should block booking without membership then allow after subscribing', async ({ page, request }) => {
    test.setTimeout(120000);

    // --- API Setup ---
    await test.step('Create membership product via API / Creer produit adhesion via API', async () => {
      const membershipResponse = await createProduct({
        request,
        name: membershipProductName,
        description: 'Adhesion de test pour verifier le blocage sur event',
        category: 'Membership',
        offers: [
          {
            name: 'Tarif adhesion gratuit',
            price: '0.00',
            subscriptionType: 'Y',
          },
        ],
      });
      expect(membershipResponse.ok).toBeTruthy();
      membershipProductUuid = membershipResponse.uuid;
      membershipPriceUuid = membershipResponse.offers?.[0]?.identifier;
      expect(membershipProductUuid).toBeTruthy();
      expect(membershipPriceUuid).toBeTruthy();
      console.log(`Membership product: ${membershipProductUuid}, price: ${membershipPriceUuid}`);
    });

    await test.step('Create event via API / Creer event via API', async () => {
      const eventResponse = await createEvent({
        request,
        name: eventName,
        startDate: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
      });
      expect(eventResponse.ok).toBeTruthy();
      eventSlug = eventResponse.slug;
      console.log(`Event slug: ${eventSlug}, uuid: ${eventResponse.uuid}`);

      // Create ticket product linked to event, with adhesion required
      // Creer produit billet lie a l'event, avec adhesion obligatoire
      const ticketResponse = await createProduct({
        request,
        name: ticketProductName,
        description: 'Billet accessible uniquement aux adherents',
        category: 'Ticket booking',
        eventUuid: eventResponse.uuid,
        offers: [
          {
            name: 'Place adherent',
            price: '5.00',
            membershipRequiredProduct: membershipProductUuid,
          },
        ],
      });
      expect(ticketResponse.ok).toBeTruthy();
      ticketPriceUuid = ticketResponse.offers?.[0]?.identifier;
      expect(ticketPriceUuid).toBeTruthy();
      console.log(`Ticket product: ${ticketResponse.uuid}, price: ${ticketPriceUuid}`);
    });

    // --- Login ---
    await test.step('Login as test user / Se connecter', async () => {
      await loginAs(page, userEmail);
    });

    // --- Check event page: booking blocked ---
    await test.step('Verify booking blocked without membership / Verifier blocage sans adhesion', async () => {
      await page.goto(`/event/${eventSlug}/`);
      await page.waitForLoadState('domcontentloaded');

      // Open booking panel
      // Ouvrir le panneau de reservation
      const reserveButton = page.locator('button:has-text("book one or more seats"), button:has-text("reserver")').first();
      await reserveButton.click();
      await page.waitForSelector('#bookingPanel.show, .offcanvas.show', { state: 'visible' });

      // Verify alert with membership name and link is visible
      // Verifier que l'alerte avec le nom de l'adhesion et un lien est visible
      const subscribeAlert = page.locator('.alert-info').filter({ hasText: membershipProductName });
      await expect(subscribeAlert).toBeVisible({ timeout: 5000 });

      // Verify the link points to the memberships page
      // Verifier que le lien pointe vers la page adhesions
      const membershipLink = subscribeAlert.locator(`a[href*="/memberships/"]`);
      await expect(membershipLink).toBeVisible();
      await expect(membershipLink).toHaveText(membershipProductName);
      console.log('Alert with membership name and link visible - OK');

      // Verify bs-counter is NOT visible for this price
      // Verifier que le bs-counter n'est PAS visible pour ce tarif
      const counter = page.locator(`[data-testid="booking-amount-${ticketPriceUuid}"]`);
      await expect(counter).toHaveCount(0);
      console.log('bs-counter not present for restricted price - OK');
    });

    // --- Subscribe via API ---
    await test.step('Create FREE membership via API / Creer adhesion gratuite via API', async () => {
      const membershipResult = await createMembershipApi({
        request,
        priceUuid: membershipPriceUuid,
        email: userEmail,
        firstName: 'Test',
        lastName: 'Adherent',
        paymentMode: 'FREE',
      });
      expect(membershipResult.ok).toBeTruthy();
      console.log(`Membership created for ${userEmail}`);
    });

    // --- Reload and check: booking available ---
    await test.step('Verify booking available after membership / Verifier acces apres adhesion', async () => {
      await page.reload();
      await page.waitForLoadState('domcontentloaded');

      // Re-open booking panel
      // Ré-ouvrir le panneau de reservation
      const reserveButton = page.locator('button:has-text("book one or more seats"), button:has-text("reserver")').first();
      await reserveButton.click();
      await page.waitForSelector('#bookingPanel.show, .offcanvas.show', { state: 'visible' });

      // Verify alert is gone
      // Verifier que l'alerte a disparu
      const subscribeAlert = page.locator('.alert-info').filter({ hasText: membershipProductName });
      await expect(subscribeAlert).toHaveCount(0);
      console.log('Alert gone after subscription - OK');

      // Verify bs-counter IS visible for this price
      // Verifier que le bs-counter EST visible pour ce tarif
      const counter = page.locator(`[data-testid="booking-amount-${ticketPriceUuid}"]`);
      await expect(counter).toBeVisible({ timeout: 5000 });
      console.log('bs-counter visible for subscribed user - OK');
    });

    console.log('Test passed / Test reussi');
  });
});
