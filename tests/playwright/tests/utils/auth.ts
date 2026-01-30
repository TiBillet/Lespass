import { Page, expect } from '@playwright/test';
import { env } from './env';

/**
 * AUTHENTICATION HELPER: Login as any user
 * AIDE À L'AUTHENTIFICATION : Se connecter avec n'importe quel utilisateur
 */
export async function loginAs(page: Page, email: string) {
  // 1. Navigate to home
  console.time('login:goto');
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  console.timeEnd('login:goto');
  
  // 2. Open the login panel
  const loginButton = page.locator('.navbar button:has-text("Log in"), .navbar button:has-text("Connexion")').first();
  console.time('login:open-panel');
  await loginButton.click();
  console.timeEnd('login:open-panel');
  
  // 3. Fill the email
  const emailInput = page.locator('#loginEmail');
  console.time('login:fill-email');
  await emailInput.fill(email);
  console.timeEnd('login:fill-email');
  
  // 4. Submit the form
  const submitButton = page.locator('#loginForm button[type="submit"]');
  console.time('login:submit');
  await submitButton.click();
  console.timeEnd('login:submit');
  
  // 5. In TEST mode, click the magic link
  if (env.TEST) {
    const testModeLink = page.locator('a:has-text("TEST MODE")');
    console.time('login:test-mode-visible');
    await expect(testModeLink).toBeVisible({ timeout: 10000 });
    console.timeEnd('login:test-mode-visible');
    console.time('login:test-mode-click');
    await testModeLink.click();
    await page.waitForLoadState('networkidle');
    console.timeEnd('login:test-mode-click');
  } else {
    console.time('login:wait-timeout');
    await page.waitForTimeout(2000);
    console.timeEnd('login:wait-timeout');
  }
  
  // 6. Verification (fast, API check)
  const accountResponse = await page.request.get('/my_account/');
  expect(accountResponse.ok()).toBeTruthy();
  console.log(`✓ Successfully authenticated as ${email} / Authentification réussie pour ${email}`);
}

/**
 * AUTHENTICATION HELPER: Login as administrator
 * AIDE À L'AUTHENTIFICATION : Se connecter en tant qu'administrateur
 */
export async function loginAsAdmin(page: Page) {
  return loginAs(page, env.ADMIN_EMAIL);
}
