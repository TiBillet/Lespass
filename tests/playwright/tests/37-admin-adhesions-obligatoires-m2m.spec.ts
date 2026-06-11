import { test, expect, Page } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';

/**
 * TEST: Adhesions obligatoires M2M on Price
 * TEST : Adhesions obligatoires M2M sur un tarif
 *
 * L'admin produit a ete refondu en proxys :
 * - adhesions via /admin/BaseBillet/membershipproduct/ (categorie cachee, subscription_type dans l'inline)
 * - billetterie via /admin/BaseBillet/ticketproduct/ (adhesions_obligatoires directement dans l'inline tarif)
 * / Product admin was split into proxies:
 * - memberships via the membershipproduct proxy (hidden category, subscription_type in the inline)
 * - ticketing via the ticketproduct proxy (adhesions_obligatoires directly in the price inline)
 *
 * Flow :
 * 1. Create 2 membership products / Creer 2 produits adhesion
 * 2. Create a free reservation product (auto-generates a free price)
 *    / Creer un produit reservation gratuite (genere auto un tarif gratuit)
 * 3. Save and continue: the inline shows the auto-created free price
 *    / Enregistrer et continuer : l'inline affiche le tarif gratuit auto-cree
 * 4. Add 2 adhesions via select2 autocomplete in the inline / Ajouter 2 adhesions via select2 dans l'inline
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
      await createMembershipProduct(page, membershipName1, '10');
      console.log(`Created membership A: ${membershipName1}`);
    });

    // --- Create membership product B ---
    await test.step('Create membership product B / Creer produit adhesion B', async () => {
      await createMembershipProduct(page, membershipName2, '15');
      console.log(`Created membership B: ${membershipName2}`);
    });

    // --- Create free reservation product: the free price is AUTO-created ---
    // Le tarif gratuit FREERES est auto-cree par post_save_Product, y compris
    // via le proxy TicketProduct (bug corrige le 2026-06-11 : les proxys sont
    // connectes aux signaux Product — cf. PROXYS_PRODUCT dans models.py et le
    // test de garde tests/pytest/test_signaux_proxys_product.py).
    // / The FREERES free price is auto-created by post_save_Product, including
    // through the TicketProduct proxy (bug fixed on 2026-06-11: proxies are
    // connected to the Product signals — see PROXYS_PRODUCT in models.py and
    // the guard test tests/pytest/test_signaux_proxys_product.py).
    await test.step('Create free reservation product / Creer produit reservation gratuite', async () => {
      await page.goto('/admin/BaseBillet/ticketproduct/add/');
      await page.waitForLoadState('networkidle');
      await page.locator('input[name="name"]').fill(freeResProductName);
      await page.locator('select[name="categorie_article"]').selectOption('F'); // FREERES

      // Save and continue editing / Enregistrer et continuer
      await page.locator('button[name="_continue"], input[name="_continue"]').first().click();
      await page.waitForLoadState('networkidle');

      // We must be on the change page of the saved product
      // On doit etre sur la page de modification du produit sauvegarde
      await expect(page).toHaveURL(/\/admin\/BaseBillet\/ticketproduct\/[0-9a-f-]+\/change\//);
      console.log(`Created free reservation product: ${freeResProductName}`);
    });

    // --- The inline shows the AUTO-created free price with the M2M field ---
    await test.step('Verify auto-created free price inline / Verifier le tarif gratuit auto-cree', async () => {
      // Le tarif gratuit auto-cree est la premiere ligne de l'inline (prices-0)
      // et son prix vaut 0 — c'est la preuve E2E du fix des signaux proxys.
      // / The auto-created free price is the first inline row (prices-0) and
      // its price is 0 — the E2E proof of the proxy-signals fix.
      const prixInput = page.locator('input[name="prices-0-prix"]');
      await expect(prixInput).toBeAttached({ timeout: 10000 });
      await expect(prixInput).toHaveValue(/^0([.,]0+)?$/);
      const adhesionsSelect = page.locator('select[name="prices-0-adhesions_obligatoires"]');
      await expect(adhesionsSelect).toBeAttached({ timeout: 10000 });
      console.log('Auto-created free price inline with adhesions_obligatoires field - OK');
    });

    // --- Verify no "add +" button on the M2M widget ---
    await test.step('Verify no add button / Verifier pas de bouton +', async () => {
      const addRelatedBtn = page.locator(
        '#add_id_prices-0-adhesions_obligatoires, .field-adhesions_obligatoires a.add-related'
      );
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

    // --- Save and continue editing to stay on the page ---
    await test.step('Save price / Enregistrer le tarif', async () => {
      await page.locator('button[name="_continue"], input[name="_continue"]').first().click();
      await page.waitForLoadState('networkidle');
      await expect(page).toHaveURL(/\/admin\/BaseBillet\/ticketproduct\/[0-9a-f-]+\/change\//);
      console.log('Product saved with 2 adhesions on the free price');
    });

    // --- Verify both adhesions persisted after reload ---
    await test.step('Verify both adhesions saved / Verifier les 2 adhesions', async () => {
      const selected = await getSelectedAdhesions(page);
      expect(selected).toContain(membershipName1);
      expect(selected).toContain(membershipName2);
      console.log(`Verified adhesions: ${selected.join(', ')}`);
    });

    // --- Remove adhesion A ---
    await test.step('Remove adhesion A / Retirer adhesion A', async () => {
      await removeAdhesionSelect2(page, membershipName1);

      // Save and continue / Enregistrer et continuer
      await page.locator('button[name="_continue"], input[name="_continue"]').first().click();
      await page.waitForLoadState('networkidle');
      await expect(page).toHaveURL(/\/admin\/BaseBillet\/ticketproduct\/[0-9a-f-]+\/change\//);
      console.log(`Removed adhesion A: ${membershipName1}`);
    });

    // --- Verify only adhesion B remains after reload ---
    await test.step('Verify only adhesion B remains / Verifier seule B reste', async () => {
      const selected = await getSelectedAdhesions(page);
      expect(selected).not.toContain(membershipName1);
      expect(selected).toContain(membershipName2);
      console.log(`Final adhesions: ${selected.join(', ')}`);
    });

    console.log('Test passed / Test reussi');
  });
});


/**
 * Create a membership product via the MembershipProduct proxy admin.
 * The category is fixed by the proxy (hidden field), no selectOption needed.
 * / Create a membership product via the MembershipProduct proxy admin.
 * The category is set by the proxy (hidden field), no selectOption needed.
 */
