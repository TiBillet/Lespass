import { test, expect, Page } from '@playwright/test';
import { loginAsAdmin } from '../utils/auth';

/**
 * TEST: Adhesions obligatoires M2M on Price
 * TEST : Adhesions obligatoires M2M sur un tarif
 *
 * Flow :
 * 1. Create 2 membership products / Creer 2 produits adhesion
 * 2. Create a free reservation product (auto-generates a free price)
 *    / Creer un produit reservation gratuite (genere auto un tarif gratuit)
 * 3. Save, then open the free price in standalone admin
 *    / Enregistrer, puis ouvrir le tarif gratuit en standalone
 * 4. Add 2 adhesions via select2 autocomplete / Ajouter 2 adhesions via select2
 * 5. Save and verify both are persisted / Enregistrer et verifier
 * 6. Remove one, verify only the other remains / Retirer une, verifier
 * 7. Verify no "add +" button on the M2M widget / Verifier pas de bouton "+"
 */

const uid = Date.now().toString(36);

test.describe('Adhesions obligatoires M2M / Adhesions obligatoires M2M', () => {
  const membershipName1 = `Adhesion A ${uid}`;
  const membershipName2 = `Adhesion B ${uid}`;
  const freeResProductName = `Resa Gratuite AdhTest ${uid}`;

  test('should manage multiple adhesions on a price / gerer plusieurs adhesions sur un tarif', async ({ page }) => {
    test.setTimeout(120000);

    // --- Login ---
    await test.step('Login', async () => {
      await loginAsAdmin(page);
    });

    // --- Create membership product A ---
    await test.step('Create membership product A / Creer produit adhesion A', async () => {
      await page.goto('/admin/BaseBillet/product/add/');
      await page.waitForLoadState('networkidle');
      await page.locator('input[name="name"]').fill(membershipName1);
      await page.locator('select[name="categorie_article"]').selectOption('A');

      const addBtn = page.locator('a:has-text("Add another"), button:has-text("Add another")').first();
      await addBtn.click();
      await page.waitForTimeout(500);
      await page.locator('input[name="prices-0-name"]').fill('Tarif annuel');
      await page.locator('input[name="prices-0-prix"]').fill('10');
      await page.locator('select[name="prices-0-subscription_type"]').selectOption('Y');

      await page.locator('button[type="submit"]:has-text("Save"), input[type="submit"]').first().click();
      await page.waitForLoadState('networkidle');
      console.log(`Created membership A: ${membershipName1}`);
    });

    // --- Create membership product B ---
    await test.step('Create membership product B / Creer produit adhesion B', async () => {
      await page.goto('/admin/BaseBillet/product/add/');
      await page.waitForLoadState('networkidle');
      await page.locator('input[name="name"]').fill(membershipName2);
      await page.locator('select[name="categorie_article"]').selectOption('A');

      const addBtn = page.locator('a:has-text("Add another"), button:has-text("Add another")').first();
      await addBtn.click();
      await page.waitForTimeout(500);
      await page.locator('input[name="prices-0-name"]').fill('Tarif annuel');
      await page.locator('input[name="prices-0-prix"]').fill('15');
      await page.locator('select[name="prices-0-subscription_type"]').selectOption('Y');

      await page.locator('button[type="submit"]:has-text("Save"), input[type="submit"]').first().click();
      await page.waitForLoadState('networkidle');
      console.log(`Created membership B: ${membershipName2}`);
    });

    // --- Create free reservation product (auto-generates a free price) ---
    await test.step('Create free reservation product / Creer produit reservation gratuite', async () => {
      await page.goto('/admin/BaseBillet/product/add/');
      await page.waitForLoadState('networkidle');
      await page.locator('input[name="name"]').fill(freeResProductName);
      await page.locator('select[name="categorie_article"]').selectOption('F'); // FREERES

      // Save and continue — Django post_save will auto-create a "Free rate" price
      await page.locator('button[name="_continue"], input[name="_continue"]').first().click();
      await page.waitForLoadState('networkidle');

      // Verify the product was saved (success message)
      const successMsg = page.locator('.messagelist .success, .alert-success, div.bg-green-100');
      await expect(successMsg).toBeVisible({ timeout: 5000 });
      console.log(`Created free reservation product: ${freeResProductName}`);
    });

    // --- Open the auto-generated free price in standalone admin ---
    let priceChangeUrl: string;

    await test.step('Open free price in standalone admin / Ouvrir le tarif gratuit en standalone', async () => {
      // The inline should show the auto-created "Free rate" price with a change link
      const changeLink = page.locator('a[href*="/admin/BaseBillet/price/"]').first();
      const href = await changeLink.getAttribute('href');
      expect(href).toBeTruthy();
      priceChangeUrl = href!;
      console.log(`Price change URL: ${priceChangeUrl}`);

      await page.goto(priceChangeUrl);
      await page.waitForLoadState('networkidle');

      // Verify we are on the Price change page
      const nameInput = page.locator('input[name="name"]');
      await expect(nameInput).toBeVisible();
      console.log('Opened Price standalone form');
    });

    // --- Verify no "add +" button on the M2M widget ---
    await test.step('Verify no add button / Verifier pas de bouton +', async () => {
      const addRelatedBtn = page.locator('#add_id_adhesions_obligatoires, a.add-related[href*="adhesions"]');
      await expect(addRelatedBtn).toHaveCount(0);
      console.log('No add button on M2M widget - OK');
    });

    // --- Add adhesion A via select2 ---
    await test.step('Add adhesion A via select2 / Ajouter adhesion A', async () => {
      await addAdhesionSelect2(page, membershipName1);
    });

    // --- Add adhesion B via select2 ---
    await test.step('Add adhesion B via select2 / Ajouter adhesion B', async () => {
      await addAdhesionSelect2(page, membershipName2);
    });

    // --- Save — PriceAdmin.response_change redirige vers la page Product parent ---
    // --- Save — PriceAdmin.response_change redirects to the parent Product page ---
    await test.step('Save price / Enregistrer le tarif', async () => {
      await page.locator('button[type="submit"]:has-text("Save"), input[type="submit"]').first().click();
      await page.waitForLoadState('networkidle');
      // Apres save, on est redirige vers la page Product parent avec un message de succes
      // After save, we are redirected to the parent Product page with a success message
      const successMsg = page.locator('.messagelist .success, .alert-success, div.bg-green-100');
      await expect(successMsg).toBeVisible({ timeout: 5000 });
      console.log('Price saved with 2 adhesions');
    });

    // --- Re-ouvrir la page Price pour verifier les adhesions ---
    // --- Re-open the Price page to verify adhesions ---
    await test.step('Verify both adhesions saved / Verifier les 2 adhesions', async () => {
      // Naviguer vers le tarif via le lien Change dans l'inline
      // Navigate to the price via the Change link in the inline
      const changeLink = page.locator('a[href*="/admin/BaseBillet/price/"]').first();
      await changeLink.click();
      await page.waitForLoadState('networkidle');

      const selected = await getSelectedAdhesions(page);
      expect(selected).toContain(membershipName1);
      expect(selected).toContain(membershipName2);
      console.log(`Verified adhesions: ${selected.join(', ')}`);
    });

    // --- Remove adhesion A ---
    await test.step('Remove adhesion A / Retirer adhesion A', async () => {
      await removeAdhesionSelect2(page, membershipName1);

      // Save — redirige vers Product parent
      // Save — redirects to parent Product
      await page.locator('button[type="submit"]:has-text("Save"), input[type="submit"]').first().click();
      await page.waitForLoadState('networkidle');
      const successMsg = page.locator('.messagelist .success, .alert-success, div.bg-green-100');
      await expect(successMsg).toBeVisible({ timeout: 5000 });
      console.log(`Removed adhesion A: ${membershipName1}`);
    });

    // --- Re-ouvrir la page Price et verifier ---
    // --- Re-open Price page and verify ---
    await test.step('Verify only adhesion B remains / Verifier seule B reste', async () => {
      const changeLink = page.locator('a[href*="/admin/BaseBillet/price/"]').first();
      await changeLink.click();
      await page.waitForLoadState('networkidle');

      const selected = await getSelectedAdhesions(page);
      expect(selected).not.toContain(membershipName1);
      expect(selected).toContain(membershipName2);
      console.log(`Final adhesions: ${selected.join(', ')}`);
    });

    console.log('Test passed / Test reussi');
  });
});


