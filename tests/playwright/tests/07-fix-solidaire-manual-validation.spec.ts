import { test, Page } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';

/**
 * TEST: Enable Manual Validation for Solidaire Price
 * TEST : Activer la validation manuelle pour le tarif Solidaire
 */

test.describe('Manual Validation Fix / Correctif Validation Manuelle', () => {
  test('Enable manual_validation for Solidaire', async ({ page }) => {
    await test.step('Login', async () => { await loginAsAdmin(page); });

    await test.step('Find product', async () => {
      await page.goto('/admin/BaseBillet/product/');
      await page.waitForLoadState('networkidle');
      const productLink = page.locator('#result_list a, .result-list a').filter({ hasText: /validation sélective|validation selective/i }).first();
      if (await productLink.count() === 0) {
        console.log('⚠ Product not found, skipping');
        test.skip();
      }
      await productLink.click();
      await page.waitForLoadState('networkidle');
    });

    await test.step('Edit Solidaire price', async () => {
      const solidaireRow = page.locator('tr:has-text("Solidaire")').first();
      if (await solidaireRow.count() === 0) {
        console.log('⚠ Solidaire price row not found');
        test.skip();
      }
      const editLink = solidaireRow.locator('a[href*="/change/"]').first();
      await editLink.click();
      await page.waitForLoadState('networkidle');
    });

    await test.step('Enable checkbox', async () => {
      const checkbox = page.locator('input[name="manual_validation"]');
      if (await checkbox.count() > 0) {
        if (!await checkbox.isChecked()) {
          await checkbox.check();
          console.log('✓ manual_validation enabled');
        }
      }
    });

    await test.step('Save', async () => {
      await page.locator('button[type="submit"]:has-text("Save"), input[type="submit"]').first().click();
      await page.waitForLoadState('networkidle');
      console.log('✓ Price saved');
    });
  });
});
