import { test, expect, Page } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';

/**
 * TEST: Product Duplication and Independence
 * TEST : Duplication de produit et indépendance
 *
 * Objectives / Objectifs:
 * 1. Create a product with multiple prices and form fields
 * 2. Duplicate it via admin
 * 3. Modify the duplicate
 * 4. Verify the original is unchanged
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

async function addInlinePrice(page: Page, priceData: {
  name: string;
  prix: number;
  subscription_type: string;
  prix_libre?: boolean;
  adhesion_obligatoire?: boolean;
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

  if (priceData.prix_libre) {
    const checkbox = page.locator(`input[name="prices-${formIndex}-prix_libre"]`);
    if (await checkbox.count() > 0) await checkbox.check();
  }

  if (priceData.adhesion_obligatoire) {
    const checkbox = page.locator(`input[name="prices-${formIndex}-adhesion_obligatoire"]`);
    if (await checkbox.count() > 0) await checkbox.check();
  }

  console.log(`✓ Added price: ${priceData.name}`);
}

async function addFormField(page: Page, fieldData: {
  label: string;
  type: string;
  required: boolean;
  help_text: string;
  order: number;
  options?: string;
}) {
  const section = page.locator('.inline-group').filter({ has: page.locator('h2:has-text("Dynamic form field")') });
  const addButton = section.locator('a:has-text("Add another")').first();

  await addButton.click();
  const lastRow = section.locator('tr.form-row:not(.empty-form)').last();
  await lastRow.waitFor({ state: 'visible', timeout: 5000 });

  await lastRow.locator('input[name*="-label"]').fill(fieldData.label);
  await lastRow.locator('select[name*="-field_type"]').selectOption(fieldData.type);

  if (fieldData.required) {
    await lastRow.locator('input[name*="-required"]').check();
  }

  await lastRow.locator('input[name*="-help_text"], textarea[name*="-help_text"]').fill(fieldData.help_text);
  await lastRow.locator('input[name*="-order"]').fill(fieldData.order.toString(), { force: true });

  if (fieldData.options) {
    const optionsTextarea = lastRow.locator('textarea[name*="-options"]');
    if (await optionsTextarea.count() > 0) {
      await optionsTextarea.fill(fieldData.options);
    }
  }

  console.log(`✓ Added form field: ${fieldData.label}`);
}

async function getPriceNames(page: Page): Promise<string[]> {
  const priceInputs = page.locator('input[name*="prices-"][name$="-name"]:not([name*="__prefix__"])');
  const count = await priceInputs.count();
  const names: string[] = [];
  for (let i = 0; i < count; i++) {
    const value = await priceInputs.nth(i).inputValue();
    if (value.trim()) names.push(value);
  }
  return names;
}

async function getFormFieldLabels(page: Page): Promise<string[]> {
  const tab = page.locator('button:has-text("Dynamic form field"), a:has-text("Dynamic form field")').first();
  if (await tab.count() > 0) {
    await tab.click();
    await page.waitForTimeout(500);
  }

  const section = page.locator('.inline-group').filter({ has: page.locator('h2:has-text("Dynamic form field")') });
  const labelInputs = section.locator('input[name*="-label"]:not([name*="__prefix__"])');
  const count = await labelInputs.count();
  const labels: string[] = [];
  for (let i = 0; i < count; i++) {
    const value = await labelInputs.nth(i).inputValue();
    if (value.trim()) labels.push(value);
  }
  return labels;
}

test.describe('Product Duplication / Duplication de produit', () => {
  const randomId = generateRandomId();
  const originalProductName = `Test Duplication ${randomId}`;

  test('should duplicate product and verify independence / dupliquer et vérifier l\'indépendance', async ({ page }) => {
    test.setTimeout(90000);

    await test.step('Login', async () => {
      await loginAsAdmin(page);
    });

    await test.step('Create product / Créer le produit', async () => {
      await page.goto('/admin/BaseBillet/product/add/');
      await page.waitForLoadState('networkidle');

      await page.locator('input[name="name"]').fill(originalProductName);
      await page.locator('select[name="categorie_article"]').selectOption('A');
      await page.locator('input[name="short_description"]').fill('Produit de test pour duplication');

      await addInlinePrice(page, { name: 'Tarif Original 1', prix: 10, subscription_type: 'Y', prix_libre: true });
      await addInlinePrice(page, { name: 'Tarif Original 2', prix: 5, subscription_type: 'Y', adhesion_obligatoire: true });
      await addInlinePrice(page, { name: 'Tarif Original 3', prix: 20, subscription_type: 'M' });

      const saveAndContinueButton = page.locator('button[name="_continue"], input[name="_continue"]').first();
      await saveAndContinueButton.click();
      await page.waitForLoadState('networkidle');
      console.log('✓ Product saved / Produit enregistré');
    });

    await test.step('Add form field / Ajouter champ formulaire', async () => {
      const tab = page.locator('button:has-text("Dynamic form field"), a:has-text("Dynamic form field")').first();
      if (await tab.count() > 0) {
        await tab.click();
        await page.waitForTimeout(800);

        const section = page.locator('.inline-group').filter({ has: page.locator('h2:has-text("Dynamic form field")') });
        if (await section.count() > 0) {
          // Add only one form field to keep test fast
          await addFormField(page, {
            label: 'Champ Original',
            type: 'ST',
            required: true,
            help_text: 'Texte court',
            order: 1
          });

          const saveButton = page.locator('button[type="submit"]:has-text("Save"), input[type="submit"]').first();
          await saveButton.click();
          await page.waitForLoadState('networkidle');
          console.log('✓ Form field added / Champ ajouté');
        } else {
          console.log('⚠ Form fields section not available / Section non disponible');
        }
      } else {
        console.log('⚠ Form fields tab not found / Onglet non trouvé');
      }
    });

    await test.step('Capture original data / Capturer données originales', async () => {
      await page.goto('/admin/BaseBillet/product/');
      await page.waitForLoadState('networkidle');

      const productLink = page.locator('#result_list a, .result-list a').filter({ hasText: originalProductName }).first();
      await productLink.click();
      await page.waitForLoadState('networkidle');

      const originalPrices = await getPriceNames(page);
      expect(originalPrices).toContain('Tarif Original 1');
      expect(originalPrices).toContain('Tarif Original 2');
      expect(originalPrices).toContain('Tarif Original 3');
      console.log('✓ Original prices:', originalPrices);

      const originalFormLabels = await getFormFieldLabels(page);
      if (originalFormLabels.length > 0) {
        expect(originalFormLabels).toContain('Champ Original');
        console.log('✓ Original form labels:', originalFormLabels);
      }
    });

    await test.step('Duplicate product / Dupliquer le produit', async () => {
      // Go to product list - this will be the HTTP_REFERER
      const listUrl = '/admin/BaseBillet/product/';
      await page.goto(listUrl);
      await page.waitForLoadState('networkidle');
      console.log('✓ On product list / Sur la liste des produits');

      // Find the product row and extract the product ID from the edit link
      const productRow = page.locator('tr').filter({ hasText: originalProductName }).first();
      await expect(productRow).toBeVisible({ timeout: 5000 });
      console.log('✓ Product found in list / Produit trouvé dans la liste');

      // Get the product ID from the edit URL (UUID format)
      const editLink = productRow.locator('a').first();
      const editHref = await editLink.getAttribute('href');
      const productIdMatch = editHref?.match(/\/([a-f0-9-]+)\/change\//);

      if (!productIdMatch) {
        throw new Error(`Could not extract product ID from href: ${editHref}`);
      }

      const productId = productIdMatch[1];
      console.log(`✓ Extracted product ID: ${productId}`);

      // Navigate to duplicate URL from the list page to ensure HTTP_REFERER is set
      const duplicateUrl = `/admin/BaseBillet/product/${productId}/duplicate_product/`;
      console.log(`✓ Navigating to duplicate URL: ${duplicateUrl}`);

      // Use evaluate to navigate with proper referer by creating and clicking a link
      await page.evaluate((url) => {
        const link = document.createElement('a');
        link.href = url;
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
      }, duplicateUrl);

      await page.waitForLoadState('networkidle');
      console.log('✓ Duplication completed / Duplication terminée');

      console.log('✓ Product duplicated / Produit dupliqué');
    });

    await test.step('Modify duplicate / Modifier la copie', async () => {
      // Find and open the duplicated product
      // The duplicated product should now exist in the list with " [DUPLICATA]" appended
      // but is unpublished by default, so we need to show unpublished products
      // Use URL parameter to show unpublished products
      await page.goto('/admin/BaseBillet/product/?publish=false');
      await page.waitForLoadState('networkidle');

      // Look for the duplicated product with "[DUPLICATA]" in the name
      const duplicateLink = page.locator('#result_list a, .result-list a').filter({ hasText: `${originalProductName} [DUPLICATA]` }).first();

      if (await duplicateLink.count() === 0) {
        // List all products to debug
        const allLinks = await page.locator('#result_list a, .result-list a').filter({ has: page.locator('text=/Test Duplication/i') }).all();
        console.log(`Total products with "Test Duplication": ${allLinks.length}`);
        for (let i = 0; i < allLinks.length; i++) {
          const text = await allLinks[i].textContent();
          console.log(`  Product ${i + 1}: ${text}`);
        }
        throw new Error(`Expected to find product "${originalProductName} [DUPLICATA]", but it was not found. Duplication may have failed.`);
      }

      console.log('✓ Found duplicated product with [DUPLICATA] suffix / Produit dupliqué trouvé avec suffixe [DUPLICATA]');
      await duplicateLink.click();
      await page.waitForLoadState('networkidle');
      console.log('✓ Opened duplicated product / Produit dupliqué ouvert')

      await page.locator('input[name="name"]').fill(`${originalProductName} (copie)`);

      const priceInputs = page.locator('input[name*="prices-"][name$="-name"]:not([name*="__prefix__"])');
      const priceCount = await priceInputs.count();

      for (let i = 0; i < priceCount; i++) {
        const currentValue = await priceInputs.nth(i).inputValue();
        if (currentValue.includes('Original')) {
          const newValue = currentValue.replace('Original', 'Dupliqué');
          await priceInputs.nth(i).fill(newValue);
        }
      }

      // Modify form field labels too
      const tab = page.locator('button:has-text("Dynamic form field"), a:has-text("Dynamic form field")').first();
      if (await tab.count() > 0) {
        await tab.click();
        await page.waitForTimeout(500);

        const section = page.locator('.inline-group').filter({ has: page.locator('h2:has-text("Dynamic form field")') });
        const labelInputs = section.locator('input[name*="-label"]:not([name*="__prefix__"])');
        const labelCount = await labelInputs.count();

        for (let i = 0; i < labelCount; i++) {
          const currentValue = await labelInputs.nth(i).inputValue();
          if (currentValue.includes('Original')) {
            const newValue = currentValue.replace('Original', 'Dupliqué');
            await labelInputs.nth(i).fill(newValue);
            console.log(`✓ Changed form label: ${currentValue} → ${newValue}`);
          }
        }
      }

      const saveButton = page.locator('button[type="submit"]:has-text("Save"), input[type="submit"]').first();
      await saveButton.click();
      await page.waitForLoadState('networkidle');
      console.log('✓ Duplicate modified and saved / Copie modifiée et enregistrée');
    });

    await test.step('Verify original unchanged / Vérifier original inchangé', async () => {
      await page.goto('/admin/BaseBillet/product/');
      await page.waitForLoadState('networkidle');

      // Find the original product (without [DUPLICATA] suffix)
      const originalLink = page.locator('#result_list a, .result-list a')
        .filter({ hasText: originalProductName })
        .filter({ hasNotText: '[DUPLICATA]' })
        .filter({ hasNotText: 'copie' })
        .first();
      await originalLink.click();
      await page.waitForLoadState('networkidle');

      const originalPrices = await getPriceNames(page);
      expect(originalPrices).toContain('Tarif Original 1');
      expect(originalPrices).toContain('Tarif Original 2');
      expect(originalPrices).toContain('Tarif Original 3');
      expect(originalPrices.every(p => p.includes('Original'))).toBeTruthy();
      console.log('✓ Original prices unchanged:', originalPrices);

      const originalFormLabels = await getFormFieldLabels(page);
      if (originalFormLabels.length > 0) {
        expect(originalFormLabels).toContain('Champ Original');
        expect(originalFormLabels.every(l => l.includes('Original'))).toBeTruthy();
        console.log('✓ Original form labels unchanged:', originalFormLabels);
      }
    });

    await test.step('Verify duplicate has changes / Vérifier copie modifiée', async () => {
      await page.goto('/admin/BaseBillet/product/');
      await page.waitForLoadState('networkidle');

      const duplicateLink = page.locator('#result_list a, .result-list a')
        .filter({ hasText: `${originalProductName} (copie)` }).first();
      await duplicateLink.click();
      await page.waitForLoadState('networkidle');

      const duplicatedPrices = await getPriceNames(page);
      expect(duplicatedPrices).toContain('Tarif Dupliqué 1');
      expect(duplicatedPrices).toContain('Tarif Dupliqué 2');
      expect(duplicatedPrices).toContain('Tarif Dupliqué 3');
      expect(duplicatedPrices.every(p => p.includes('Dupliqué'))).toBeTruthy();
      console.log('✓ Duplicated prices modified:', duplicatedPrices);

      const duplicatedFormLabels = await getFormFieldLabels(page);
      if (duplicatedFormLabels.length > 0) {
        expect(duplicatedFormLabels).toContain('Champ Dupliqué');
        expect(duplicatedFormLabels.every(l => l.includes('Dupliqué'))).toBeTruthy();
        console.log('✓ Duplicated form labels modified:', duplicatedFormLabels);
      }
    });

    console.log('✅ Test passed: Products are independent / Test réussi : Les produits sont indépendants');
  });
});
