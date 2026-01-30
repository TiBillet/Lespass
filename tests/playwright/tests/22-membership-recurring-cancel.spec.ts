import { test, expect } from '@playwright/test';
import { createProduct, createMembershipApi } from './utils/api';
import { loginAs } from './utils/auth';

/**
 * TEST: Recurring membership cancel flow (UI)
 * TEST : Annulation recurrente (UI)
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

test.describe('Recurring cancel / Annulation recurrente', () => {
  test('should show cancel button and handle error / doit montrer bouton et erreur', async ({ page, request }) => {
    const randomId = generateRandomId();
    const userEmail = `jturbeaux+auto${randomId}@pm.me`;

    const productName = `Adhesion Auto ${randomId}`;
    const priceName = 'Mensuelle';

    let priceUuid = '';

    await test.step('Create recurring membership product / Creer produit recurrent', async () => {
      const productResponse = await createProduct({
        request,
        name: productName,
        description: 'Produit adhesion recurrente.',
        category: 'Membership',
        offers: [{
          name: priceName,
          price: '10.00',
          recurringPayment: true,
          subscriptionType: 'M',
        }],
      });
      expect(productResponse.ok).toBeTruthy();
      priceUuid = productResponse.offers?.find((offer: any) => offer.name === priceName)?.identifier || '';
      if (!priceUuid) {
        throw new Error('Price UUID missing for recurring product');
      }
    });

    await test.step('Create AUTO membership via API / Creer adhesion AUTO via API', async () => {
      const validUntil = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString();
      const membership = await createMembershipApi({
        request,
        priceUuid,
        email: userEmail,
        paymentMode: 'FREE',
        validUntil,
        status: 'A',
        stripeSubscriptionId: 'sub_test_00000000',
      });
      expect(membership.ok).toBeTruthy();
    });

    await test.step('Login user / Connecter utilisateur', async () => {
      await loginAs(page, userEmail);
    });

    await test.step('Cancel button visible / Bouton annuler visible', async () => {
      await page.goto('/my_account/membership/');
      await page.waitForLoadState('domcontentloaded');
      const cancelButton = page.locator('[data-testid^="membership-cancel-auto-"]').first();
      await expect(cancelButton).toBeVisible();
    });

    await test.step('Cancel shows error message / Annulation montre erreur', async () => {
      const cancelButton = page.locator('[data-testid^="membership-cancel-auto-"]').first();
      await cancelButton.click();
      const errorAlert = page.locator('.alert-danger, .alert-warning').first();
      await expect(errorAlert).toBeVisible();
    });
  });
});