/**
 * Add an adhesion via select2 autocomplete widget
 * / Ajouter une adhesion via le widget select2 autocomplete
 *
 * Select2 renders:
 * - A hidden <select multiple> with id="id_adhesions_obligatoires"
 * - A visible <span class="select2 ..."> with a search input inside
 */
async function addAdhesionSelect2(page: Page, adhesionName: string) {
  // Click on the select2 search area to open the dropdown
  const select2Container = page.locator('.select2-container').filter({
    has: page.locator('[aria-labelledby*="adhesions_obligatoires"], [aria-owns*="adhesions_obligatoires"]')
  }).first();

  // Fallback: find the select2 container near the field
  const searchArea = page.locator('.field-adhesions_obligatoires .select2-selection, .field-adhesions_obligatoires .select2-container').first();

  const target = (await select2Container.count() > 0) ? select2Container : searchArea;
  await target.click();
  await page.waitForTimeout(300);

  // Type in the select2 search input (it appears in a dropdown)
  const searchInput = page.locator('.select2-search__field').last();
  await expect(searchInput).toBeVisible({ timeout: 3000 });
  // Type a substring to trigger the AJAX search
  await searchInput.fill(uid);
  await page.waitForTimeout(1000); // Wait for AJAX

  // Click the matching result
  const option = page.locator('.select2-results__option').filter({ hasText: adhesionName }).first();
  await expect(option).toBeVisible({ timeout: 5000 });
  await option.click();
  await page.waitForTimeout(300);

  console.log(`Added adhesion: ${adhesionName}`);
}


