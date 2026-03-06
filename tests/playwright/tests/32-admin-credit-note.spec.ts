import { test, expect } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';
import { createEvent, createProduct, createMembershipApi } from './utils/api';
import { execSync } from 'child_process';

/**
 * TEST: Credit note (avoir) on LigneArticle from admin
 * TEST : Avoir comptable sur LigneArticle depuis l'admin
 *
 * Scenarios :
 * 1. Emettre un avoir sur une ligne VALID -> succes, ligne negative creee
 * 2. Tenter un 2e avoir sur la meme ligne -> erreur "already exists"
 *
 * Strategie : on cree une adhesion gratuite (qui genere une LigneArticle VALID),
 * puis on emet un avoir dessus depuis la changelist admin.
 * Strategy: create a free membership (which generates a VALID LigneArticle),
 * then issue a credit note from the admin changelist.
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

test.describe('Admin Credit Note / Avoir comptable admin', () => {

  let productName: string;
  let priceUuid: string;
  const userEmail = `jturbeaux+cn${randomId}@pm.me`;

  test.beforeAll(async ({ request }) => {
    // Creer un produit adhesion gratuit qui genere une LigneArticle VALID
    // Create a free membership product that generates a VALID LigneArticle
    productName = `Adhesion CN ${randomId}`;

    const productResult = await createProduct({
      request,
      name: productName,
      description: 'Produit pour test avoir',
      category: 'Membership',
      offers: [{ name: 'Gratuit CN', price: '0.00', subscriptionType: 'Y' }],
    });
    expect(productResult.ok).toBeTruthy();
    priceUuid = productResult.offers?.[0]?.identifier || '';
    expect(priceUuid).not.toBe('');

    // Creer une adhesion gratuite -> genere une LigneArticle VALID
    // Create a free membership -> generates a VALID LigneArticle
    const msResult = await createMembershipApi({
      request,
      priceUuid,
      email: userEmail,
      firstName: 'Credit',
      lastName: 'Note',
      paymentMode: 'FREE',
    });
    expect(msResult.ok).toBeTruthy();
  });

  test('should create and block duplicate credit note / doit creer et bloquer avoir en double', async ({ page }) => {
    await loginAsAdmin(page);

    let lignePk = '';

    // Etape 1 : Recuperer le PK de la LigneArticle VALID en base
    // Step 1: Get the PK of the VALID LigneArticle from DB
    await test.step('Get LigneArticle PK / Recuperer le PK de la LigneArticle', async () => {
      const result = djangoShell(`
from BaseBillet.models import LigneArticle
ligne = LigneArticle.objects.filter(
    membership__user__email='${userEmail}',
    status__in=['V', 'P']
).first()
if not ligne:
    ligne = LigneArticle.objects.filter(membership__user__email='${userEmail}').first()
    if ligne:
        ligne.status = 'V'
        ligne.save(update_fields=['status'])
if ligne:
    print(f'pk={ligne.pk}')
    print(f'status={ligne.status}')
else:
    print('NOT_FOUND')
`);
      console.log('DB LigneArticle:', result);
      expect(result).not.toContain('NOT_FOUND');
      const pkMatch = result.match(/pk=(.+)/);
      expect(pkMatch).not.toBeNull();
      lignePk = pkMatch![1].trim();
      console.log(`✓ LigneArticle PK: ${lignePk}`);
    });

    // Etape 2 : Appeler directement l'URL emettre_avoir
    // Step 2: Call the emettre_avoir URL directly
    await test.step('Issue credit note via URL / Emettre avoir via URL', async () => {
      await page.goto(`/admin/BaseBillet/lignearticle/${lignePk}/emettre_avoir/`);
      await page.waitForLoadState('networkidle');

      // Verifier le message de succes sur la page de retour
      // Check success message on the return page
      const pageContent = await page.innerText('body');
      expect(
        pageContent.toLowerCase().includes('credit note created') ||
        pageContent.toLowerCase().includes('avoir cr')
      ).toBeTruthy();
      console.log('✓ Credit note created successfully / Avoir cree avec succes');
    });

    // Etape 3 : Verifier en base qu'on a bien une ligne CREDIT_NOTE
    // Step 3: Verify in DB we have a CREDIT_NOTE line
    await test.step('Verify credit note in DB / Verifier avoir en base', async () => {
      const result = djangoShell(`
from BaseBillet.models import LigneArticle
cn = LigneArticle.objects.filter(
    credit_note_for__membership__user__email='${userEmail}',
    status='N'
)
for l in cn:
    print(f'cn_pk={l.pk} qty={l.qty} status={l.status}')
print(f'count={cn.count()}')
`);
      expect(result).toContain('count=1');
      expect(result).toContain('qty=-');
      console.log('✓ Credit note confirmed in DB / Avoir confirme en base');
    });

    // Etape 3b : Verifier les lignes de vente dans l'admin
    // Step 3b: Check sale lines in admin
    await test.step('Check LigneArticle in admin / Verifier les ventes dans l\'admin', async () => {
      await page.goto('/admin/BaseBillet/lignearticle/');
      await page.waitForLoadState('networkidle');

      const searchInput = page.locator('input[name="q"]').first();
      await searchInput.fill(productName);
      await searchInput.press('Enter');
      await page.waitForLoadState('networkidle');

      const rows = page.locator('#result_list tbody tr');
      const rowCount = await rows.count();
      expect(rowCount).toBeGreaterThanOrEqual(2); // ligne originale + avoir
      console.log(`✓ ${rowCount} LigneArticle rows found in admin / lignes trouvees`);

      // Verifier qu'on a une ligne Confirmed et une ligne Credit note
      // Check we have a Confirmed line and a Credit note line
      const bodyText = await page.innerText('body');
      // Unfold affiche les badges en majuscules : CONFIRMED, CREDIT NOTE
      // Unfold displays badges in uppercase: CONFIRMED, CREDIT NOTE
      const hasConfirmed = bodyText.includes('CONFIRMED') || bodyText.includes('Confirmed') || bodyText.includes('Confirmé');
      const hasCreditNote = bodyText.includes('CREDIT NOTE') || bodyText.includes('Credit note') || bodyText.includes('Avoir');
      expect(hasConfirmed).toBeTruthy();
      expect(hasCreditNote).toBeTruthy();
      console.log('✓ CONFIRMED + CREDIT NOTE lines visible in admin / Lignes visibles');
    });

    // Etape 4 : Tenter un 2e avoir -> erreur "already exists"
    // Step 4: Try a 2nd credit note -> error "already exists"
    await test.step('Try duplicate credit note / Tenter un avoir en double', async () => {
      await page.goto(`/admin/BaseBillet/lignearticle/${lignePk}/emettre_avoir/`);
      await page.waitForLoadState('networkidle');

      const pageContent = await page.innerText('body');
      const isBlocked = pageContent.toLowerCase().includes('already exists') ||
                        pageContent.toLowerCase().includes('existe deja');
      expect(isBlocked).toBeTruthy();
      console.log('✓ Duplicate credit note blocked / Avoir en double bloque');
    });
  });
});
