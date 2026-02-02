import { test, expect } from '@playwright/test';
import { createEvent, createProduct } from './utils/api';
import { createPromotionalCodeInDb } from './utils/setup';

/**
 * TEST: Reservation validations (form errors)
 * TEST : Validations de reservation (erreurs de formulaire)
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

test.describe('Reservation validations / Validations reservation', () => {
  test('should show form errors before payment / doit montrer les erreurs avant paiement', async ({ page }) => {
    const randomId = generateRandomId();
    const eventName = `E2E Reservation Validation ${randomId}`;
    const productName = `Billets Validation ${randomId}`;
    const priceName = 'Tarif Libre Test';
    const promoCode = `PROMO-${randomId}`;
    const userEmail = `jturbeaux+resa${randomId}@pm.me`;
    const startDate = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();

    const booleanLabel = 'Consent';
    const multiSelectLabel = 'Topics';
    const booleanFieldName = slugifyName(booleanLabel);
    const multiSelectFieldName = slugifyName(multiSelectLabel);

    let eventSlug = slugifyName(eventName);

    await test.step('Create event and product / Creer event et produit', async () => {
      const eventResponse = await createEvent({
        request: page.request,
        name: eventName,
        startDate,
        optionsRadio: ['Option Radio A'],
        optionsCheckbox: ['Option Check A'],
      });
      expect(eventResponse.ok).toBeTruthy();
      eventSlug = eventResponse.slug || eventSlug;

      const productResponse = await createProduct({
        request: page.request,
        name: productName,
        description: 'Produit pour valider les erreurs de formulaire.',
        category: 'Ticket booking',
        eventUuid: eventResponse.uuid,
        offers: [
          {
            name: priceName,
            price: '5.00',
            freePrice: true,
          },
        ],
        formFields: [
          { label: booleanLabel, fieldType: 'boolean', required: true, order: 1 },
          { label: multiSelectLabel, fieldType: 'multiSelect', options: ['A', 'B'], required: true, order: 2 },
        ],
      });
      expect(productResponse.ok).toBeTruthy();
    });

    await test.step('Create promo code / Creer un code promo', async () => {
      const result = createPromotionalCodeInDb({
        product: productName,
        codeName: promoCode,
        discountRate: 10,
      });
      expect(result.status).toBe('success');
    });

    await test.step('Open booking form / Ouvrir le formulaire', async () => {
      await page.goto(`/event/${eventSlug}/`);
      await page.waitForLoadState('domcontentloaded');
      const openButton = page.locator('[data-testid="booking-open-panel"], button:has-text("book one or more seats"), button:has-text("réserver")').first();
      await openButton.click();
      await page.waitForSelector('#bookingPanel.show, .offcanvas.show', { state: 'visible' });
      const bookingForm = page.locator('[data-testid="booking-form"], #reservation_form').first();
      await expect(bookingForm).toBeVisible();
    });

    await test.step('Check required fields / Verifier les champs requis', async () => {
      const emailInput = page.locator('[data-testid="booking-email"], #booking-email').first();
      const confirmInput = page.locator('[data-testid="booking-email-confirm"], #booking-confirm').first();
      await expect(emailInput).toHaveAttribute('required', '');
      await expect(confirmInput).toHaveAttribute('required', '');
    });

    await test.step('Email mismatch error / Erreur email different', async () => {
      const emailInput = page.locator('[data-testid="booking-email"], #booking-email').first();
      const confirmInput = page.locator('[data-testid="booking-email-confirm"], #booking-confirm').first();
      const submitButton = page.locator('[data-testid="booking-submit"], #bookingPanel button[type="submit"]').first();
      const booleanInput = page.locator(`[data-testid="booking-form-field-${booleanFieldName}"], input[name="form__${booleanFieldName}"]`).first();
      const priceBlock = page.locator('[data-testid^="booking-price-"], .js-order').filter({ hasText: priceName }).first();
      const optionRadio = page.locator('[data-testid^="booking-option-radio-"]').first();
      const optionCheckbox = page.locator('[data-testid^="booking-option-checkbox-"]').first();
      const multiSelectInput = page.locator(`[data-testid="booking-form-field-${multiSelectFieldName}"], input[name="form__${multiSelectFieldName}"]`).first();
      await emailInput.fill(userEmail);
      await confirmInput.fill(`${userEmail}.bad`);
      if (await booleanInput.isVisible()) {
        await booleanInput.check();
      }
      await priceBlock.evaluate((block) => {
        const counter = block.querySelector('bs-counter');
        if (counter) {
          (counter as any).value = 1;
          counter.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });
      const customAmountInput = priceBlock.locator('input[name^="custom_amount_"]').first();
      if (await customAmountInput.isVisible()) {
        await customAmountInput.fill('7');
      }
      if (await optionRadio.isVisible()) {
        await optionRadio.check();
      }
      if (await optionCheckbox.isVisible()) {
        await optionCheckbox.check();
      }
      if (await multiSelectInput.isVisible()) {
        await multiSelectInput.check();
      }
      await submitButton.click();
      const isValid = await confirmInput.evaluate((el) => (el as HTMLInputElement).validity.valid);
      expect(isValid).toBeFalsy();
      const message = await confirmInput.evaluate((el) => (el as HTMLInputElement).validationMessage);
      expect(message || '').toContain('emails');
      if (await booleanInput.isVisible()) {
        await booleanInput.uncheck();
      }
    });

    await test.step('No ticket error / Erreur sans billet', async () => {
      const confirmInput = page.locator('[data-testid="booking-email-confirm"], #booking-confirm').first();
      const submitButton = page.locator('[data-testid="booking-submit"], #bookingPanel button[type="submit"]').first();
      const booleanInput = page.locator(`[data-testid="booking-form-field-${booleanFieldName}"], input[name="form__${booleanFieldName}"]`).first();
      const optionRadio = page.locator('[data-testid^="booking-option-radio-"]').first();
      const optionCheckbox = page.locator('[data-testid^="booking-option-checkbox-"]').first();
      const multiSelectInput = page.locator(`[data-testid="booking-form-field-${multiSelectFieldName}"], input[name="form__${multiSelectFieldName}"]`).first();
      await page.evaluate(() => {
        document.querySelectorAll('bs-counter').forEach((counter) => {
          (counter as any).value = 0;
          counter.dispatchEvent(new CustomEvent('bs-counter:update', { bubbles: true }));
        });
      });
      await confirmInput.fill(userEmail);
      if (await booleanInput.isVisible()) {
        await booleanInput.check();
      }
      if (await optionRadio.isVisible()) {
        await optionRadio.check();
      }
      if (await optionCheckbox.isVisible()) {
        await optionCheckbox.check();
      }
      if (await multiSelectInput.isVisible()) {
        await multiSelectInput.check();
      }
      await submitButton.click();
      const noTicketError = page.locator('[data-testid="booking-no-ticket-error"], #booking-form-error').first();
      await expect(noTicketError).toBeVisible();
    });

    await test.step('Free price needs amount / Prix libre demande un montant', async () => {
      const priceBlock = page.locator('[data-testid^="booking-price-"], .js-order').filter({ hasText: priceName }).first();
      await priceBlock.evaluate((block) => {
        const counter = block.querySelector('bs-counter');
        if (counter) {
          (counter as any).value = 1;
          counter.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });

      const customAmountInput = priceBlock.locator('input[name^="custom_amount_"]').first();
      await expect(customAmountInput).toHaveAttribute('min', '5.00');
      await expect(customAmountInput).toHaveAttribute('required', '');
      await customAmountInput.fill('7');
    });

    await test.step('Dynamic required fields / Champs dynamiques requis', async () => {
      const submitButton = page.locator('[data-testid="booking-submit"], #bookingPanel button[type="submit"]').first();
      const booleanInput = page.locator(`[data-testid="booking-form-field-${booleanFieldName}"], input[name="form__${booleanFieldName}"]`).first();
      const multiSelectInput = page.locator(`[data-testid="booking-form-field-${multiSelectFieldName}"], input[name="form__${multiSelectFieldName}"]`).first();
      if (await booleanInput.isVisible()) {
        await booleanInput.uncheck();
      }
      if (await multiSelectInput.isVisible()) {
        await multiSelectInput.uncheck();
      }
      await submitButton.click();
      const booleanError = page.locator(`[data-testid="booking-form-error-${booleanFieldName}"], [data-bl-error]`).first();
      const multiSelectError = page.locator(`[data-testid="booking-form-error-${multiSelectFieldName}"], [data-ms-error]`).first();
      await expect(booleanError).toBeVisible();
      await expect(multiSelectError).toBeVisible();
    });

    await test.step('Promo code input visible / Champ code promo visible', async () => {
      const promoInput = page.locator('[data-testid="booking-promo-code"], #promotional-code').first();
      await expect(promoInput).toBeVisible();
    });
  });
});
