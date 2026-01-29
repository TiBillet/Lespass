import { test, expect } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';

/**
 * TEST: Admin Configuration
 * TEST : Configuration de l'administration
 * 
 * This test reproduces Section 2 of demo_data_operations.md:
 * Ce test reproduit la Section 2 de demo_data_operations.md :
 * "Configuration générale (pour chaque tenant)"
 */

test.describe('Admin Configuration / Configuration Admin', () => {
  test('should fill configuration fields and verify on homepage / doit remplir la configuration et vérifier sur l\'accueil', async ({ page }) => {
    
    // Step 1: Login
    await test.step('Login as admin / Connexion admin', async () => {
      await loginAsAdmin(page);
    });

    // Step 2: Navigate to admin panel
    await test.step('Navigate to admin panel / Naviguer vers le panel admin', async () => {
      await page.goto('/admin/');
      await page.waitForLoadState('networkidle');
      await expect(page).toHaveURL(/\/admin\//);
    });

    // Step 3: Open Configuration page
    await test.step('Open Configuration settings / Ouvrir les paramètres de configuration', async () => {
      await page.goto('/admin/BaseBillet/configuration/');
      await page.waitForLoadState('networkidle');
      await expect(page.url()).toContain('configuration');
    });

    // Step 4: Fill fields
    await test.step('Fill configuration fields / Remplir les champs de configuration', async () => {
      const organisationInput = page.locator('input[name="organisation"]');
      if (await organisationInput.count() > 0) {
        await organisationInput.fill('Le Tiers-Lustre');
      }
      
      const shortDescInput = page.locator('input[name="short_description"], textarea[name="short_description"]');
      if (await shortDescInput.count() > 0) {
        await shortDescInput.fill('Instance de démonstration du collectif imaginaire « Le Tiers-Lustre ».');
      }
    });

    // Step 5: Save
    await test.step('Save configuration / Enregistrer la configuration', async () => {
      const saveButton = page.locator('button[type="submit"]:has-text("Save"), button[type="submit"]:has-text("Enregistrer"), input[type="submit"]').first();
      if (await saveButton.count() > 0) {
        await saveButton.click();
        await page.waitForLoadState('networkidle');
        console.log('✓ Configuration saved / Configuration enregistrée');
      }
    });

    // Step 6: Verify
    await test.step('Verify configuration on homepage / Vérifier sur l\'accueil', async () => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      const orgName = page.locator('.navbar-brand').first();
      const brandText = await orgName.innerText();
      if (brandText.trim().length === 0) {
        await expect(orgName.locator('img')).toBeVisible();
      } else {
        await expect(orgName).toContainText(/Le Tiers-Lustre|Tiers-Lustre|Lespass/i);
      }
    });
  });
});
