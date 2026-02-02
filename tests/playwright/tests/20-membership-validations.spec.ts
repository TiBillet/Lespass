import { test, expect } from '@playwright/test';
import { createProduct } from './utils/api';

/**
 * TEST: Membership validations (form errors)
 * TEST : Validations adhesion (erreurs de formulaire)
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

function slugifyName(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

test.describe('Membership validations / Validations adhesion', () => {
  test('should show membership form errors / doit montrer les erreurs', async ({ page }) => {
    const randomId = generateRandomId();
    const productName = `Adhesion Validation ${randomId}`;
    const priceName = 'Tarif Libre';
    const userEmail = `jturbeaux+adh${randomId}@pm.me`;

    const booleanLabel = 'Consent';
    const multiSelectLabel = 'Topics';
    const booleanFieldName = slugifyName(booleanLabel);
    const multiSelectFieldName = slugifyName(multiSelectLabel);

    let productUuid = '';

    await test.step('Create membership product / Creer produit adhesion', async () => {
      const productResponse = await createProduct({
        request: page.request,
        name: productName,
        description: 'Produit pour validations adhesion.',
        category: 'Membership',
        offers: [
          {
            name: priceName,
            price: '10.00',
            freePrice: true,
          },
        ],
        formFields: [
          { label: booleanLabel, fieldType: 'boolean', required: true, order: 1 },
          { label: multiSelectLabel, fieldType: 'multiSelect', options: ['A', 'B'], required: true, order: 2 },
        ],
      });
      expect(productResponse.ok).toBeTruthy();
      productUuid = productResponse.uuid;
    });

    await test.step('Open membership form / Ouvrir le formulaire', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('domcontentloaded');
      const openButton = page.locator(`[data-testid="membership-open-${productUuid}"], button[hx-get="/memberships/${productUuid}/"]`).first();
      await openButton.click();
      const membershipForm = page.locator('[data-testid="membership-form"], #membership-form').first();
      await expect(membershipForm).toBeVisible();
    });

    await test.step('Check required fields / Verifier les champs requis', async () => {
      const emailInput = page.locator('[data-testid="membership-email"], #membership-email, input[name="email"]').first();
      const confirmInput = page.locator('[data-testid="membership-email-confirm"], #confirm-email').first();
      const firstNameInput = page.locator('[data-testid="membership-firstname"], input[name="firstname"]').first();
      const lastNameInput = page.locator('[data-testid="membership-lastname"], input[name="lastname"]').first();
      const acknowledgeInput = page.locator('[data-testid="membership-acknowledge"], #acknowledge').first();
      await expect(emailInput).toHaveAttribute('required', '');
      await expect(confirmInput).toHaveAttribute('required', '');
      await expect(firstNameInput).toHaveAttribute('required', '');
      await expect(lastNameInput).toHaveAttribute('required', '');
      if (await acknowledgeInput.isVisible()) {
        await expect(acknowledgeInput).toHaveAttribute('required', '');
      }
    });

    await test.step('Email mismatch error / Erreur email different', async () => {
      const emailInput = page.locator('[data-testid="membership-email"], #membership-email').first();
      const confirmInput = page.locator('[data-testid="membership-email-confirm"], #confirm-email').first();
      const submitButton = page.locator('[data-testid="membership-submit"], #membership-submit').first();
      const firstNameInput = page.locator('[data-testid="membership-firstname"], input[name="firstname"]').first();
      const lastNameInput = page.locator('[data-testid="membership-lastname"], input[name="lastname"]').first();
      const acknowledgeInput = page.locator('[data-testid="membership-acknowledge"], #acknowledge').first();
      const booleanInput = page.locator(`[data-testid="membership-form-field-${booleanFieldName}"], input[name="form__${booleanFieldName}"]`).first();
      const multiSelectInput = page.locator(`[data-testid="membership-form-field-${multiSelectFieldName}"], input[name="form__${multiSelectFieldName}"]`).first();
      const customAmountInput = page.locator('input[name^="custom_amount_"]').first();
      await firstNameInput.fill('Test');
      await lastNameInput.fill('User');
      if (await acknowledgeInput.isVisible()) {
        await acknowledgeInput.check();
      }
      if (await customAmountInput.isVisible()) {
        await customAmountInput.fill('12');
      }
      if (await booleanInput.isVisible()) {
        await booleanInput.check();
      }
      if (await multiSelectInput.isVisible()) {
        await multiSelectInput.check();
      }
      await emailInput.fill(userEmail);
      await confirmInput.fill(`${userEmail}.bad`);
      await submitButton.click();
      const isValid = await confirmInput.evaluate((el) => (el as HTMLInputElement).validity.valid);
      expect(isValid).toBeFalsy();
      const message = await confirmInput.evaluate((el) => (el as HTMLInputElement).validationMessage);
      expect(message || '').toContain('Email');
    });

    await test.step('Free price needs amount / Prix libre demande un montant', async () => {
      const confirmInput = page.locator('[data-testid="membership-email-confirm"], #confirm-email').first();
      const submitButton = page.locator('[data-testid="membership-submit"], #membership-submit').first();
      await confirmInput.fill(userEmail);
      const customAmountInput = page.locator('input[name^="custom_amount_"]').first();
      if (await customAmountInput.isVisible()) {
        await customAmountInput.fill('');
      }
      await submitButton.click();
      const isValid = await customAmountInput.evaluate((el) => (el as HTMLInputElement).validity.valid);
      expect(isValid).toBeFalsy();
      await customAmountInput.fill('12');
    });

    await test.step('Dynamic required fields / Champs dynamiques requis', async () => {
      const submitButton = page.locator('[data-testid="membership-submit"], #membership-submit').first();
      const booleanInput = page.locator(`[data-testid="membership-form-field-${booleanFieldName}"], input[name="form__${booleanFieldName}"]`).first();
      const multiSelectInput = page.locator(`[data-testid="membership-form-field-${multiSelectFieldName}"], input[name="form__${multiSelectFieldName}"]`).first();
      if (await booleanInput.isVisible()) {
        await booleanInput.uncheck();
      }
      if (await multiSelectInput.isVisible()) {
        await multiSelectInput.uncheck();
      }
      await submitButton.click();
      const booleanError = page.locator(`[data-testid="membership-form-error-${booleanFieldName}"], [data-bl-error]`).first();
      const multiSelectError = page.locator(`[data-testid="membership-form-error-${multiSelectFieldName}"], [data-ms-error]`).first();
      await expect(booleanError).toBeVisible();
      await expect(multiSelectError).toBeVisible();
    });
  });
});
