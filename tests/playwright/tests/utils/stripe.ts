import { Page, expect } from '@playwright/test';

/**
 * Stripe form helper
 * Helper pour le paiement Stripe
 */
export async function fillStripeCard(page: Page, email: string) {
  const emailInput = page.locator('input#email, input[name="email"]').first();
  if (await emailInput.isVisible()) {
    await emailInput.fill(email);
  }

  const roleCardNumber = page.getByRole('textbox', { name: /card number/i }).first();
  try {
    await roleCardNumber.waitFor({ state: 'visible', timeout: 5000 });
    await roleCardNumber.fill('4242424242424242');
    const roleExpiry = page.getByRole('textbox', { name: /expiration/i }).first();
    await roleExpiry.fill('12/42');
    const roleCvc = page.getByRole('textbox', { name: /cvc/i }).first();
    await roleCvc.fill('424');
    const roleName = page.getByRole('textbox', { name: /cardholder name/i }).first();
    if (await roleName.isVisible()) {
      await roleName.fill('Douglas Adams');
    }
    return;
  } catch {
    // Fallback below
  }

  const directCardNumber = page.locator('input#cardNumber').first();
  if (await directCardNumber.isVisible()) {
    await page.locator('input#cardNumber').fill('4242424242424242');
    await page.locator('input#cardExpiry').fill('12/42');
    await page.locator('input#cardCvc').fill('424');
    const billingName = page.locator('input#billingName').first();
    if (await billingName.isVisible()) {
      await billingName.fill('Douglas Adams');
    }
    return;
  }

  const fallbackNumber = page.locator('input[name="cardnumber"], input[placeholder*="1234"]').first();
  if (await fallbackNumber.isVisible()) {
    await fallbackNumber.fill('4242424242424242');
    const fallbackExpiry = page.locator('input[name="exp-date"], input[placeholder*="MM"]').first();
    if (await fallbackExpiry.isVisible()) {
      await fallbackExpiry.fill('12/42');
    }
    const fallbackCvc = page.locator('input[name="cvc"], input[placeholder*="CVC"]').first();
    if (await fallbackCvc.isVisible()) {
      await fallbackCvc.fill('424');
    }
    const billingName = page.locator('input#billingName, input[placeholder*="Full name"]').first();
    if (await billingName.isVisible()) {
      await billingName.fill('Douglas Adams');
    }
    return;
  }

  const iframeHandles = await page.locator('iframe').elementHandles();
  for (const iframeHandle of iframeHandles) {
    const frame = await iframeHandle.contentFrame();
    if (!frame) {
      continue;
    }
    const numberInput = frame.locator('input[name="cardnumber"], input[placeholder*="1234"]').first();
    if (await numberInput.count() > 0) {
      await numberInput.fill('4242424242424242');
    }
    const expInput = frame.locator('input[name="exp-date"], input[placeholder*="MM"]').first();
    if (await expInput.count() > 0) {
      await expInput.fill('12/42');
    }
    const cvcInput = frame.locator('input[name="cvc"], input[placeholder*="CVC"]').first();
    if (await cvcInput.count() > 0) {
      await cvcInput.fill('424');
    }
  }

  const submitButton = page.locator('button[type="submit"]').first();
  await expect(submitButton).toBeEnabled({ timeout: 20000 });
}
