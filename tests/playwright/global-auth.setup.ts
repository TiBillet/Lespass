/**
 * Global Auth Setup — Sauvegarde le state de session admin pour eviter les re-logins.
 * / Saves admin session state to avoid repeated logins.
 *
 * Usage dans playwright.config.ts :
 *   - Ajouter un projet "auth-setup" qui depend de rien
 *   - Les projets de test dependent de "auth-setup"
 *   - Les tests admin utilisent storageState: '.auth/admin.json'
 *
 * Voir tests/PLAN_TEST.md section 6.2 pour le detail.
 *
 * NOTE: Ce fichier n'est PAS encore branche dans la config.
 * Pour l'activer, modifier playwright.config.ts :
 *
 *   projects: [
 *     { name: 'auth-setup', testMatch: /global-auth\.setup\.ts/ },
 *     {
 *       name: 'chromium',
 *       dependencies: ['auth-setup'],
 *       use: {
 *         ...devices['Desktop Chrome'],
 *         storageState: '.auth/admin.json',
 *       },
 *     },
 *   ]
 */

import { test as setup, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const AUTH_DIR = path.resolve(__dirname, '.auth');
const ADMIN_STATE_PATH = path.join(AUTH_DIR, 'admin.json');

setup('authenticate as admin', async ({ page }) => {
  // Creer le dossier .auth s'il n'existe pas
  // / Create .auth directory if it doesn't exist
  if (!fs.existsSync(AUTH_DIR)) {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
  }

  const adminEmail = process.env.ADMIN_EMAIL;
  if (!adminEmail) {
    throw new Error('ADMIN_EMAIL environment variable is not set');
  }

  // 1. Aller sur la page d'accueil / Navigate to home
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  // 2. Ouvrir le panneau de login / Open login panel
  const loginButton = page
    .locator('.navbar button:has-text("Log in"), .navbar button:has-text("Connexion")')
    .first();
  await loginButton.click();

  // 3. Remplir l'email admin / Fill admin email
  const emailInput = page.locator('#loginEmail');
  await emailInput.fill(adminEmail);

  // 4. Soumettre le formulaire / Submit form
  const submitButton = page.locator('#loginForm button[type="submit"]');
  await submitButton.click();

  // 5. Cliquer sur le lien magic (mode test) / Click magic link (test mode)
  const testModeLink = page.locator('a:has-text("TEST MODE")');
  await expect(testModeLink).toBeVisible({ timeout: 10000 });
  await testModeLink.click();
  await page.waitForLoadState('networkidle');

  // 6. Verifier que le login a fonctionne / Verify login worked
  const accountResponse = await page.request.get('/my_account/');
  expect(accountResponse.ok()).toBeTruthy();

  // 7. Sauvegarder le state de session / Save session state
  await page.context().storageState({ path: ADMIN_STATE_PATH });
  console.log(`✓ Admin session saved to ${ADMIN_STATE_PATH}`);
});
