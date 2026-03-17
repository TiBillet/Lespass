import { test, expect } from '@playwright/test';
import { loginAsAdmin } from '../utils/auth';
import { createProduct, createMembershipApi } from '../utils/api';

/**
 * TEST: Admin membership list — statut et deadline après adhésion réussie
 * TEST: Admin membership list — status and deadline after successful membership
 *
 * Vérifie que la vue liste admin (/admin/BaseBillet/membership/) affiche
 * correctement le statut et la deadline pour 3 scénarios d'adhésion réussie.
 *
 * Verifies that the admin list view (/admin/BaseBillet/membership/) displays
 * the correct status and deadline for 3 successful membership scenarios.
 *
 * Scénarios :
 * 1. Adhésion offerte via API (paymentMode FREE) → statut "Payé en ligne" + deadline date
 * 2. Adhésion créée via formulaire admin (Offert 0€) → statut "Créé via l'administration" + deadline date
 * 3. Adhésion prix libre 0€ via API → statut "Payé en ligne" + deadline date
 *
 * Colonne testées dans la liste :
 * - td.field-status      → statut lisible
 * - td.field-display_deadline → date de fin (format JJ/MM/AAAA, pas "-")
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

/**
 * Cherche une adhésion dans la liste admin par email et retourne la ligne.
 * Searches for a membership in the admin list by email and returns the row.
 *
 * Precondition : page est déjà sur /admin/BaseBillet/membership/
 * Precondition: page is already on /admin/BaseBillet/membership/
 */
async function rechercherDansListeAdmin(page: any, email: string) {
  const searchInput = page.locator('input[name="q"]').first();
  await searchInput.fill(email);
  await searchInput.press('Enter');
  await page.waitForLoadState('networkidle');
  return page.locator('#result_list tbody tr').filter({ hasText: email });
}

const randomId = generateRandomId();

