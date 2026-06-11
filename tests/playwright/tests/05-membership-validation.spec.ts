import { test, expect, Page } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';

/**
 * TEST: Create Membership Product 3 - Adhésion à validation sélective
 * TEST : Créer le produit d'adhésion 3 - Adhésion à validation sélective
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

test.describe('Create Selective Validation Membership / Créer Adhésion à Validation Sélective', () => {
  test('Create Adhésion à validation sélective with 2 prices', async ({ page }) => {
    await test.step('Login', async () => { await loginAsAdmin(page); });

    await test.step('Open form', async () => {
      // L'admin produit a ete refondu en proxys : les adhesions se creent via
      // /admin/BaseBillet/membershipproduct/ (la categorie est fixee par le proxy).
      // / Product admin was split into proxies: memberships are created via
      // the membershipproduct proxy (category is set by the proxy itself).
      await page.goto('/admin/BaseBillet/membershipproduct/');
      await page.waitForLoadState('networkidle');
      const productLink = page.locator('#result_list a, .result-list a').filter({ hasText: 'Adhésion à validation sélective (Le Tiers-Lustre)' }).first();
      if (await productLink.count() > 0) {
        await productLink.click();
      } else {
        await page.goto('/admin/BaseBillet/membershipproduct/add/');
      }
      await page.waitForLoadState('networkidle');
    });

    await test.step('Fill basic info', async () => {
      await page.locator('input[name="name"]').fill('Adhésion à validation sélective (Le Tiers-Lustre)');
      // Pas de selection de categorie : le proxy MembershipProduct la fixe (champ cache).
      // / No category selection: the MembershipProduct proxy sets it (hidden field).
      await page.locator('input[name="short_description"]').first().fill('Tarif solidaire soumis à validation manuelle');
    });

    await test.step('Add prices', async () => {
      await addInlinePrice(page, { name: 'Solidaire', prix: 2, subscription_type: 'Y' });
      await addInlinePrice(page, { name: 'Plein tarif', prix: 30, subscription_type: 'Y' });
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
      expect(content.includes('validation sélective') || content.includes('validation selective')).toBeTruthy();
    });
  });
});
