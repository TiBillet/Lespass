import { test, expect } from '@playwright/test';
import { verifyDbData } from './utils/db';
import { createEvent, createProduct } from './utils/api';
import { loginAs } from './utils/auth';

/**
 * TEST: Anonymous Event Bookings
 * TEST : Réservations d'événements anonymes
 * 
 * Objectives:
 * 1. Book a free event and verify the confirmation message.
 * 2. Book a paid event using specific Stripe test credentials.
 */

// Function to generate a random 8-character ID
// Fonction pour générer un ID aléatoire de 8 caractères
function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

const userEmail = `jturbeaux+${generateRandomId()}@pm.me`;

test.describe('Anonymous Event Bookings / Réservations d\'événements anonymes', () => {

  test('should book a free event (Disco Caravane) / doit réserver un événement gratuit (Disco Caravane)', async ({ page, request }) => {
    const randomId = generateRandomId();
    const freeEventName = `Disco Caravane ${randomId}`;
    const freeProductName = `Billets Disco ${randomId}`;
    const freeStartDate = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();

    let freeEventSlug = '';

    await test.step('Create free event and product / Creer event gratuit', async () => {
      const eventResponse = await createEvent({
        request,
        name: freeEventName,
        startDate: freeStartDate,
      });
      expect(eventResponse.ok).toBeTruthy();
      freeEventSlug = eventResponse.slug || '';

      const productResponse = await createProduct({
        request,
        name: freeProductName,
        description: 'Produit gratuit pour test anonyme.',
        category: 'Free booking',
        eventUuid: eventResponse.uuid,
        offers: [
          { name: 'Tarif gratuit', price: '0.00' },
        ],
      });
      expect(productResponse.ok).toBeTruthy();
    });

    // Step 1: Navigate to the events page / Naviguer vers la page des événements
    await test.step('Navigate to events / Naviguer vers les événements', async () => {
      await page.goto('/event/');
      await page.waitForLoadState('domcontentloaded');
      console.log('✓ On events page / Sur la page des événements');
    });

    // Step 2: Select "Disco Caravane" / Sélectionner "Disco Caravane"
    await test.step('Select event / Sélectionner l\'événement', async () => {
      await page.goto(`/event/${freeEventSlug}/`);
      await page.waitForLoadState('domcontentloaded');
      console.log('✓ Event selected / Événement sélectionné');
    });

    // Step 3: Start booking / Commencer la réservation
    await test.step('Start booking / Commencer la réservation', async () => {
      // The button seen in curl: "I want to book one or more seats"
      const reserveButton = page.locator('button:has-text("book one or more seats"), button:has-text("réserver")').first();
      await reserveButton.click();
      await page.waitForSelector('#bookingPanel.show, .offcanvas.show', { state: 'visible' });
    });

    // Step 4: Fill email and select quantity / Remplir l'email et sélectionner la quantité
    await test.step('Fill email and quantity / Remplir l\'email et la quantité', async () => {
      // Inside offcanvas
      const emailInput = page.locator('#bookingPanel input[name="email"], #bookingEmail').first();
      await emailInput.fill(userEmail);

      const confirmEmailInput = page.locator('#bookingPanel input[name="email-confirm"]').first();
      if (await confirmEmailInput.isVisible()) {
        await confirmEmailInput.fill(userEmail);
      }
      
      // Select 1 ticket using the bs-counter / Sélectionner 1 billet via le bs-counter
      const counter = page.locator('bs-counter').first();
      const plusButton = counter.locator('.bi-plus, button:has(.bi-plus)').first();
      
      await plusButton.click();
      console.log('✓ Ticket quantity incremented / Quantité de billets augmentée');

      const submitButton = page.locator('#bookingPanel button[type="submit"]:has-text("booking request"), #bookingPanel button[type="submit"]:has-text("réserver")').first();
      await submitButton.click();
    });

    // Step 5: Verify confirmation message / Vérifier le message de confirmation
    await test.step('Verify message / Vérifier le message', async () => {
      // We expect a success message in the offcanvas or page
      await page.waitForTimeout(3000); // Wait for HTMX
      
      const content = await page.innerText('body');
      const lowerContent = content.toLowerCase();
      
      // Check for user-defined keywords
      const found = lowerContent.includes('reservation ok') || 
                    lowerContent.includes('merci de valider votre email') ||
                    lowerContent.includes('please validate your e-mail') ||
                    lowerContent.includes('votre réservation est confirmée') ||
                    lowerContent.includes('merci pour votre réservation');
                    
      if (!found) {
          console.log('DEBUG: Content after submission:', content);
      }
      expect(found).toBeTruthy();
      console.log('✓ Free booking successful / Réservation gratuite réussie');
    });

    // Step 7: DB Verification / Vérification DB
    await test.step('Verify reservation in database / Vérifier la réservation en base de données', async () => {
        const dbResult = await verifyDbData({
            type: 'reservation',
            email: userEmail,
            event: freeEventName,
        });
        expect(dbResult).not.toBeNull();
        expect(dbResult?.status).toBe('success');
    });
  });

  test('should book a paid event (What the Funk) / doit réserver un événement payant (What the Funk)', async ({ page, request }) => {
    const randomId = generateRandomId();
    const paidEventName = `What the Funk ${randomId}`;
    const paidProductName = `Billets Funk ${randomId}`;
    const paidStartDate = new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString();

    let paidEventSlug = '';

    await test.step('Create paid event and product / Creer event payant', async () => {
      const eventResponse = await createEvent({
        request,
        name: paidEventName,
        startDate: paidStartDate,
      });
      expect(eventResponse.ok).toBeTruthy();
      paidEventSlug = eventResponse.slug || '';

      const productResponse = await createProduct({
        request,
        name: paidProductName,
        description: 'Produit payant pour test anonyme.',
        category: 'Ticket booking',
        eventUuid: eventResponse.uuid,
        offers: [
          { name: 'Plein tarif', price: '12.00' },
        ],
      });
      expect(productResponse.ok).toBeTruthy();
    });
    
    // Step 1: Navigate to events / Naviguer vers les événements
    await page.goto('/event/');
    await page.waitForLoadState('domcontentloaded');

    // Step 2: Select "What the Funk" / Sélectionner "What the Funk"
    await page.goto(`/event/${paidEventSlug}/`);
    await page.waitForLoadState('domcontentloaded');

    // Step 3: Start booking / Commencer la réservation
    const reserveButton = page.locator('button:has-text("book one or more seats"), button:has-text("réserver")').first();
    await reserveButton.click();
    await page.waitForSelector('#bookingPanel.show, .offcanvas.show', { state: 'visible' });

    // Step 4: Fill email / Remplir l'email
    const emailInput = page.locator('#bookingPanel input[name="email"], #bookingEmail').first();
    await emailInput.fill(userEmail);
    
    const confirmEmailInput = page.locator('#bookingPanel input[name="email-confirm"]').first();
    if (await confirmEmailInput.isVisible()) {
      await confirmEmailInput.fill(userEmail);
    }
    
    // Step 5: Select quantities / Sélectionner les quantités
    // For paid events, we often have a table of prices. We select 1 for "Plein tarif"
    await test.step('Select quantities / Sélectionner les quantités', async () => {
      // Find the row with "Plein tarif" and its counter
      const row = page.locator('div.js-order:has-text("Plein tarif"), tr:has-text("Plein tarif")').first();
      const plusButton = row.locator('bs-counter .bi-plus, bs-counter button:has(.bi-plus)').first();
      
      if (await plusButton.isVisible()) {
          await plusButton.click();
      } else {
          // Fallback evaluation
          await page.evaluate(() => {
              const rows = Array.from(document.querySelectorAll('.js-order'));
              const pleinTarifRow = rows.find(r => r.textContent?.includes('Plein tarif'));
              const counter = pleinTarifRow?.querySelector('bs-counter');
              if (counter) {
                  (counter as any).value = 1;
                  counter.dispatchEvent(new Event('change', { bubbles: true }));
              }
          });
      }
      
      const submitButton = page.locator('#bookingPanel button[type="submit"]:has-text("booking request"), #bookingPanel button[type="submit"]:has-text("réserver")').first();
      await submitButton.click();
    });

    // Step 6: Stripe Payment / Paiement Stripe
    await test.step('Stripe Payment / Paiement Stripe', async () => {
      // Wait for Stripe redirection / Attendre la redirection Stripe
      await page.waitForURL(/checkout.stripe.com/, { timeout: 30000 });
      
      // Card details from user instructions / Détails de carte fournis par l'utilisateur
      // We use more robust selectors and wait for visibility
      const cardNumberInput = page.locator('input#cardNumber');
      await cardNumberInput.waitFor({ state: 'visible', timeout: 20000 });
      
      try {
          // If email is not pre-filled
          const emailInput = page.locator('input#email');
          if (await emailInput.count() > 0 && await emailInput.isVisible()) {
              await emailInput.fill(userEmail);
          }
          
          await page.locator('input#cardNumber').fill('4242424242424242');
          await page.locator('input#cardExpiry').fill('12/42');
          await page.locator('input#cardCvc').fill('424');
          
          const billingName = page.locator('input#billingName');
          if (await billingName.count() > 0) {
              await billingName.fill('Douglas Adams');
          } else {
              // Try by label if ID is different
              const label = page.getByLabel(/Nom|Name|Nom sur la carte/i).first();
              if (await label.count() > 0) {
                  await label.fill('Douglas Adams');
              }
          }
          
          // Pay / Payer
          await page.locator('button[type="submit"]').click();
      } catch (e) {
          console.log('⚠ Stripe interaction failed, trying fallback / Échec interaction Stripe, tentative alternative');
          // Global fallback using placeholders
          await page.getByPlaceholder(/email/i).first().fill(userEmail);
          await page.locator('input#cardNumber').fill('4242424242424242');
          await page.locator('input#cardExpiry').fill('12/42');
          await page.locator('input#cardCvc').fill('424');
          await page.getByPlaceholder(/nom|name/i).first().fill('Douglas Adams');
          await page.locator('button[type="submit"]').click();
      }
    });

    // Step 7: Verify success / Vérifier le succès
    await test.step('Verify success / Vérifier le succès', async () => {
      // Redirect back to the app / Retour sur l'application
      await page.waitForURL(url => url.hostname.includes('tibillet.localhost'), { timeout: 30000 });
      
      const successMessage = page.locator('text=/merci|confirmée|succès|success/i');
      await expect(successMessage).toBeVisible({ timeout: 15000 });
      console.log('✓ Paid booking successful / Réservation payante réussie');
    });

    // Step 7: DB Verification / Vérification DB
    await test.step('Verify paid reservation in database / Vérifier la réservation payante en base de données', async () => {
        const dbResult = await verifyDbData({
            type: 'reservation',
            email: userEmail,
            event: paidEventName,
        });
        expect(dbResult).not.toBeNull();
        expect(dbResult?.status).toBe('success');
        // Paid tickets should have status 'V' (Valid) or 'P' (Paid) depending on flow
        console.log(`✓ Ticket status in DB: ${dbResult?.ticket_status}`);
    });
  });

  test('should book mixed free price and fixed price tickets / doit réserver prix libres + prix fixe', async ({ page, request }) => {
    const randomId = generateRandomId();
    const eventName = `Prix Libre Mix ${randomId}`;
    const productName = `Billets Mix ${randomId}`;
    const startDate = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString();
    const accountEmail = `jturbeaux+mix${generateRandomId()}@pm.me`;

    const freePriceNameA = 'Tarif libre';
    const fixedPriceName = 'Tarif fixe';

    const freeAmountA = '7.50';
    const fixedAmount = '12.00';

    let eventSlug = '';
    let freePriceUuidA = '';
    let fixedPriceUuid = '';

    await test.step('Create mixed price event and product / Creer event mixte', async () => {
      const eventResponse = await createEvent({
        request,
        name: eventName,
        startDate,
        maxPerUser: 2,
      });
      expect(eventResponse.ok).toBeTruthy();
      eventSlug = eventResponse.slug || '';

      const productResponse = await createProduct({
        request,
        name: productName,
        description: 'Produit mixte pour test prix libre.',
        category: 'Ticket booking',
        eventUuid: eventResponse.uuid,
        offers: [
          { name: freePriceNameA, price: '1.00', freePrice: true },
          { name: fixedPriceName, price: fixedAmount },
        ],
      });
      expect(productResponse.ok).toBeTruthy();

      freePriceUuidA = productResponse.offers?.find((offer: any) => offer.name === freePriceNameA)?.identifier || '';
      fixedPriceUuid = productResponse.offers?.find((offer: any) => offer.name === fixedPriceName)?.identifier || '';

      expect(freePriceUuidA).not.toBe('');
      expect(fixedPriceUuid).not.toBe('');
    });

    await test.step('Open booking form / Ouvrir le formulaire', async () => {
      await page.goto(`/event/${eventSlug}/`);
      await page.waitForLoadState('domcontentloaded');

      const reserveButton = page.locator('button:has-text("book one or more seats"), button:has-text("réserver")').first();
      await reserveButton.click();
      await page.waitForSelector('#bookingPanel.show, .offcanvas.show', { state: 'visible' });
    });

    await test.step('Fill email and select tickets / Remplir email et billets', async () => {
      const emailInput = page.locator('#bookingPanel input[name="email"], #bookingEmail').first();
      await emailInput.fill(accountEmail);

      const confirmEmailInput = page.locator('#bookingPanel input[name="email-confirm"]').first();
      if (await confirmEmailInput.isVisible()) {
        await confirmEmailInput.fill(accountEmail);
      }

      const setTicketQuantity = async (priceUuid: string, qty: number) => {
        await page.evaluate(({ priceUuid, qty }) => {
          const counter = document.querySelector(`[data-testid="booking-amount-${priceUuid}"]`) as any;
          if (!counter) return;
          counter.value = qty;

          const input = counter.shadowRoot?.querySelector('input#counter') as HTMLInputElement | null;
          if (input) {
            input.value = String(qty);
            input.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
          }
        }, { priceUuid, qty });
      };

      await setTicketQuantity(freePriceUuidA, 1);
      const amountContainerA = page.locator(`[data-testid="booking-custom-amount-container-${freePriceUuidA}"]`).first();
      await amountContainerA.waitFor({ state: 'visible' });
      const amountInputA = page.locator(`[data-testid="booking-custom-amount-${freePriceUuidA}"]`).first();
      await amountInputA.fill(freeAmountA);
      expect(await amountInputA.inputValue()).toBe(freeAmountA);

      await setTicketQuantity(fixedPriceUuid, 1);

      const submitButton = page.locator('#bookingPanel button[type="submit"]:has-text("booking request"), #bookingPanel button[type="submit"]:has-text("réserver")').first();
      await submitButton.click();
    });

    await test.step('Stripe Payment / Paiement Stripe', async () => {
      await page.waitForURL(/checkout.stripe.com/, { timeout: 30000 });

      const cardNumberInput = page.locator('input#cardNumber');
      await cardNumberInput.waitFor({ state: 'visible', timeout: 20000 });

      await page.locator('input#cardNumber').fill('4242424242424242');
      await page.locator('input#cardExpiry').fill('12/42');
      await page.locator('input#cardCvc').fill('424');

      const billingName = page.locator('input#billingName');
      if (await billingName.count() > 0) {
        await billingName.fill('Douglas Adams');
      } else {
        const label = page.getByLabel(/Nom|Name|Nom sur la carte/i).first();
        if (await label.count() > 0) {
          await label.fill('Douglas Adams');
        }
      }

      await page.locator('button[type="submit"]').click();
    });

    await test.step('Verify success and account values / Vérifier succès et montants', async () => {
      await page.waitForURL(url => url.hostname.includes('tibillet.localhost'), { timeout: 30000 });
      await expect(page.locator('text=/merci|confirmée|succès|success/i')).toBeVisible({ timeout: 15000 });

      await loginAs(page, accountEmail);
      await page.goto('/my_account/my_reservations/');
      await page.waitForLoadState('domcontentloaded');

      const reservationCard = page.locator('.reservation-card', { hasText: eventName }).first();
      await expect(reservationCard).toBeVisible();

      const ticketItems = reservationCard.locator('.accordion-item');
      const ticketCount = await ticketItems.count();
      expect(ticketCount).toBeGreaterThanOrEqual(2);

      for (let i = 0; i < ticketCount; i += 1) {
        const item = ticketItems.nth(i);
        const toggle = item.locator('.accordion-button').first();
        await toggle.click();
      }

      const expectTicketValue = async (rateName: string, expectedValue: string) => {
        let found = false;
        for (let i = 0; i < ticketCount; i += 1) {
          const item = ticketItems.nth(i);
          const rateCell = item.locator('tr:has(th:has-text("Rate name")) td').first();
          const rateText = (await rateCell.innerText()).trim();
          if (rateText.includes(rateName)) {
            const valueCell = item.locator('tr:has(th:has-text("Value")) td').first();
            const valueText = (await valueCell.innerText()).replace(',', '.').trim();
            expect(valueText).toContain(expectedValue);
            found = true;
            break;
          }
        }
        expect(found).toBeTruthy();
      };

      await expectTicketValue(freePriceNameA, freeAmountA);
      await expectTicketValue(fixedPriceName, fixedAmount);
    });
  });

});
