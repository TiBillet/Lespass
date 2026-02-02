import { test, expect, Page } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';

/**
 * TEST: Create Membership Product 1 - Adhésion (Le Tiers-Lustre)
 * TEST : Créer le produit d'adhésion 1 - Adhésion (Le Tiers-Lustre)
 */

async function addInlinePrice(page: Page, priceData: {
  name: string;
  prix: number;
  subscription_type: string;
  free_price?: boolean;
}) {
  const countBefore = await page.locator('input[name*="prices-"][name$="-name"]:not([name*="__prefix__"])').count();
  const addButtons = await page.locator('a:has-text("Add another"), button:has-text("Add another")').all();
  if (addButtons.length > 0) {
    await addButtons[0].click();
    await page.waitForTimeout(500);
  }
  const formIndex = countBefore;
  await page.locator(`input[name="prices-${formIndex}-name"]`).fill(priceData.name);
  await page.locator(`input[name="prices-${formIndex}-prix"]`).fill(priceData.prix.toString());
  await page.locator(`select[name="prices-${formIndex}-subscription_type"]`).selectOption(priceData.subscription_type);
  if (priceData.free_price) {
    await page.locator(`input[name="prices-${formIndex}-free_price"]`).check();
  }
  console.log(`✓ Added price / Tarif ajouté : ${priceData.name}`);
}

test.describe('Create Membership Product / Créer le produit d\'adhésion', () => {
  test('Create Product 1: Adhésion (Le Tiers-Lustre)', async ({ page }) => {
    await test.step('Login', async () => { await loginAsAdmin(page); });

    await test.step('Navigate or Edit', async () => {
      await page.goto('/admin/BaseBillet/product/');
      await page.waitForLoadState('networkidle');
      const productLink = page.locator('#result_list a, .result-list a').filter({ hasText: 'Adhésion (Le Tiers-Lustre)' }).first();
      if (await productLink.count() > 0) {
        await productLink.click();
      } else {
        await page.goto('/admin/BaseBillet/product/add/');
      }
      await page.waitForLoadState('networkidle');
    });

    await test.step('Fill info', async () => {
      await page.locator('input[name="name"]').fill('Adhésion (Le Tiers-Lustre)');
      await page.locator('input[name="short_description"]').first().fill('Adhérez au collectif Le Tiers-Lustre');
      await page.locator('select[name="categorie_article"]').selectOption('A');
    });

    await test.step('Add prices', async () => {
      await addInlinePrice(page, { name: 'Annuelle', prix: 20, subscription_type: 'Y' });
      await addInlinePrice(page, { name: 'Mensuelle', prix: 2, subscription_type: 'M' });
    });

    await test.step('Save', async () => {
      await page.locator('button[type="submit"]:has-text("Save"), input[type="submit"]').first().click();
      await page.waitForLoadState('networkidle');
      console.log('✓ Product saved / Produit enregistré');
    });

    await test.step('Verify', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('networkidle');
      const content = await page.content();
      expect(content.includes('Adhésion') && content.includes('Tiers-Lustre')).toBeTruthy();
    });
  });
});
