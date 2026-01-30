import { test, expect } from '@playwright/test';
import { createEvent, createProduct, createReservationApi, createMembershipApi } from './utils/api';
import { loginAs } from './utils/auth';

/**
 * TEST: Reservation limits (stock, max per user, membership required)
 * TEST : Limites de reservation (stock, max par utilisateur, adhesion requise)
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

test.describe('Reservation limits / Limites reservation', () => {
  test('should show stock/max/membership messages / doit montrer les messages', async ({ page, request }) => {
    const randomId = generateRandomId();
    const userEmail = `jturbeaux+limit${randomId}@pm.me`;

    const eventName = `E2E Reservation Limits ${randomId}`;
    const productName = `Billets Limits ${randomId}`;
    const priceName = 'Tarif Unique';

    const maxEventName = `E2E Event Max ${randomId}`;
    const maxProductName = `Billets Event Max ${randomId}`;

    const membershipProductName = `Adhesion Required ${randomId}`;
    const membershipPriceName = 'Adhesion Tarif';
    const restrictedEventName = `E2E Reservation Restricted ${randomId}`;
    const restrictedProductName = `Billets Restricted ${randomId}`;
    const restrictedPriceName = 'Tarif Reserve';

    const startDate = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();

    let eventSlug = '';
    let maxEventSlug = '';
    let restrictedEventSlug = '';
    let eventUuid = '';
    let maxEventUuid = '';
    let priceUuid = '';
    let maxPriceUuid = '';
    let membershipPriceUuid = '';

    await test.step('Create events and products / Creer events et produits', async () => {
      const eventResponse = await createEvent({
        request,
        name: eventName,
        startDate,
        maxPerUser: 5,
      });
      if (!eventResponse.ok) {
        throw new Error(`createEvent failed: ${eventResponse.status} ${eventResponse.errorText}`);
      }
      eventSlug = eventResponse.slug || '';
      eventUuid = eventResponse.uuid || '';

      const productResponse = await createProduct({
        request,
        name: productName,
        description: 'Produit pour stock et max par prix.',
        category: 'Free booking',
        eventUuid: eventResponse.uuid,
        offers: [
          {
            name: priceName,
            price: '0.00',
            stock: 1,
            maxPerUser: 1,
          },
        ],
      });
      if (!productResponse.ok) {
        throw new Error('createProduct failed for stock/max price');
      }
      priceUuid = productResponse.offers?.find((offer: any) => offer.name === priceName)?.identifier || '';
      if (!priceUuid) {
        throw new Error('Price UUID missing for main product');
      }

      const maxEventResponse = await createEvent({
        request,
        name: maxEventName,
        startDate,
        maxPerUser: 1,
      });
      if (!maxEventResponse.ok) {
        throw new Error(`createEvent failed: ${maxEventResponse.status} ${maxEventResponse.errorText}`);
      }
      maxEventSlug = maxEventResponse.slug || '';
      maxEventUuid = maxEventResponse.uuid || '';

      const maxProductResponse = await createProduct({
        request,
        name: maxProductName,
        description: 'Produit pour max event.',
        category: 'Free booking',
        eventUuid: maxEventResponse.uuid,
        offers: [
          {
            name: 'Tarif Event Max',
            price: '0.00',
          },
        ],
      });
      if (!maxProductResponse.ok) {
        throw new Error('createProduct failed for event max');
      }
      maxPriceUuid = maxProductResponse.offers?.[0]?.identifier || '';
      if (!maxPriceUuid) {
        throw new Error('Price UUID missing for max product');
      }

      const restrictedEventResponse = await createEvent({
        request,
        name: restrictedEventName,
        startDate,
      });
      if (!restrictedEventResponse.ok) {
        throw new Error(`createEvent failed: ${restrictedEventResponse.status} ${restrictedEventResponse.errorText}`);
      }
      restrictedEventSlug = restrictedEventResponse.slug || '';

      const membershipProductResponse = await createProduct({
        request,
        name: membershipProductName,
        description: 'Adhesion de test.',
        category: 'Membership',
        offers: [
          { name: membershipPriceName, price: '10.00' },
        ],
      });
      if (!membershipProductResponse.ok) {
        throw new Error('createProduct failed for membership');
      }
      membershipPriceUuid = membershipProductResponse.offers?.find((offer: any) => offer.name === membershipPriceName)?.identifier || '';
      if (!membershipPriceUuid) {
        throw new Error('Membership price UUID missing');
      }
      const membershipProductUuid = membershipProductResponse.uuid;
      if (!membershipProductUuid) {
        throw new Error('Membership product UUID missing');
      }

      const restrictedProductResponse = await createProduct({
        request,
        name: restrictedProductName,
        description: 'Produit avec adhesion obligatoire.',
        category: 'Free booking',
        eventUuid: restrictedEventResponse.uuid,
        offers: [
          {
            name: restrictedPriceName,
            price: '0.00',
            membershipRequiredProduct: membershipProductUuid,
          },
        ],
      });
      if (!restrictedProductResponse.ok) {
        throw new Error('createProduct failed for membership required');
      }
    });

    await test.step('Create reservations via API / Creer reservations via API', async () => {
      const res1 = await createReservationApi({
        request,
        eventUuid,
        email: userEmail,
        tickets: [{ priceUuid, qty: 1 }],
        confirmed: true,
      });
      expect(res1.ok).toBeTruthy();

      const res2 = await createReservationApi({
        request,
        eventUuid: maxEventUuid,
        email: userEmail,
        tickets: [{ priceUuid: maxPriceUuid, qty: 1 }],
        confirmed: true,
      });
      expect(res2.ok).toBeTruthy();
    });

    await test.step('Anonymous sees out of stock / Anonyme voit stock epuise', async () => {
      await page.goto(`/event/${eventSlug}/`);
      await page.waitForLoadState('domcontentloaded');
      const openButton = page.locator('[data-testid="booking-open-panel"], button:has-text("book one or more seats"), button:has-text("réserver")').first();
      await openButton.click();
      const priceBlock = page.locator('[data-testid^="booking-price-"], .js-order').filter({ hasText: priceName }).first();
      await expect(priceBlock).toContainText('no longer available');
    });

    await test.step('Logged user sees max per user / Connecte voit max par user', async () => {
      await loginAs(page, userEmail);
      await page.goto(`/event/${eventSlug}/`);
      await page.waitForLoadState('domcontentloaded');
      const openButton = page.locator('[data-testid="booking-open-panel"], button:has-text("book one or more seats"), button:has-text("réserver")').first();
      await openButton.click();
      const priceBlock = page.locator('[data-testid^="booking-price-"], .js-order').filter({ hasText: priceName }).first();
      await expect(priceBlock).toContainText('maximum number of reservations');
    });

    await test.step('Event max per user message / Message max event', async () => {
      await page.goto(`/event/${maxEventSlug}/`);
      await page.waitForLoadState('domcontentloaded');
      const pageText = await page.textContent('body');
      expect(pageText || '').toContain('maximum number of tickets');
    });

    await test.step('Anonymous and non member messages / Messages anonyme et non membre', async () => {
      const browser = page.context().browser();
      if (!browser) throw new Error('Browser not available');

      const anonContext = await browser.newContext();
      const anonPage = await anonContext.newPage();

      await anonPage.goto(`/event/${restrictedEventSlug}/`);
      await anonPage.waitForLoadState('domcontentloaded');
      const openButtonAnon = anonPage.locator('[data-testid="booking-open-panel"], button:has-text("book one or more seats"), button:has-text("réserver")').first();
      await openButtonAnon.click();
      const priceBlock = anonPage.locator('[data-testid^="booking-price-"], .js-order').filter({ hasText: restrictedPriceName }).first();
      await expect(priceBlock).toContainText('Log in to access this rate');

      await anonContext.close();

      await page.goto(`/event/${restrictedEventSlug}/`);
      await page.waitForLoadState('domcontentloaded');
      const openButton = page.locator('[data-testid="booking-open-panel"], button:has-text("book one or more seats"), button:has-text("réserver")').first();
      await openButton.click();
      const priceBlockLogged = page.locator('[data-testid^="booking-price-"], .js-order').filter({ hasText: restrictedPriceName }).first();
      await expect(priceBlockLogged).toContainText('Suscribe to access this rate');
    });

    await test.step('Member can see counter / Membre peut voir le compteur', async () => {
      const validUntil = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString();
      const membership = await createMembershipApi({
        request,
        priceUuid: membershipPriceUuid,
        email: userEmail,
        paymentMode: 'FREE',
        validUntil,
      });
      expect(membership.ok).toBeTruthy();

      await page.goto(`/event/${restrictedEventSlug}/`);
      await page.waitForLoadState('domcontentloaded');
      const openButton = page.locator('[data-testid="booking-open-panel"], button:has-text("book one or more seats"), button:has-text("réserver")').first();
      await openButton.click();
      const priceBlock = page.locator('[data-testid^="booking-price-"], .js-order').filter({ hasText: restrictedPriceName }).first();
      const counter = priceBlock.locator('bs-counter');
      await expect(counter).toBeVisible();
    });
  });
});
