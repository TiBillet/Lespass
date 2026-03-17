import { test, expect } from '@playwright/test';
import { loginAsAdmin } from '../utils/auth';
import { createProduct, createMembershipApi } from '../utils/api';
import { execSync } from 'child_process';

/**
 * TEST: Cancel membership with optional credit note from admin
 * TEST : Annulation adhesion avec option avoir depuis l'admin
 *
 * Nouveau flux (v1.7.7) :
 * Le bouton "Annuler l'adhésion" est dans le panneau HTMX inline.
 * Plus de page intermédiaire — le formulaire de confirmation apparait inline.
 * Après confirmation, HX-Redirect vers la changelist.
 *
 * New flow (v1.7.7):
 * The "Cancel membership" button is in the inline HTMX panel.
 * No intermediate page — confirmation form appears inline.
 * After confirmation, HX-Redirect to changelist.
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

    // Creer une adhesion gratuite (passe directement en VALID/ONCE via signal)
    // Create a free membership (goes directly to VALID/ONCE via signal)
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

    // Recuperer le PK directement en base
    // Get PK directly from DB
    let membershipPk = '';
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

    // Naviguer vers la fiche admin de l'adhesion (la page change)
    // Navigate to the membership admin change page
    await test.step('Go to membership change page / Aller sur la fiche adhesion', async () => {
      await page.goto(`/admin/BaseBillet/membership/${membershipPk}/change/`);
      await page.waitForLoadState('networkidle');
      console.log('✓ Sur la fiche admin de l\'adhesion');
    });

    // Cliquer sur "Annuler l'adhesion" dans le panneau HTMX
    // Click "Annuler l'adhesion" in the HTMX panel
    await test.step('Click cancel button in HTMX panel / Clic bouton annulation dans le panneau', async () => {
      const cancelButton = page.locator('[data-testid="membership-action-cancel"]');
      await expect(cancelButton).toBeVisible({ timeout: 5000 });
      await cancelButton.click();

      // Attendre que le formulaire de confirmation s'affiche inline
      // Wait for confirmation form to appear inline
      const cancelForm = page.locator('[data-testid="membership-cancel-form"]');
      await expect(cancelForm).toBeVisible({ timeout: 5000 });
      console.log('✓ Formulaire de confirmation inline visible');
    });

    // Confirmer l'annulation sans avoir
    // Confirm cancellation without credit note
    await test.step('Confirm cancellation / Confirmer l\'annulation', async () => {
      // L'email de l'adherent doit apparaitre dans le formulaire
      // Member email should appear in the form
      const formContent = await page.locator('[data-testid="membership-cancel-form"]').innerText();
      expect(formContent).toContain(userEmail);

      // Cliquer sur le bouton de confirmation (sans avoir)
      // Click the confirmation button (without credit note)
      const confirmButton = page.locator('[data-testid="membership-cancel-confirm"]');
      await expect(confirmButton).toBeVisible({ timeout: 5000 });
      await confirmButton.click();

      // Apres HX-Redirect, on arrive sur la changelist
      // After HX-Redirect, we land on the changelist
      await page.waitForURL('**/BaseBillet/membership/**', { timeout: 10000 });
      console.log('✓ Redirige vers la changelist apres annulation');

      const pageContent = await page.innerText('body');
      expect(
        pageContent.toLowerCase().includes('annul') ||
        pageContent.toLowerCase().includes('cancelled') ||
        pageContent.toLowerCase().includes('canceled')
      ).toBeTruthy();
      console.log('✓ Adhesion annulee avec succes');
    });
  });

  test('should show credit note option for paid membership / doit proposer avoir pour adhesion payee', async ({ page, request }) => {
    const paidEmail = `jturbeaux+cancp${randomId}@pm.me`;

    // Creer un produit payant + adhesion en attente
    // Create paid product + pending membership
    const paidProductName = `Adhesion Annul Paid ${randomId}`;

    let paidPriceUuid = '';

    await test.step('Create paid product and pending membership / Creer produit payant et adhesion en attente', async () => {
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
      paidPriceUuid = paidProduct.offers?.[0]?.identifier || '';

      const msResult = await createMembershipApi({
        request,
        priceUuid: paidPriceUuid,
        email: paidEmail,
        firstName: 'Pierre',
        lastName: 'Payeur',
        status: 'AW',
      });
      expect(msResult.ok).toBeTruthy();
    });

    await loginAsAdmin(page);

    // Recuperer le PK et naviguer vers la fiche
    // Get PK and navigate to change page
    let membershipPk = '';
    await test.step('Get PK and navigate / Recuperer PK et naviguer', async () => {
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
      console.log(`✓ Membership PK: ${membershipPk}`);

      await page.goto(`/admin/BaseBillet/membership/${membershipPk}/change/`);
      await page.waitForLoadState('networkidle');
    });

    // Ajouter un paiement via le panneau HTMX
    // Add a payment via the HTMX panel
    await test.step('Add payment via HTMX panel / Ajouter un paiement via le panneau HTMX', async () => {
      const payButton = page.locator('[data-testid="membership-action-ajouter-paiement"]');
      await expect(payButton).toBeVisible({ timeout: 5000 });
      await payButton.click();

      const form = page.locator('[data-testid="membership-paiement-form"]');
      await expect(form).toBeVisible({ timeout: 5000 });

      // Selectionner "Especes" et soumettre
      // Select "Cash" and submit
      const methodSelect = page.locator('[data-testid="membership-payment-method"]');
      await methodSelect.selectOption('CA'); // Cash

      const submitButton = page.locator('[data-testid="membership-payment-submit"]');
      await submitButton.click();

      // Attendre le succes inline
      // Wait for inline success
      const successArea = page.locator('[data-testid="membership-paiement-success"]');
      await expect(successArea).toBeVisible({ timeout: 10000 });
      console.log('✓ Paiement ajoute via HTMX');
    });

    // Cliquer sur "Annuler l'adhesion" dans le panneau
    // Click "Annuler l'adhesion" in the panel
    await test.step('Click cancel button / Cliquer sur annuler', async () => {
      const cancelButton = page.locator('[data-testid="membership-action-cancel"]');
      await expect(cancelButton).toBeVisible({ timeout: 5000 });
      await cancelButton.click();

      const cancelForm = page.locator('[data-testid="membership-cancel-form"]');
      await expect(cancelForm).toBeVisible({ timeout: 5000 });
      console.log('✓ Formulaire de confirmation annulation inline visible');
    });

    // Verifier les 2 options et choisir "avec avoir"
    // Check 2 options and choose "with credit note"
    await test.step('Verify credit note option and cancel with credit note / Verifier option avoir et annuler', async () => {
      const formContent = await page.locator('[data-testid="membership-cancel-form"]').innerText();

      // Les 2 boutons doivent etre visibles (sans avoir + avec avoir)
      // Both buttons must be visible (without + with credit note)
      expect(
        formContent.toLowerCase().includes('avoir') ||
        formContent.toLowerCase().includes('credit note') ||
        formContent.toLowerCase().includes('annuler avec avoir') ||
        formContent.toLowerCase().includes('cancel with credit note')
      ).toBeTruthy();
      console.log('✓ Option avoir visible');

      // Cliquer sur "Annuler avec avoir"
      // Click "Cancel with credit note"
      const withCNButton = page.locator('[data-testid="membership-cancel-with-credit-note"]');
      await expect(withCNButton).toBeVisible({ timeout: 5000 });
      await withCNButton.click();

      // Apres HX-Redirect, on arrive sur la changelist
      // After HX-Redirect, we land on the changelist
      await page.waitForURL('**/BaseBillet/membership/**', { timeout: 10000 });
      console.log('✓ Redirige vers la changelist apres annulation avec avoir');
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
      console.log('✓ Avoir confirme en base');
    });
  });
});