/**
 * Get the list of currently selected adhesions from select2
 * / Recuperer la liste des adhesions selectionnees dans select2
 *
 * Select2 multiple shows selected items as <li class="select2-selection__choice"> elements
 */
async function getSelectedAdhesions(page: Page): Promise<string[]> {
  const items = page.locator('.field-adhesions_obligatoires .select2-selection__choice');
  const count = await items.count();
  const names: string[] = [];
  for (let i = 0; i < count; i++) {
    const text = await items.nth(i).textContent();
    // select2 prepends a "x" remove button, strip it
    const cleaned = text?.replace(/^[\u00d7\u2715×x]\s*/, '').trim();
    if (cleaned) names.push(cleaned);
  }
  return names;
}


/**
 * Remove an adhesion from select2 by clicking its remove button
 * / Retirer une adhesion de select2 en cliquant sur son bouton de suppression
 */
async function removeAdhesionSelect2(page: Page, adhesionName: string) {
  const items = page.locator('.field-adhesions_obligatoires .select2-selection__choice');
  const count = await items.count();

  for (let i = 0; i < count; i++) {
    const text = await items.nth(i).textContent();
    if (text?.includes(adhesionName)) {
      // Click the remove button (x) inside this choice
      const removeBtn = items.nth(i).locator('.select2-selection__choice__remove');
      await removeBtn.click();
      await page.waitForTimeout(300);
      // Close any open select2 dropdown (it can stay open after remove)
      await page.keyboard.press('Escape');
      await page.waitForTimeout(200);
      console.log(`Removed adhesion: ${adhesionName}`);
      return;
    }
  }

  throw new Error(`Adhesion "${adhesionName}" not found in selected items`);
}
