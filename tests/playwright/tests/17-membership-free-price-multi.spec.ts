import { test, expect } from '@playwright/test';

/**
 * TEST: Membership Multi Free Price
 * TEST : Adhésion multi prix libre
 * 
 * Objectives:
 * 1. Simple free price membership -> check Stripe.
 * 2. Multi free price membership -> check Stripe.
 * 3. Change choice from Price 1 to Price 2 -> check Stripe (should be Price 2).
 * 4. Change choice from Price 2 to Price 1 -> check Stripe (should be Price 1).
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

test.describe('Membership Multi Free Price / Adhésion multi prix libre', () => {

  test('Scenario 1: Simple free price / Prix libre simple', async ({ page }) => {
    const userEmail = `jturbeaux+multi1${generateRandomId()}@pm.me`;
    const amount = "12";
    
    await page.goto('/memberships/');
    await page.waitForLoadState('domcontentloaded');
    
    // Select the product created by setup_test_data.py
    const card = page.locator('.card:has-text("Adhésion Multi-Prix Libre")').first();
    await card.locator('button:has-text("Subscribe"), button:has-text("Adhérer")').click();
    await page.waitForSelector('#subscribePanel.show', { state: 'visible' });

    await page.locator('#subscribePanel input[name="email"]').fill(userEmail);
    await page.locator('#subscribePanel input[name="confirm-email"]').fill(userEmail);
    await page.locator('#subscribePanel input[name="firstname"]').fill('Multi');
    await page.locator('#subscribePanel input[name="lastname"]').fill('One');

    // Select "Prix Libre 1"
    const price1Label = page.locator('label:has-text("Prix Libre 1")').first();
    await price1Label.click();
    
    // Fill amount in the specific container for Price 1
    const container1 = page.locator('div:has(label:has-text("Prix Libre 1")) + .custom-amount-container');
    await container1.locator('input[type="number"]').fill(amount);

    await page.locator('#membership-submit').click();
    
    // Wait for Stripe redirection
    await page.waitForURL(/checkout.stripe.com/, { timeout: 40000 });
    
    // Verify amount on Stripe
    const priceRegex = new RegExp(`${amount}[.,]00`);
    await expect(page.locator('body')).toContainText(priceRegex, { timeout: 20000 });
    console.log(`✓ Scenario 1 OK: Stripe shows ${amount}€`);
  });

  test('Scenario 2: Select second free price / Sélection du deuxième prix libre', async ({ page }) => {
    const userEmail = `jturbeaux+multi2${generateRandomId()}@pm.me`;
    const amount = "18";
    
    await page.goto('/memberships/');
    await page.waitForLoadState('domcontentloaded');
    
    const card = page.locator('.card:has-text("Adhésion Multi-Prix Libre")').first();
    await card.locator('button:has-text("Subscribe"), button:has-text("Adhérer")').click();
    await page.waitForSelector('#subscribePanel.show', { state: 'visible' });

    await page.locator('#subscribePanel input[name="email"]').fill(userEmail);
    await page.locator('#subscribePanel input[name="confirm-email"]').fill(userEmail);
    await page.locator('#subscribePanel input[name="firstname"]').fill('Multi');
    await page.locator('#subscribePanel input[name="lastname"]').fill('Two');

    // Select "Prix Libre 2"
    const price2Label = page.locator('label:has-text("Prix Libre 2")').first();
    await price2Label.click();
    
    // Fill amount in the specific container for Price 2
    const container2 = page.locator('div:has(label:has-text("Prix Libre 2")) + .custom-amount-container');
    await container2.locator('input[type="number"]').fill(amount);

    await page.locator('#membership-submit').click();
    
    // Wait for Stripe redirection
    await page.waitForURL(/checkout.stripe.com/, { timeout: 40000 });
    
    // Verify amount on Stripe
    const priceRegex = new RegExp(`${amount}[.,]00`);
    await expect(page.locator('body')).toContainText(priceRegex, { timeout: 20000 });
    console.log(`✓ Scenario 2 OK: Stripe shows ${amount}€`);
  });

  test('Scenario 3: Change from first to second free price / Changer du premier au second prix libre', async ({ page }) => {
    const userEmail = `jturbeaux+multi3${generateRandomId()}@pm.me`;
    const amount1 = "13";
    const amount2 = "22";
    
    await page.goto('/memberships/');
    await page.waitForLoadState('domcontentloaded');
    
    const card = page.locator('.card:has-text("Adhésion Multi-Prix Libre")').first();
    await card.locator('button:has-text("Subscribe"), button:has-text("Adhérer")').click();
    await page.waitForSelector('#subscribePanel.show', { state: 'visible' });

    await page.locator('#subscribePanel input[name="email"]').fill(userEmail);
    await page.locator('#subscribePanel input[name="confirm-email"]').fill(userEmail);
    await page.locator('#subscribePanel input[name="firstname"]').fill('Multi');
    await page.locator('#subscribePanel input[name="lastname"]').fill('Three');

    // 1. Select "Prix Libre 1" and fill amount1
    const price1Label = page.locator('label:has-text("Prix Libre 1")').first();
    await price1Label.click();
    const container1 = page.locator('div:has(label:has-text("Prix Libre 1")) + .custom-amount-container');
    const input1 = container1.locator('input[type="number"]');
    await input1.fill(amount1);

    // 2. Change to "Prix Libre 2" and fill amount2
    const price2Label = page.locator('label:has-text("Prix Libre 2")').first();
    await price2Label.click();
    const container2 = page.locator('div:has(label:has-text("Prix Libre 2")) + .custom-amount-container');
    const input2 = container2.locator('input[type="number"]');
    
    // VERIFY: input1 should be cleared by JS when switching radio
    await expect(input1).toHaveValue('');
    
    await input2.fill(amount2);

    await page.locator('#membership-submit').click();
    
    // Wait for Stripe redirection
    await page.waitForURL(/checkout.stripe.com/, { timeout: 40000 });
    
    // Verify amount on Stripe (should be amount2)
    const priceRegex = new RegExp(`${amount2}[.,]00`);
    await expect(page.locator('body')).toContainText(priceRegex, { timeout: 20000 });
    console.log(`✓ Scenario 3 OK: Stripe shows ${amount2}€ after change`);
  });

  test('Scenario 4: Change from second to first free price / Changer du second au premier prix libre', async ({ page }) => {
    const userEmail = `jturbeaux+multi4${generateRandomId()}@pm.me`;
    const amount1 = "14";
    const amount2 = "24";
    
    await page.goto('/memberships/');
    await page.waitForLoadState('domcontentloaded');
    
    const card = page.locator('.card:has-text("Adhésion Multi-Prix Libre")').first();
    await card.locator('button:has-text("Subscribe"), button:has-text("Adhérer")').click();
    await page.waitForSelector('#subscribePanel.show', { state: 'visible' });

    await page.locator('#subscribePanel input[name="email"]').fill(userEmail);
    await page.locator('#subscribePanel input[name="confirm-email"]').fill(userEmail);
    await page.locator('#subscribePanel input[name="firstname"]').fill('Multi');
    await page.locator('#subscribePanel input[name="lastname"]').fill('Four');

    // 1. Select "Prix Libre 2" and fill amount2
    const price2Label = page.locator('label:has-text("Prix Libre 2")').first();
    await price2Label.click();
    const container2 = page.locator('div:has(label:has-text("Prix Libre 2")) + .custom-amount-container');
    const input2 = container2.locator('input[type="number"]');
    await input2.fill(amount2);

    // 2. Change to "Prix Libre 1" and fill amount1
    const price1Label = page.locator('label:has-text("Prix Libre 1")').first();
    await price1Label.click();
    const container1 = page.locator('div:has(label:has-text("Prix Libre 1")) + .custom-amount-container');
    const input1 = container1.locator('input[type="number"]');
    
    // VERIFY: input2 should be cleared
    await expect(input2).toHaveValue('');
    
    await input1.fill(amount1);

    await page.locator('#membership-submit').click();
    
    // Wait for Stripe redirection
    await page.waitForURL(/checkout.stripe.com/, { timeout: 40000 });
    
    // Verify amount on Stripe (should be amount1)
    const priceRegex = new RegExp(`${amount1}[.,]00`);
    await expect(page.locator('body')).toContainText(priceRegex, { timeout: 20000 });
    console.log(`✓ Scenario 4 OK: Stripe shows ${amount1}€ after change`);
  });

});
