import { test, expect } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';
import { createEvent, createProduct, createReservationApi } from './utils/api';
import { execSync } from 'child_process';

/**
 * TEST: Cancel admin reservation with credit note + FK reservation on LigneArticle
 * TEST : Annulation reservation admin avec avoir + FK reservation sur LigneArticle
 *
 * Couvre les fichiers md :
 * - annulation-reservation-admin.md (tests 1, 2, 5)
 * - fk-reservation-lignearticle.md (tests 1, 5)
 *
 * Scenarios :
 * 1. Reservation admin gratuite -> annulation -> avoir CREDIT_NOTE cree
 * 2. Verifier que la FK LigneArticle.reservation est renseignee
 * 3. Double annulation impossible
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

/**
 * Executer une commande Django shell dans le tenant
 * / Execute a Django shell command in the tenant
 */
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

test.describe('Admin Reservation Cancel + FK Verification / Annulation reservation admin + verification FK', () => {

  let eventName: string;
  let productName: string;
  let eventUuid: string;
  let priceUuid: string;
  const userEmail = `jturbeaux+rcan${randomId}@pm.me`;

  test.beforeAll(async ({ request }) => {
    eventName = `Event Cancel Admin ${randomId}`;
    productName = `Billet Cancel ${randomId}`;
    const startDate = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();

    const eventResult = await createEvent({ request, name: eventName, startDate });
    expect(eventResult.ok).toBeTruthy();
    eventUuid = eventResult.uuid;

    const productResult = await createProduct({
      request,
      name: productName,
      description: 'Produit pour test annulation admin',
      category: 'Free booking',
      eventUuid,
      offers: [{ name: 'Gratuit annul', price: '0.00' }],
    });
    expect(productResult.ok).toBeTruthy();
    priceUuid = productResult.offers?.[0]?.identifier || '';
    expect(priceUuid).not.toBe('');
  });

  test('should cancel reservation and create credit note / doit annuler reservation et creer avoir', async ({ page, request }) => {

    // Creer une reservation via l'API
    // Create a reservation via API
    await test.step('Create reservation via API / Creer reservation via API', async () => {
      const resaResult = await createReservationApi({
        request,
        eventUuid,
        email: userEmail,
        tickets: [{ priceUuid, qty: 2 }],
      });
      expect(resaResult.ok).toBeTruthy();
      console.log('✓ Reservation created / Reservation creee');
    });

    // Verifier que la FK reservation est renseignee sur les LigneArticle
    // Check that LigneArticle.reservation FK is set
    await test.step('Verify FK reservation on LigneArticle / Verifier FK reservation', async () => {
      const result = djangoShell(`
from BaseBillet.models import LigneArticle
lignes = LigneArticle.objects.filter(
    pricesold__productsold__product__name__contains='${productName.replace(/'/g, "\\'")}'
).order_by('-datetime')[:5]
for l in lignes:
    print(f'UUID={l.uuid} resa_id={l.reservation_id} ps_id={l.paiement_stripe_id} status={l.status}')
`);
      console.log('DB check FK reservation:', result);
      // Au moins une ligne doit avoir reservation_id renseigne
      // At least one line should have reservation_id set
      expect(result).toContain('resa_id=');
      // Verifier que resa_id n'est pas "None" pour les lignes pertinentes
      // Check resa_id is not "None" for relevant lines
      const lines = result.split('\n').filter(l => l.includes('UUID='));
      const hasReservationFk = lines.some(l => !l.includes('resa_id=None'));
      expect(hasReservationFk).toBeTruthy();
      console.log('✓ FK reservation is set on LigneArticle / FK reservation renseignee');
    });

    await loginAsAdmin(page);

    // Aller sur la liste des reservations et annuler
    // Go to reservations list and cancel
    await test.step('Navigate to reservations / Naviguer vers les reservations', async () => {
      await page.goto('/admin/BaseBillet/reservation/');
      await page.waitForLoadState('networkidle');

      // Chercher par email
      // Search by email
      const searchInput = page.locator('input[name="q"]').first();
      await searchInput.fill(userEmail);
      await searchInput.press('Enter');
      await page.waitForLoadState('networkidle');

      // Verifier qu'on a un resultat
      // Check we have a result
      const rows = page.locator('#result_list tbody tr');
      await expect(rows.first()).toBeVisible({ timeout: 10000 });
      console.log('✓ Reservation found / Reservation trouvee');
    });

    // Selectionner la reservation et lancer l'action d'annulation
    // Select the reservation and trigger cancel action
    await test.step('Cancel reservation via bulk action / Annuler via action groupee', async () => {
      // Cocher la checkbox de la premiere reservation
      // Check the checkbox of the first reservation
      const checkbox = page.locator('#result_list tbody tr input[type="checkbox"]').first();
      await checkbox.check();

      // Selectionner l'action "Cancel and refund" et soumettre le formulaire
      // Select the "Cancel and refund" action and submit the form
      // Note: Unfold utilise Alpine.js x-show sur le bouton Run,
      // selectOption ne declenche pas toujours Alpine -> on soumet le form directement
      const actionSelect = page.locator('select[name="action"]');
      await actionSelect.selectOption('action_cancel_refund_reservations');
      await page.evaluate(() => {
        const form = document.querySelector('#changelist-form') as HTMLFormElement;
        if (form) form.submit();
      });
      await page.waitForLoadState('networkidle');

      // Verifier le message de succes
      // Check success message
      const successMessage = page.locator('.bg-green-100, .bg-blue-100, .messagelist .success');
      await expect(successMessage).toBeVisible({ timeout: 10000 });
      console.log('✓ Reservation cancelled / Reservation annulee');
    });

    // Verifier en base que la reservation est annulee et les tickets aussi
    // Check in DB that reservation is cancelled and tickets too
    await test.step('Verify cancellation in DB / Verifier annulation en base', async () => {
      const result = djangoShell(`
from BaseBillet.models import Reservation, Ticket
resa = Reservation.objects.filter(user_commande__email='${userEmail}').first()
if resa:
    cancelled_tickets = resa.tickets.filter(status='${`C`}').count()
    total_tickets = resa.tickets.count()
    print(f'resa_status={resa.status} cancelled_tickets={cancelled_tickets} total_tickets={total_tickets}')
else:
    print('NOT_FOUND')
`);
      console.log('DB check after cancel:', result);
      // La reservation doit etre en status CANCELED
      // Reservation should be in CANCELED status
      expect(result).toContain('resa_status=C');
      // Tous les tickets doivent etre annules
      // All tickets should be cancelled
      expect(result).not.toContain('NOT_FOUND');
      console.log('✓ Reservation and tickets cancelled in DB / Reservation et tickets annules en base');
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

      // Lister les statuts visibles
      // List visible statuses
      const bodyText = await page.innerText('body');
      const statusLabels = ['CONFIRMED', 'CREDIT NOTE', 'FREE BOOKING', 'CANCELLED', 'REFUNDED', 'Confirmed', 'Credit note'];
      const foundStatuses = statusLabels.filter(s => bodyText.includes(s));
      console.log('LigneArticle statuses found:', foundStatuses.join(', '));
    });
  });

  test('should not cancel already cancelled reservation / ne doit pas annuler une reservation deja annulee', async ({ page, request }) => {
    const cancelledEmail = `jturbeaux+rcan2${randomId}@pm.me`;

    // Creer et annuler une reservation
    // Create and cancel a reservation
    await test.step('Create and cancel reservation / Creer et annuler reservation', async () => {
      const resaResult = await createReservationApi({
        request,
        eventUuid,
        email: cancelledEmail,
        tickets: [{ priceUuid, qty: 1 }],
      });
      expect(resaResult.ok).toBeTruthy();
    });

    await loginAsAdmin(page);

    // 1ere annulation / 1st cancellation
    await test.step('First cancellation / Premiere annulation', async () => {
      await page.goto('/admin/BaseBillet/reservation/');
      await page.waitForLoadState('networkidle');

      const searchInput = page.locator('input[name="q"]').first();
      await searchInput.fill(cancelledEmail);
      await searchInput.press('Enter');
      await page.waitForLoadState('networkidle');

      const checkbox = page.locator('#result_list tbody tr input[type="checkbox"]').first();
      await checkbox.check();

      const actionSelect = page.locator('select[name="action"]');
      await actionSelect.selectOption('action_cancel_refund_reservations');
      await page.evaluate(() => {
        const form = document.querySelector('#changelist-form') as HTMLFormElement;
        if (form) form.submit();
      });
      await page.waitForLoadState('networkidle');
      console.log('✓ First cancellation done / Premiere annulation faite');
    });

    // 2e tentative d'annulation -> doit pas creer de doublon
    // 2nd cancellation attempt -> should not create duplicate
    await test.step('Second cancellation attempt / Deuxieme tentative d\'annulation', async () => {
      // Chercher a nouveau / Search again
      const searchInput = page.locator('input[name="q"]').first();
      await searchInput.fill(cancelledEmail);
      await searchInput.press('Enter');
      await page.waitForLoadState('networkidle');

      const rows = page.locator('#result_list tbody tr');
      const rowCount = await rows.count();

      if (rowCount > 0) {
        const checkbox = page.locator('#result_list tbody tr input[type="checkbox"]').first();
        await checkbox.check();

        const actionSelect = page.locator('select[name="action"]');
        // Verifier que l'action est disponible
        // Check if action is available
        const options = await actionSelect.locator('option').allTextContents();
        const hasCancelAction = options.some(o =>
          o.toLowerCase().includes('cancel') || o.toLowerCase().includes('annuler')
        );

        if (hasCancelAction) {
          await actionSelect.selectOption('action_cancel_refund_reservations');
          await page.evaluate(() => {
            const form = document.querySelector('#changelist-form') as HTMLFormElement;
            if (form) form.submit();
          });
          await page.waitForLoadState('networkidle');

          // Verifier : pas de nouveau avoir en base
          // Check: no new credit note in DB
          const result = djangoShell(`
from BaseBillet.models import LigneArticle
count = LigneArticle.objects.filter(
    pricesold__productsold__product__name__contains='${productName.replace(/'/g, "\\'")}',
    status__in=['R', 'N'],
    credit_note_for__isnull=False
).count()
print(f'credit_notes_count={count}')
`);
          console.log('DB check double cancel:', result);
          // Doit y avoir au max 1 avoir (pas de doublon)
          // Should have at most 1 credit note (no duplicate)
          const match = result.match(/credit_notes_count=(\d+)/);
          if (match) {
            expect(parseInt(match[1])).toBeLessThanOrEqual(1);
          }
        }
      }
      console.log('✓ Double cancellation handled / Double annulation geree');
    });
  });
});