async function createMembershipProduct(page: Page, name: string, prix: string) {
  await page.goto('/admin/BaseBillet/membershipproduct/add/');
  await page.waitForLoadState('networkidle');
  await page.locator('input[name="name"]').fill(name);

  // Add an inline price row / Ajouter une ligne de tarif inline
  const addBtn = page.locator('a:has-text("Add another"), button:has-text("Add another"), a:has-text("Ajouter")').first();
  await addBtn.click();
  await page.waitForTimeout(500);
  await page.locator('input[name="prices-0-name"]').fill('Tarif annuel');
  await page.locator('input[name="prices-0-prix"]').fill(prix);
  await page.locator('select[name="prices-0-subscription_type"]').selectOption('Y');

  await page.locator('button[name="_save"], input[name="_save"]').first().click();
  await page.waitForLoadState('networkidle');
}


/**
 * Add an adhesion via select2 autocomplete widget (inline price row)
 * / Ajouter une adhesion via le widget select2 autocomplete (ligne tarif inline)
 *
 * Select2 renders:
 * - A hidden <select multiple> with name="prices-0-adhesions_obligatoires"
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

  // Close the dropdown so it does not block other interactions
  // Fermer le dropdown pour ne pas bloquer les autres interactions
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);

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
    const cleaned = text?.replace(/^[×✕×x]\s*/, '').trim();
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
