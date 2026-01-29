import { test, expect, Page } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';

/**
 * TEST: Create Membership Product 4 - Panier AMAP
 * TEST : Créer le produit d'adhésion 4 - Panier AMAP
 */

async function addInlinePrice(page: Page, priceData: {
  name: string;
  prix: number;
  subscription_type: string;
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
  console.log(`✓ Added price / Tarif ajouté : ${priceData.name}`);
}

test.describe('Create AMAP Membership / Créer Adhésion AMAP', () => {
  test('Create Panier AMAP with 2 prices', async ({ page }) => {
    await test.step('Login', async () => { await loginAsAdmin(page); });

    await test.step('Open form', async () => {
      await page.goto('/admin/BaseBillet/product/');
      await page.waitForLoadState('networkidle');
      const productLink = page.locator('#result_list a, .result-list a').filter({ hasText: 'Panier AMAP (Le Tiers-Lustre)' }).first();
      if (await productLink.count() > 0) {
        await productLink.click();
      } else {
        await page.goto('/admin/BaseBillet/product/add/');
      }
      await page.waitForLoadState('networkidle');
    });

    await test.step('Fill basic info', async () => {
      await page.locator('input[name="name"]').fill('Panier AMAP (Le Tiers-Lustre)');
      await page.locator('select[name="categorie_article"]').selectOption('A');
      await page.locator('input[name="short_description"]').fill('Adhésion au panier de l\'AMAP partenaire Le Tiers-Lustre');
      
      const options = [
        { value: 'livraison_asso', label: "Livraison à l'asso" },
        { value: 'livraison_maison', label: "Livraison à la maison" }
      ];
      for (const opt of options) {
        const checkbox = page.locator(`input[value="${opt.value}"], input[value="${opt.label}"]`).first();
        if (await checkbox.count() > 0) { await checkbox.check(); }
      }
    });

    await test.step('Add prices', async () => {
      await addInlinePrice(page, { name: 'Annuelle', prix: 400, subscription_type: 'Y' });
      await addInlinePrice(page, { name: 'Mensuelle', prix: 40, subscription_type: 'M' });
    });

    await test.step('Save product', async () => {
      await page.locator('button[type="submit"]:has-text("Save"), input[type="submit"]').first().click();
      await page.waitForLoadState('networkidle');
      console.log('✓ Product saved / Produit enregistré');
    });

    await test.step('Verify', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('networkidle');
      const content = await page.content();
      expect(content.includes('AMAP') || content.includes('Panier')).toBeTruthy();
    });
  });
});
