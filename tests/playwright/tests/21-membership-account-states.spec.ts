import { test, expect } from '@playwright/test';
import { createProduct, createMembershipApi } from './utils/api';
import { loginAs } from './utils/auth';

/**
 * TEST: Membership account states (already has, expired)
 * TEST : Etats adhesion (deja active, expiree)
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

test.describe('Membership account states / Etats adhesion', () => {
  test('should show already-has and expired / doit montrer deja actif et expire', async ({ page, request }) => {
    const randomId = generateRandomId();
    const userEmail = `jturbeaux+state${randomId}@pm.me`;

    const limitedProductName = `Adhesion Limited ${randomId}`;
    const limitedPriceName = 'Tarif Limited';

    const expiredProductName = `Adhesion Expired ${randomId}`;
    const expiredPriceName = 'Tarif Expired';

    let limitedProductUuid = '';

    await test.step('Create limited membership product / Creer produit limite', async () => {
      const productResponse = await createProduct({
        request,
        name: limitedProductName,
        description: 'Produit adhesion limite.',
        category: 'Membership',
        productMaxPerUser: 1,
        offers: [{ name: limitedPriceName, price: '10.00' }],
      });
      if (!productResponse.ok) {
        throw new Error(`createProduct failed: ${productResponse.status} ${productResponse.errorText}`);
      }
      limitedProductUuid = productResponse.uuid;
      const priceUuid = productResponse.offers?.find((offer: any) => offer.name === limitedPriceName)?.identifier || '';
      if (!priceUuid) {
        throw new Error('Price UUID missing for limited product');
      }
      const validUntil = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString();
      const membership = await createMembershipApi({
        request,
        priceUuid,
        email: userEmail,
        paymentMode: 'FREE',
        validUntil,
      });
      expect(membership.ok).toBeTruthy();
    });

    await test.step('Login user / Connecter utilisateur', async () => {
      await loginAs(page, userEmail);
    });

    await test.step('Already has membership message / Message deja actif', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('domcontentloaded');
      const openButton = page.locator(`[data-testid="membership-open-${limitedProductUuid}"], button[hx-get="/memberships/${limitedProductUuid}/"]`).first();
      await openButton.click();
      const alreadyContent = page.locator('#membership-already-has-content').first();
      await expect(alreadyContent).toBeVisible();
      await expect(alreadyContent).toContainText('Adhésion déjà active');
    });

    await test.step('Create expired membership / Creer adhesion expiree', async () => {
      const expiredProductResponse = await createProduct({
        request,
        name: expiredProductName,
        description: 'Produit adhesion expiree.',
        category: 'Membership',
        offers: [{ name: expiredPriceName, price: '5.00' }],
      });
      if (!expiredProductResponse.ok) {
        throw new Error(`createProduct failed: ${expiredProductResponse.status} ${expiredProductResponse.errorText}`);
      }
      const expiredPriceUuid = expiredProductResponse.offers?.find((offer: any) => offer.name === expiredPriceName)?.identifier || '';
      if (!expiredPriceUuid) {
        throw new Error('Price UUID missing for expired product');
      }
      const expiredUntil = new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString();
      const expiredMembership = await createMembershipApi({
        request,
        priceUuid: expiredPriceUuid,
        email: userEmail,
        paymentMode: 'FREE',
        validUntil: expiredUntil,
      });
      expect(expiredMembership.ok).toBeTruthy();
    });

    await test.step('Expired card shows renew / Carte expiree montre renouveler', async () => {
      await page.goto('/my_account/membership/');
      await page.waitForLoadState('domcontentloaded');
      const content = await page.textContent('body');
      expect(content || '').toContain('Expired');
      await expect(page.locator('a:has-text("Renew")').first()).toBeVisible();
    });
  });
});
