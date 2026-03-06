import { test, expect } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';
import { createProduct, createMembershipApi } from './utils/api';
import { execSync } from 'child_process';

/**
 * TEST: Cancel membership with optional credit note from admin
 * TEST : Annulation adhesion avec option avoir depuis l'admin
 *
 * Scenarios :
 * 1. Annuler une adhesion sans lignes de vente -> confirmation simple
 * 2. Annuler une adhesion avec lignes payees -> choix avec/sans avoir
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

function djangoShell(pythonCode: string): string {
  const escaped = pythonCode.replace(/"/g, '\\"');
  const command = `docker exec lespass_django poetry run python /DjangoFiles/manage.py tenant_command shell -s lespass -c "${escaped}"`;
  try {
    return execSync(command, { encoding: 'utf-8', timeout: 20000 }).trim();
  } catch (error: any) {
    console.error(`Django shell error: ${error.message}`);
    return '';
  }
}

const randomId = generateRandomId();

test.describe('Admin Cancel Membership / Annulation adhesion admin', () => {

  let productName: string;
  let priceUuid: string;

  test.beforeAll(async ({ request }) => {
    productName = `Adhesion Annul ${randomId}`;

    const productResult = await createProduct({
      request,
      name: productName,
      description: 'Test annulation adhesion',
      category: 'Membership',
      offers: [{
        name: 'Annuel annul',
        price: '0.00',
        subscriptionType: 'Y',
      }],
    });
    expect(productResult.ok).toBeTruthy();
    priceUuid = productResult.offers?.[0]?.identifier || '';
    expect(priceUuid).not.toBe('');
  });

  test('should cancel membership without paid lines / doit annuler adhesion sans lignes payees', async ({ page, request }) => {
    const userEmail = `jturbeaux+canc${randomId}@pm.me`;

    await test.step('Create free membership / Creer adhesion gratuite', async () => {
      const msResult = await createMembershipApi({
        request,
        priceUuid,
        email: userEmail,
        firstName: 'Anne',
        lastName: 'Gratuit',
        paymentMode: 'FREE',
      });
      expect(msResult.ok).toBeTruthy();
    });

    await loginAsAdmin(page);

    let membershipPk = '';

    // Recuperer le PK directement en base
    // Get PK directly from DB
    await test.step('Get membership PK / Recuperer le PK', async () => {
      const result = djangoShell(`
from BaseBillet.models import Membership
m = Membership.objects.filter(user__email='${userEmail}').first()
if m: print(f'pk={m.pk}')
else: print('NOT_FOUND')
`);
      expect(result).not.toContain('NOT_FOUND');
      const pkMatch = result.match(/pk=(\d+)/);
      expect(pkMatch).not.toBeNull();
      membershipPk = pkMatch![1];
      console.log(`✓ Membership PK: ${membershipPk}`);
    });

    // Appeler l'URL cancel directement (action_detail Unfold)
    // Call cancel URL directly (Unfold action_detail)
    await test.step('Go to cancel page / Aller sur la page d\'annulation', async () => {
      await page.goto(`/admin/BaseBillet/membership/${membershipPk}/cancel/`);
      await page.waitForLoadState('networkidle');
    });

    // Verifier la page de confirmation et annuler sans avoir
    // Check confirmation page and cancel without credit note
    await test.step('Verify and confirm cancellation / Verifier et confirmer l\'annulation', async () => {
      const pageContent = await page.innerText('body');

      // La page doit contenir les infos de l'adherent
      // Page should contain member info
      expect(pageContent).toContain(userEmail);

      // Cliquer sur le bouton "sans avoir" ou "confirmer annulation" (formulaire avec with_credit_note=0)
      // Click the "without credit note" or "confirm cancellation" button (form with with_credit_note=0)
      const withoutCNForm = page.locator('form:has(input[value="0"])');
      const confirmButton = withoutCNForm.locator('button[type="submit"]');
      await expect(confirmButton).toBeVisible({ timeout: 5000 });
      await confirmButton.click();
      await page.waitForLoadState('networkidle');

      // Verifier le message de succes
      // Check success message
      const resultContent = await page.innerText('body');
      expect(
        resultContent.toLowerCase().includes('cancelled') ||
        resultContent.toLowerCase().includes('annul')
      ).toBeTruthy();
      console.log('✓ Membership cancelled / Adhesion annulee');
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
      console.log(`✓ ${rowCount} LigneArticle row(s) in admin after cancel / ligne(s) apres annulation`);

      const bodyText = await page.innerText('body');
      // Log les statuts visibles pour verification manuelle
      // Log visible statuses for manual check
      const statusLabels = ['CONFIRMED', 'CREDIT NOTE', 'FREE BOOKING', 'CANCELLED', 'Confirmed', 'Credit note'];
      const foundStatuses = statusLabels.filter(s => bodyText.includes(s));
      console.log('LigneArticle statuses found:', foundStatuses.join(', '));
    });
  });

  test('should show credit note option for paid membership / doit proposer avoir pour adhesion payee', async ({ page, request }) => {
    const paidEmail = `jturbeaux+cancp${randomId}@pm.me`;

    // Creer un produit payant + adhesion en attente
    // Create paid product + pending membership
    const paidProductName = `Adhesion Annul Paid ${randomId}`;

    const paidProduct = await createProduct({
      request,
      name: paidProductName,
      description: 'Test annulation avec avoir',
      category: 'Membership',
      offers: [{
        name: 'Annuel payant',
        price: '30.00',
        subscriptionType: 'Y',
        manualValidation: true,
      }],
    });
    expect(paidProduct.ok).toBeTruthy();
    const paidPriceUuid = paidProduct.offers?.[0]?.identifier || '';

    // Creer l'adhesion en ADMIN_WAITING
    const msResult = await createMembershipApi({
      request,
      priceUuid: paidPriceUuid,
      email: paidEmail,
      firstName: 'Pierre',
      lastName: 'Payeur',
      status: 'AW',
    });
    expect(msResult.ok).toBeTruthy();

    await loginAsAdmin(page);

    let membershipPk = '';

    // Recuperer le PK et ajouter un paiement
    // Get PK and add payment
    await test.step('Get PK and pay / Recuperer PK et payer', async () => {
      const result = djangoShell(`
from BaseBillet.models import Membership
m = Membership.objects.filter(user__email='${paidEmail}').first()
if m: print(f'pk={m.pk}')
else: print('NOT_FOUND')
`);
      expect(result).not.toContain('NOT_FOUND');
      const pkMatch = result.match(/pk=(\d+)/);
      expect(pkMatch).not.toBeNull();
      membershipPk = pkMatch![1];

      // Ajouter un paiement pour creer des lignes de vente
      // Add a payment to create sale lines
      await page.goto(`/admin/BaseBillet/membership/${membershipPk}/ajouter_paiement/`);
      await page.waitForLoadState('networkidle');

      const methodSelect = page.locator('[data-testid="membership-payment-method"]');
      await methodSelect.selectOption('CA'); // Cash

      const submitButton = page.locator('[data-testid="membership-payment-submit"]');
      await submitButton.click();
      await page.waitForLoadState('networkidle');
      console.log('✓ Payment added / Paiement ajoute');
    });

    // Aller sur la page d'annulation
    // Go to cancel page
    await test.step('Go to cancel page / Aller sur la page d\'annulation', async () => {
      await page.goto(`/admin/BaseBillet/membership/${membershipPk}/cancel/`);
      await page.waitForLoadState('networkidle');
    });

    // Verifier la page de confirmation avec les 2 boutons
    // Check confirmation page with 2 buttons
    await test.step('Verify credit note option / Verifier option avoir', async () => {
      const pageContent = await page.innerText('body');

      // Le bouton "Annuler et creer un avoir" doit etre visible
      // "Cancel and create credit note" button should be visible
      expect(
        pageContent.toLowerCase().includes('cancel and create credit note') ||
        pageContent.toLowerCase().includes('annuler et creer un avoir')
      ).toBeTruthy();

      // Le bouton "Annuler sans avoir" doit aussi etre visible
      // "Cancel without credit note" button should also be visible
      expect(
        pageContent.toLowerCase().includes('cancel without credit note') ||
        pageContent.toLowerCase().includes('annuler sans avoir')
      ).toBeTruthy();

      console.log('✓ Both cancel options shown / Les 2 options d\'annulation affichees');
    });

    // Annuler avec avoir / Cancel with credit note
    await test.step('Cancel with credit note / Annuler avec avoir', async () => {
      // Trouver le formulaire avec with_credit_note=1
      // Find the form with with_credit_note=1
      const withCNForm = page.locator('form:has(input[value="1"])');
      const withCNButton = withCNForm.locator('button[type="submit"]');
      await expect(withCNButton).toBeVisible({ timeout: 5000 });
      await withCNButton.click();
      await page.waitForLoadState('networkidle');

      // Verifier le message de succes mentionnant les avoirs
      // Check success message mentioning credit notes
      const pageContent = await page.innerText('body');
      expect(
        pageContent.toLowerCase().includes('credit note') ||
        pageContent.toLowerCase().includes('avoir') ||
        pageContent.toLowerCase().includes('cancelled') ||
        pageContent.toLowerCase().includes('annul')
      ).toBeTruthy();
      console.log('✓ Membership cancelled with credit notes / Adhesion annulee avec avoirs');
    });

    // Verifier en base qu'un avoir existe
    // Verify in DB that a credit note exists
    await test.step('Verify credit note in DB / Verifier avoir en base', async () => {
      const result = djangoShell(`
from BaseBillet.models import LigneArticle
cn = LigneArticle.objects.filter(
    membership__user__email='${paidEmail}',
    status='N'
).count()
print(f'credit_notes={cn}')
`);
      expect(result).toContain('credit_notes=');
      const match = result.match(/credit_notes=(\d+)/);
      expect(match).not.toBeNull();
      expect(parseInt(match![1])).toBeGreaterThanOrEqual(1);
      console.log('✓ Credit note confirmed in DB / Avoir confirme en base');
    });

    // Verifier les lignes de vente dans l'admin apres annulation avec avoir
    // Check sale lines in admin after cancel with credit note
    await test.step('Check LigneArticle in admin after cancel / Verifier les ventes apres annulation', async () => {
      await page.goto('/admin/BaseBillet/lignearticle/');
      await page.waitForLoadState('networkidle');

      const searchInput = page.locator('input[name="q"]').first();
      await searchInput.fill(paidProductName);
      await searchInput.press('Enter');
      await page.waitForLoadState('networkidle');

      const rows = page.locator('#result_list tbody tr');
      const rowCount = await rows.count();
      expect(rowCount).toBeGreaterThanOrEqual(2); // ligne originale + avoir
      console.log(`✓ ${rowCount} LigneArticle row(s) in admin / ligne(s) trouvee(s)`);

      const bodyText = await page.innerText('body');
      const hasCreditNote = bodyText.includes('CREDIT NOTE') || bodyText.includes('Credit note') || bodyText.includes('Avoir');
      expect(hasCreditNote).toBeTruthy();
      console.log('✓ CREDIT NOTE line visible in admin after cancel / Ligne AVOIR visible');
    });
  });
});
