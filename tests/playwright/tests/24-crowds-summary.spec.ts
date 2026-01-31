import { test, expect } from '@playwright/test';
import { env } from './utils/env';

/**
 * TEST: Crowds summary toggle on list page
 * TEST : Toggle du résumé crowds sur la page liste
 *
 * Objective / Objectif:
 * - Open the list summary and verify details area renders.
 * - Ouvrir le résumé et vérifier l'affichage des détails.
 */
test.describe('Crowds summary toggle / Toggle résumé crowds', () => {
  test('should expand summary details / doit afficher les détails du résumé', async ({ page }) => {
    // Step 1: Login as admin / Étape 1 : Connexion admin
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const loginButton = page.locator('.navbar button:has-text("Log in"), .navbar button:has-text("Connexion")').first();
    await expect(loginButton).toBeVisible();
    await loginButton.click();

    const emailInput = page.locator('#loginEmail');
    await emailInput.fill(env.ADMIN_EMAIL);

    const submitButton = page.locator('#loginForm button[type="submit"]');
    await submitButton.click();

    if (env.TEST) {
      const testModeLink = page.locator('a:has-text("TEST MODE")');
      await expect(testModeLink).toBeVisible({ timeout: 10000 });
      await testModeLink.click();
      await page.waitForLoadState('domcontentloaded');
    } else {
      await page.waitForTimeout(2000);
    }

    // Step 2: Go to the list page / Étape 2 : Aller sur la page liste
    await page.goto('/crowd/');
    await page.waitForLoadState('domcontentloaded');

    // Step 3: Check summary cards / Étape 3 : Vérifier les cartes du résumé
    await expect(page.locator('[data-testid="crowds-summary"]')).toBeVisible();
    await expect(page.locator('[data-testid="crowds-summary-card-contributors"]')).toBeVisible();
    await expect(page.locator('[data-testid="crowds-summary-card-projects"]')).toBeVisible();
    await expect(page.locator('[data-testid="crowds-summary-card-time"]')).toBeVisible();

    const sourcesCard = page.locator('[data-testid="crowds-summary-card-sources"]');
    if (await sourcesCard.count()) {
      await expect(sourcesCard).toBeVisible();
    }

    const rulesButton = page.locator('[data-testid="crowds-summary-rules-button"]');
    await expect(rulesButton).toBeVisible();
    await expect(rulesButton).toHaveAttribute('target', '_blank');

    const fundingCard = page.locator('[data-testid="crowds-summary-card-funding"]');
    await expect(fundingCard).toBeVisible();
    const allocButton = page.locator('[data-testid="crowds-summary-funding-allocate-button"]');
    if (await allocButton.count()) {
      await allocButton.click();
      const popup = page.locator('.swal2-popup');
      await expect(popup).toBeVisible();
      await expect(popup.locator('#alloc-amount')).toBeVisible();
      const projectButtons = popup.locator('button[data-uuid]');
      if (await projectButtons.count()) {
        await expect(projectButtons.first()).toBeVisible();
      } else {
        await expect(popup).toContainText('Aucun projet disponible');
      }
      const closeButton = popup.locator('.swal2-close');
      if (await closeButton.count()) {
        await closeButton.click();
      } else {
        await page.keyboard.press('Escape');
      }
    }

    const globalFundingButton = page.locator('[data-testid="crowds-summary-global-funding-button"]');
    if (await globalFundingButton.count()) {
      await globalFundingButton.click();
      const popup = page.locator('.swal2-popup');
      await expect(popup).toBeVisible();
      await expect(popup.locator('#contrib-name')).toBeVisible();
      await expect(popup.locator('#contrib-amt')).toBeVisible();
      await popup.locator('button:has-text("Annuler")').click();
    }

    // Step 4: Check toggle button / Étape 4 : Vérifier le bouton toggle
    const toggle = page.locator('[data-testid="crowds-summary-toggle-details"]');
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveText(/Voir plus de détail/);

    // Step 5: Expand details / Étape 5 : Ouvrir les détails
    await toggle.click();
    const details = page.locator('[data-testid="crowds-summary-details"]');
    await expect(details).toHaveClass(/show/);
    await expect(toggle).toHaveText(/Voir moins/);

    // Step 6: Check currency block / Étape 6 : Vérifier un bloc monnaie
    const currencyCards = details.locator('[data-testid="crowds-summary-currency-card"]');
    if (await currencyCards.count()) {
      await expect(currencyCards.first()).toBeVisible();
    }

    // Step 7: Check actions section / Étape 7 : Vérifier les actions en cours
    const actionsCard = details.locator('[data-testid="crowds-summary-actions-card"]');
    await expect(actionsCard).toBeVisible();
    const actionsGrid = details.locator('[data-testid="crowds-summary-actions-grid"]');
    const actionsEmpty = details.locator('text=Aucune action en cours');
    if (await actionsGrid.count()) {
      await expect(actionsGrid).toBeVisible();
    } else {
      await expect(actionsEmpty).toBeVisible();
    }
  });
});