test.describe('Admin Membership List Status / Statut vue liste admin adhésion', () => {

  let productName: string;
  let priceName: string;
  let priceUuid: string;

  test.beforeAll(async ({ request }) => {
    // Créer un produit adhésion annuel (subscription_type Y).
    // La deadline sera calculée = last_contribution + 12 mois.
    // Create annual membership product (subscription_type Y).
    // Deadline will be calculated = last_contribution + 12 months.
    productName = `Adhesion Liste ${randomId}`;
    priceName = `Annuel liste ${randomId}`;

    const productResult = await createProduct({
      request,
      name: productName,
      description: 'Test vue liste admin statut',
      category: 'Membership',
      offers: [{
        name: priceName,
        price: '15.00',
        subscriptionType: 'Y',
      }],
    });
    expect(productResult.ok).toBeTruthy();

    // Récupérer l'UUID du tarif créé
    // Get the UUID of the created price
    priceUuid = productResult.offers?.[0]?.identifier || '';
    expect(priceUuid).not.toBe('');
    console.log(`✓ Produit adhésion créé : ${productName} / ${priceName} (${priceUuid})`);
  });

  // ─────────────────────────────────────────────────────────────
  // Scénario 1 : Adhésion offerte via API (paymentMode FREE)
  // → status ONCE → "Payé en ligne" + deadline active
  // ─────────────────────────────────────────────────────────────
  test('1. API FREE → "Payé en ligne" + deadline / API FREE -> statut + deadline', async ({ page, request }) => {

    // Email unique pour ce scénario
    // Unique email for this scenario
    const email = `jturbeaux+list1${randomId}@pm.me`;

    // Créer l'adhésion via l'API (paymentMode FREE → status ONCE)
    // Create membership via API (paymentMode FREE → ONCE status)
    await test.step('Créer adhésion via API / Create membership via API', async () => {
      const result = await createMembershipApi({
        request,
        priceUuid,
        email,
        firstName: 'API',
        lastName: 'Test',
        paymentMode: 'FREE',
      });
      expect(result.ok).toBeTruthy();
      console.log('✓ Adhésion créée via API');
    });

    await loginAsAdmin(page);

    // Aller sur la liste admin et chercher l'adhésion
    // Go to admin list and search for the membership
    await test.step('Rechercher dans la liste admin / Search in admin list', async () => {
      await page.goto('/admin/BaseBillet/membership/');
      await page.waitForLoadState('networkidle');
    });

    // Vérifier statut et deadline dans la ligne
    // Verify status and deadline in the row
    await test.step('Vérifier statut et deadline / Verify status and deadline', async () => {
      const row = await rechercherDansListeAdmin(page, email);
      await expect(row).toBeVisible({ timeout: 10000 });

      // Le statut doit être "Payé en ligne" (status ONCE = 'A')
      // Status must be "Payé en ligne" (status ONCE = 'A')
      const statusCell = row.locator('td.field-status');
      await expect(statusCell).toContainText('Payé en ligne');

      // La deadline doit être une date au format JJ/MM/AAAA (pas "-")
      // Deadline must be a date in DD/MM/YYYY format (not "-")
      const deadlineCell = row.locator('td.field-display_deadline');
      const deadlineText = (await deadlineCell.innerText()).trim();
      expect(deadlineText).not.toBe('-');
      expect(deadlineText).toMatch(/\d{2}\/\d{2}\/\d{4}/);

      console.log(`✓ Scénario 1 — Statut: "${await statusCell.innerText()}", Deadline: "${deadlineText}"`);
    });
  });

  // ─────────────────────────────────────────────────────────────
  // Scénario 2 : Adhésion créée via formulaire admin (Offert, 0€)
  // → status ADMIN → "Créé via l'administration" + deadline active
  // ─────────────────────────────────────────────────────────────
  test('2. Formulaire admin → "Créé via l\'administration" + deadline', async ({ page }) => {

    // Email unique pour ce scénario
    // Unique email for this scenario
    const email = `jturbeaux+list2${randomId}@pm.me`;

    await loginAsAdmin(page);

    // Remplir le formulaire admin d'ajout d'adhésion
    // Fill the admin membership add form
    await test.step('Remplir le formulaire admin / Fill the admin form', async () => {
      await page.goto('/admin/BaseBillet/membership/add/');
      await page.waitForLoadState('networkidle');

      // Nom et prénom
      await page.locator('#id_last_name').fill('Admin');
      await page.locator('#id_first_name').fill('Test');

      // Email
      await page.locator('#id_email').fill(email);

      // Tarif : sélection par UUID (valeur du <select>)
      // Price: select by UUID (value of the <select>)
      await page.locator('#id_price').selectOption(priceUuid);

      // Contribution = 0 (adhésion offerte)
      // Contribution = 0 (offered membership)
      await page.locator('#id_contribution').fill('0');

      // Mode de paiement = NA (Offert) — déjà la valeur par défaut
      // Payment method = NA (Offered) — already the default value
      await page.locator('#id_payment_method').selectOption('NA');

      // Soumettre le formulaire avec "Enregistrer"
      // Submit the form with "Enregistrer"
      const saveButton = page.locator('[name="_save"]').first();
      await saveButton.click();
      await page.waitForLoadState('networkidle');

      console.log(`✓ Formulaire soumis, URL: ${page.url()}`);
    });

    // Chercher l'adhésion dans la liste admin
    // Search for the membership in the admin list
    await test.step('Rechercher dans la liste admin / Search in admin list', async () => {
      await page.goto('/admin/BaseBillet/membership/');
      await page.waitForLoadState('networkidle');
    });

    // Vérifier statut et deadline dans la ligne
    // Verify status and deadline in the row
    await test.step('Vérifier statut et deadline / Verify status and deadline', async () => {
      const row = await rechercherDansListeAdmin(page, email);
      await expect(row).toBeVisible({ timeout: 10000 });

      // Le statut doit être "Créé via l'administration" (status ADMIN = 'D').
      // Le signal post_save crée une LigneArticle mais ne change pas le statut.
      // Status must be "Créé via l'administration" (status ADMIN = 'D').
      // The post_save signal creates a LigneArticle but does not change the status.
      const statusCell = row.locator('td.field-status');
      await expect(statusCell).toContainText("l'administration");

      // La deadline doit être une date (trigger_A appelle set_deadline())
      // Deadline must be a date (trigger_A calls set_deadline())
      const deadlineCell = row.locator('td.field-display_deadline');
      const deadlineText = (await deadlineCell.innerText()).trim();
      expect(deadlineText).not.toBe('-');
      expect(deadlineText).toMatch(/\d{2}\/\d{2}\/\d{4}/);

      console.log(`✓ Scénario 2 — Statut: "${await statusCell.innerText()}", Deadline: "${deadlineText}"`);
    });
  });

  // ─────────────────────────────────────────────────────────────
  // Scénario 3 : Adhésion prix libre 0€ via API
  // → status ONCE → "Payé en ligne" + deadline active
  // ─────────────────────────────────────────────────────────────
  test('3. Prix libre 0€ via API → "Payé en ligne" + deadline', async ({ page, request }) => {

    // Email unique pour ce scénario
    // Unique email for this scenario
    const email = `jturbeaux+list3${randomId}@pm.me`;

    // Créer l'adhésion prix libre 0€ via API (customAmount = '0')
    // Create free-price 0€ membership via API (customAmount = '0')
    await test.step('Créer adhésion 0€ via API / Create 0€ membership via API', async () => {
      const result = await createMembershipApi({
        request,
        priceUuid,
        email,
        firstName: 'Zero',
        lastName: 'Euro',
        paymentMode: 'FREE',
        customAmount: '0',
      });
      expect(result.ok).toBeTruthy();
      console.log('✓ Adhésion prix libre 0€ créée via API');
    });

    await loginAsAdmin(page);

    // Aller sur la liste admin
    // Go to admin list
    await test.step('Rechercher dans la liste admin / Search in admin list', async () => {
      await page.goto('/admin/BaseBillet/membership/');
      await page.waitForLoadState('networkidle');
    });

    // Vérifier statut et deadline dans la ligne
    // Verify status and deadline in the row
    await test.step('Vérifier statut et deadline / Verify status and deadline', async () => {
      const row = await rechercherDansListeAdmin(page, email);
      await expect(row).toBeVisible({ timeout: 10000 });

      // Le statut doit être "Payé en ligne" (status ONCE = 'A')
      // Status must be "Payé en ligne" (ONCE = 'A')
      const statusCell = row.locator('td.field-status');
      await expect(statusCell).toContainText('Payé en ligne');

      // La deadline doit être une date (pas "-")
      // Deadline must be a date (not "-")
      const deadlineCell = row.locator('td.field-display_deadline');
      const deadlineText = (await deadlineCell.innerText()).trim();
      expect(deadlineText).not.toBe('-');
      expect(deadlineText).toMatch(/\d{2}\/\d{2}\/\d{4}/);

      console.log(`✓ Scénario 3 — Statut: "${await statusCell.innerText()}", Deadline: "${deadlineText}"`);
    });
  });

});
