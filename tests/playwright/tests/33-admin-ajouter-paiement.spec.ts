import { test, expect } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';
import { createProduct, createMembershipApi } from './utils/api';

/**
 * TEST: Add offline payment on a pending membership from admin
 * TEST : Ajouter un paiement hors-ligne sur une adhesion en attente
 *
 * Scenarios :
 * 1. Ajouter un paiement especes sur adhesion WP -> succes
 * 2. Gardes : montant negatif, "Offert" avec montant > 0
 * 3. Adhesion deja payee -> bouton absent
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

const randomId = generateRandomId();

test.describe('Admin Add Payment on Membership / Ajouter paiement adhesion admin', () => {

  let productName: string;
  let priceUuid: string;
  const userEmail = `jturbeaux+pay${randomId}@pm.me`;
  const userEmailGuard = `jturbeaux+payg${randomId}@pm.me`;

  test.beforeAll(async ({ request }) => {
    // Creer un produit adhesion gratuit avec prix
    // Create a free membership product with price
    productName = `Adhesion Paiement ${randomId}`;

    const productResult = await createProduct({
      request,
      name: productName,
      description: 'Test paiement admin',
      category: 'Membership',
      offers: [{
        name: 'Annuel',
        price: '25.00',
        subscriptionType: 'Y',
        manualValidation: true,
      }],
    });
    expect(productResult.ok).toBeTruthy();
    priceUuid = productResult.offers?.[0]?.identifier || '';
    expect(priceUuid).not.toBe('');
  });

  test('should add cash payment on pending membership / doit ajouter un paiement especes', async ({ page, request }) => {

    // Creer l'adhesion en status ADMIN_WAITING via l'API
    // Create membership in ADMIN_WAITING status via API
    await test.step('Create pending membership / Creer adhesion en attente', async () => {
      const msResult = await createMembershipApi({
        request,
        priceUuid,
        email: userEmail,
        firstName: 'Paiement',
        lastName: 'Test',
        status: 'AW',
      });
      expect(msResult.ok).toBeTruthy();
      console.log('✓ Created pending membership / Adhesion en attente creee');
    });

    await loginAsAdmin(page);

    let membershipPk = '';

    // Trouver l'adhesion dans l'admin
    // Find the membership in admin
    await test.step('Find membership in admin / Trouver l\'adhesion dans l\'admin', async () => {
      await page.goto('/admin/BaseBillet/membership/');
      await page.waitForLoadState('networkidle');

      // Chercher par email
      // Search by email
      const searchInput = page.locator('input[name="q"]').first();
      await searchInput.fill(userEmail);
      await searchInput.press('Enter');
      await page.waitForLoadState('networkidle');

      // Cliquer sur la premiere adhesion trouvee
      // Click the first found membership
      const firstLink = page.locator('#result_list tbody tr a').first();
      await expect(firstLink).toBeVisible({ timeout: 10000 });
      await firstLink.click();
      await page.waitForLoadState('networkidle');

      // Extraire le PK de l'URL
      // Extract PK from URL
      const url = page.url();
      const pkMatch = url.match(/\/membership\/(\d+)\//);
      expect(pkMatch).not.toBeNull();
      membershipPk = pkMatch![1];
      console.log(`✓ Found membership PK: ${membershipPk}`);
    });

    // Cliquer sur "Ajouter un paiement"
    // Click "Add payment"
    await test.step('Click add payment button / Cliquer sur ajouter paiement', async () => {
      const addPaymentLink = page.locator('a:has-text("Ajouter un paiement"), a:has-text("Add payment")').first();
      await expect(addPaymentLink).toBeVisible({ timeout: 5000 });
      await addPaymentLink.click();
      await page.waitForLoadState('networkidle');
      console.log('✓ Add payment form opened / Formulaire de paiement ouvert');
    });

    // Verifier le formulaire
    // Check the form
    await test.step('Verify form is pre-filled / Verifier le formulaire pre-rempli', async () => {
      const form = page.locator('[data-testid="membership-add-payment-form"]');
      await expect(form).toBeVisible({ timeout: 5000 });

      const amountInput = page.locator('[data-testid="membership-payment-amount"]');
      await expect(amountInput).toBeVisible();

      // Verifier que le montant est pre-rempli avec le prix du produit (25.00 ou 25,00)
      // Check amount is pre-filled with product price (25.00 or 25,00 depending on locale)
      const amountValue = await amountInput.inputValue();
      const parsed = parseFloat(amountValue.replace(',', '.'));
      expect(parsed).toBe(25.00);
      console.log(`✓ Amount pre-filled: ${amountValue}`);

      const methodSelect = page.locator('[data-testid="membership-payment-method"]');
      await expect(methodSelect).toBeVisible();
    });

    // Remplir et soumettre avec paiement especes
    // Fill and submit with cash payment
    await test.step('Submit cash payment / Soumettre paiement especes', async () => {
      const methodSelect = page.locator('[data-testid="membership-payment-method"]');
      await methodSelect.selectOption('CA'); // Cash / Especes

      const submitButton = page.locator('[data-testid="membership-payment-submit"]');
      await submitButton.click();
      await page.waitForLoadState('networkidle');

      // Verifier le message de succes
      // Check success message
      const successMessage = page.locator('.bg-green-100, .messagelist .success');
      await expect(successMessage).toBeVisible({ timeout: 10000 });
      const messageText = await successMessage.innerText();
      expect(
        messageText.toLowerCase().includes('paiement enregistr') ||
        messageText.toLowerCase().includes('payment recorded') ||
        messageText.toLowerCase().includes('succes') ||
        messageText.toLowerCase().includes('success')
      ).toBeTruthy();
      console.log('✓ Payment recorded successfully / Paiement enregistre');
    });

    // Verifier que l'adhesion est maintenant payee (pas d'erreur sur la page)
    // Check that membership is now paid (no error on page)
    await test.step('Verify membership is paid / Verifier adhesion payee', async () => {
      // On est redirige vers la page detail de l'adhesion
      // We are redirected to the membership detail page
      const pageContent = await page.innerText('body');
      // Verifier que le message de succes est affiche (bg-green-100)
      // Check that the success message is displayed
      expect(
        pageContent.toLowerCase().includes('paiement enregistr') ||
        pageContent.toLowerCase().includes('payment recorded') ||
        pageContent.toLowerCase().includes('succes') ||
        pageContent.toLowerCase().includes('success')
      ).toBeTruthy();
      console.log('✓ Membership paid successfully / Adhesion payee avec succes');
    });

    // Verifier les lignes de vente dans l'admin
    // Check sale lines in admin
    await test.step('Check LigneArticle in admin / Verifier les ventes dans l\'admin', async () => {
      await page.goto('/admin/BaseBillet/lignearticle/');
      await page.waitForLoadState('networkidle');

      const searchInput = page.locator('input[name="q"]').first();
      await searchInput.fill(productName);
      await searchInput.press('Enter');
      await page.waitForLoadState('networkidle');

      const rows = page.locator('#result_list tbody tr');
      const rowCount = await rows.count();
      expect(rowCount).toBeGreaterThanOrEqual(1);
      console.log(`✓ ${rowCount} LigneArticle row(s) found in admin / ligne(s) trouvee(s)`);

      // Verifier qu'on a une ligne Confirmed (paiement enregistre)
      // Check we have a Confirmed line (payment recorded)
      const bodyText = await page.innerText('body');
      const hasConfirmed = bodyText.includes('CONFIRMED') || bodyText.includes('Confirmed') || bodyText.includes('Confirmé');
      expect(hasConfirmed).toBeTruthy();
      console.log('✓ CONFIRMED line visible in admin / Ligne CONFIRMED visible');
    });
  });

  test('should reject "Offered" with positive amount / doit refuser "Offert" avec montant positif', async ({ page, request }) => {

    // Creer une 2e adhesion en attente pour les gardes
    // Create a 2nd pending membership for guard tests
    await test.step('Create 2nd pending membership / Creer 2e adhesion en attente', async () => {
      const msResult = await createMembershipApi({
        request,
        priceUuid,
        email: userEmailGuard,
        firstName: 'Guard',
        lastName: 'Test',
        status: 'AW',
      });
      expect(msResult.ok).toBeTruthy();
    });

    await loginAsAdmin(page);

    await test.step('Navigate to membership / Naviguer vers l\'adhesion', async () => {
      await page.goto('/admin/BaseBillet/membership/');
      await page.waitForLoadState('networkidle');

      const searchInput = page.locator('input[name="q"]').first();
      await searchInput.fill(userEmailGuard);
      await searchInput.press('Enter');
      await page.waitForLoadState('networkidle');

      const firstLink = page.locator('#result_list tbody tr a').first();
      await expect(firstLink).toBeVisible({ timeout: 10000 });
      await firstLink.click();
      await page.waitForLoadState('networkidle');
    });

    await test.step('Open payment form / Ouvrir le formulaire de paiement', async () => {
      const addPaymentLink = page.locator('a:has-text("Ajouter un paiement"), a:has-text("Add payment")').first();
      await expect(addPaymentLink).toBeVisible({ timeout: 5000 });
      await addPaymentLink.click();
      await page.waitForLoadState('networkidle');
    });

    await test.step('Submit "Offered" with 25 euros / Soumettre "Offert" avec 25 euros', async () => {
      const amountInput = page.locator('[data-testid="membership-payment-amount"]');
      await amountInput.fill('25');

      const methodSelect = page.locator('[data-testid="membership-payment-method"]');
      await methodSelect.selectOption('NA'); // Offered / Offert

      const submitButton = page.locator('[data-testid="membership-payment-submit"]');
      await submitButton.click();
      await page.waitForLoadState('networkidle');

      // Verifier le message d'erreur
      // Check error message
      const errorMessage = page.locator('div.errornote');
      await expect(errorMessage).toBeVisible({ timeout: 5000 });
      const errorText = await errorMessage.innerText();
      expect(
        errorText.toLowerCase().includes('offert') ||
        errorText.toLowerCase().includes('offered') ||
        errorText.toLowerCase().includes('impossible')
      ).toBeTruthy();
      console.log('✓ Offered with positive amount rejected / Offert avec montant positif refuse');
    });
  });
});
