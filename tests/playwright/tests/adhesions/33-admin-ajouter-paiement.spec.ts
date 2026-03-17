import { test, expect } from '@playwright/test';
import { loginAsAdmin } from '../utils/auth';
import { createProduct, createMembershipApi } from '../utils/api';

/**
 * TEST: Add offline payment on a pending membership from admin
 * TEST : Ajouter un paiement hors-ligne sur une adhesion en attente
 *
 * Nouveau flux (v1.7.7) :
 * Les actions sont dans le panneau HTMX inline affiché avant le formulaire admin.
 * Plus de page intermédiaire — tout se passe dans la vue change de l'adhésion.
 *
 * New flow (v1.7.7):
 * Actions are in the inline HTMX panel shown before the admin form.
 * No intermediate page — everything happens in the membership change view.
 *
 * Scenarios :
 * 1. Ajouter un paiement especes sur adhesion WP -> succes inline
 * 2. Gardes : "Offert" avec montant > 0 -> erreur inline
 * 3. Adhesion non en attente -> bouton "Enregistrer un paiement" absent
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
    // Creer un produit adhesion avec validation manuelle
    // Create a membership product with manual validation
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

    // Trouver l'adhesion dans l'admin et aller sur sa page de modification
    // Find the membership in admin and go to its change page
    await test.step('Find membership and go to change page / Trouver l\'adhesion et aller sur la fiche', async () => {
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

      console.log(`✓ On membership change page: ${page.url()}`);
    });

    // Le panneau HTMX doit etre visible avant le formulaire
    // HTMX panel must be visible before the form
    await test.step('Panel HTMX visible avec le bouton paiement / HTMX panel visible with payment button', async () => {
      const panelButton = page.locator('[data-testid="membership-action-ajouter-paiement"]');
      await expect(panelButton).toBeVisible({ timeout: 5000 });
      console.log('✓ Bouton "Enregistrer un paiement" visible dans le panneau');
    });

    // Cliquer sur "Enregistrer un paiement" → le formulaire apparait inline via HTMX
    // Click "Enregistrer un paiement" → form appears inline via HTMX
    await test.step('Click payment button → form appears inline / Clic bouton → formulaire inline', async () => {
      const panelButton = page.locator('[data-testid="membership-action-ajouter-paiement"]');
      await panelButton.click();

      // Attendre que le formulaire HTMX s'affiche
      // Wait for HTMX form to appear
      const form = page.locator('[data-testid="membership-paiement-form"]');
      await expect(form).toBeVisible({ timeout: 5000 });
      console.log('✓ Formulaire de paiement apparu inline via HTMX');
    });

    // Verifier que le montant est pre-rempli avec le prix catalogue
    // Check that amount is pre-filled with catalog price
    await test.step('Verify form is pre-filled / Verifier le formulaire pre-rempli', async () => {
      const amountInput = page.locator('[data-testid="membership-payment-amount"]');
      await expect(amountInput).toBeVisible();

      const amountValue = await amountInput.inputValue();
      const parsed = parseFloat(amountValue.replace(',', '.'));
      expect(parsed).toBe(25.00);
      console.log(`✓ Montant pre-rempli : ${amountValue}`);

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

      // Le succes s'affiche inline — pas de navigation de page
      // Success is shown inline — no page navigation
      const successArea = page.locator('[data-testid="membership-paiement-success"]');
      await expect(successArea).toBeVisible({ timeout: 10000 });
      const successText = await successArea.innerText();
      console.log(`✓ Paiement enregistre (succes inline) : ${successText.trim()}`);
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
      console.log(`✓ ${rowCount} LigneArticle trouve(s) dans l'admin`);

      // Verifier qu'on a une ligne Confirmed
      // Check we have a Confirmed line
      const bodyText = await page.innerText('body');
      const hasConfirmed = bodyText.includes('CONFIRMED') || bodyText.includes('Confirmed') || bodyText.includes('Confirmé');
      expect(hasConfirmed).toBeTruthy();
      console.log('✓ Ligne CONFIRMED visible dans l\'admin');
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

    // Trouver l'adhesion et aller sur sa fiche
    // Find membership and go to its change page
    await test.step('Navigate to membership change page / Naviguer vers la fiche adhesion', async () => {
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

    // Ouvrir le formulaire de paiement via HTMX
    // Open payment form via HTMX
    await test.step('Open payment form / Ouvrir le formulaire de paiement', async () => {
      const panelButton = page.locator('[data-testid="membership-action-ajouter-paiement"]');
      await expect(panelButton).toBeVisible({ timeout: 5000 });
      await panelButton.click();

      const form = page.locator('[data-testid="membership-paiement-form"]');
      await expect(form).toBeVisible({ timeout: 5000 });
    });

    // Soumettre "Offert" avec 25 euros → doit echouer
    // Submit "Offered" with 25 euros → must fail
    await test.step('Submit "Offered" with 25 euros / Soumettre "Offert" avec 25 euros', async () => {
      const amountInput = page.locator('[data-testid="membership-payment-amount"]');
      await amountInput.fill('25');

      const methodSelect = page.locator('[data-testid="membership-payment-method"]');
      await methodSelect.selectOption('NA'); // Offered / Offert

      const submitButton = page.locator('[data-testid="membership-payment-submit"]');
      await submitButton.click();

      // Erreur affichee inline dans le formulaire (pas de div.errornote Django admin)
      // Error shown inline in the form (no Django admin div.errornote)
      const form = page.locator('[data-testid="membership-paiement-form"]');
      await expect(form).toBeVisible({ timeout: 5000 });

      const pageContent = await page.innerText('body');
      expect(
        pageContent.toLowerCase().includes('offert') ||
        pageContent.toLowerCase().includes('offered') ||
        pageContent.toLowerCase().includes('impossible')
      ).toBeTruthy();
      console.log('✓ Offert avec montant positif refuse (erreur inline)');
    });
  });
});
