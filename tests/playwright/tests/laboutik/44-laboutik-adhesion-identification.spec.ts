import { test, expect } from '@playwright/test';
import { loginAsAdmin } from '../utils/auth';
import { execSync } from 'child_process';

/**
 * TEST: LaBoutik POS — Flow adhesion avec identification obligatoire (6 chemins)
 * TEST: LaBoutik POS — Membership flow with mandatory identification (6 paths)
 *
 * LOCALISATION : tests/playwright/tests/44-laboutik-adhesion-identification.spec.ts
 *
 * Les 6 chemins de l'arbre de decision :
 * 1. CASHLESS → NFC → carte avec user → confirmation → PAYER
 * 2. CASHLESS → NFC → carte anonyme → formulaire email → confirmation → PAYER
 * 3. ESPECE/CB → "Scanner carte" → NFC → carte avec user → confirmation → PAYER
 * 4. ESPECE/CB → "Scanner carte" → NFC → carte anonyme → formulaire → PAYER
 * 5. ESPECE/CB → "Saisir email" → formulaire → confirmation → PAYER
 * 6. Garde serveur : refus si email absent
 *
 * The 6 decision tree paths:
 * 1. CASHLESS → NFC → card with user → confirmation → PAY
 * 2. CASHLESS → NFC → anonymous card → email form → confirmation → PAY
 * 3. CASH/CB → "Scan card" → NFC → card with user → confirmation → PAY
 * 4. CASH/CB → "Scan card" → NFC → anonymous card → form → PAY
 * 5. CASH/CB → "Enter email" → form → confirmation → PAY
 * 6. Server guard: refuse if no email
 *
 * Prerequis :
 * - La commande `create_test_pos_data` doit avoir ete lancee
 * - Le PV "Adhesions" (type A) doit exister
 * - Les cartes de simulation doivent exister (52BE6543 anonyme, 33BC1DAA)
 */

const DEMO_TAGID_CM = process.env.DEMO_TAGID_CM || 'A49E8E2A';
// Carte client 1 : anonyme (pas de user)
// / Client card 1: anonymous (no user)
const DEMO_TAGID_CLIENT1 = process.env.DEMO_TAGID_CLIENT1 || '52BE6543';
// Carte client 3 "jetable" : remise a zero avant chaque suite de tests.
// En debut de test, on lui assigne un user pour tester "carte avec user",
// puis on la reset en afterAll pour le prochain run.
// / Client card 3 "disposable": reset before each test suite.
// At test start, we assign a user to test "card with user",
// then reset it in afterAll for the next run.
const DEMO_TAGID_CLIENT3 = process.env.DEMO_TAGID_CLIENT3 || 'D74B1B5D';

/**
 * Execute du code Python dans le shell Django du tenant lespass
 * Executes Python code in the Django shell for the lespass tenant
 */
function djangoShell(pythonCode: string): string {
  const escaped = pythonCode.replace(/"/g, '\\"');
  const command = `docker exec lespass_django poetry run python /DjangoFiles/manage.py tenant_command shell -s lespass -c "${escaped}"`;
  try {
    return execSync(command, { encoding: 'utf-8', timeout: 30000 }).trim();
  } catch (error: any) {
    console.error(`Django shell error: ${error.message}`);
    return '';
  }
}

/**
 * Helper : naviguer vers le PV Adhesions, ajouter "Adhesion POS Test" au panier, cliquer VALIDER
 * Helper: navigate to Adhesions POS, add "Adhesion POS Test" to cart, click VALIDATE
 */
async function naviguerEtAjouterAdhesion(page: any, adhesionPvUuid: string) {
  await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${adhesionPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
  await page.waitForLoadState('networkidle');

  // Cliquer sur "Adhesion POS Test" (mono-tarif, pas d'overlay)
  // / Click "Adhesion POS Test" (single rate, no overlay)
  const adhesionTile = page.locator('#products .article-container').filter({ hasText: 'Adhesion POS' }).first();
  await expect(adhesionTile).toBeVisible({ timeout: 10000 });
  await adhesionTile.click();
  await expect(page.locator('#addition-list')).toContainText('Adhesion POS', { timeout: 5000 });

  // Cliquer VALIDER → ecran choix paiement
  // / Click VALIDATE → payment choice screen
  await page.locator('#bt-valider').click();
  await expect(page.locator('[data-testid="paiement-moyens"]')).toBeVisible({ timeout: 10000 });
}

test.describe('LaBoutik POS — Adhesion identification obligatoire / Mandatory membership identification', () => {

  let adhesionPvUuid: string;
  const uniqueSuffix = Date.now().toString(36);

  test.beforeAll(async () => {
    // 1. Recuperer l'UUID du PV Adhesions
    // / 1. Fetch the Adhesions POS UUID
    const pvResult = djangoShell(`
from laboutik.models import PointDeVente
pv = PointDeVente.objects.filter(comportement='A').first()
if pv:
    print(f'uuid={pv.uuid}')
else:
    print('NOT_FOUND')
`);
    const uuidMatch = pvResult.match(/uuid=(.+)/);
    if (!uuidMatch) {
      throw new Error(`PV Adhesion introuvable. Resultat: ${pvResult}`);
    }
    adhesionPvUuid = uuidMatch[1].trim();
    console.log(`OK PV Adhesion UUID : ${adhesionPvUuid}`);

    // 2. Reset carte 1 (doit rester anonyme) au cas ou un run precedent lui a assigne un user
    // / 2. Reset card 1 (must stay anonymous) in case a previous run assigned a user
    djangoShell(`
from laboutik.utils.test_helpers import reset_carte
result = reset_carte('${DEMO_TAGID_CLIENT1}')
print(f'OK reset client1 beforeAll: {result}')
`);

    // 3. Reset carte 3 (jetable) puis lui assigner un user pour les tests NFC
    // / 3. Reset card 3 (disposable) then assign a user for NFC tests
    const setupResult = djangoShell(`
from laboutik.utils.test_helpers import reset_carte
from QrcodeCashless.models import CarteCashless
from AuthBillet.utils import get_or_create_user

# Reset d'abord (supprime tout user/wallet precedent)
reset_carte('${DEMO_TAGID_CLIENT3}')

# Assigner un user frais pour tester "carte avec user"
user = get_or_create_user('carte3-jetable-${uniqueSuffix}@tibillet.localhost', send_mail=False)
user.first_name = 'CarteJetable'
user.last_name = 'TestNFC'
user.save()
carte = CarteCashless.objects.get(tag_id='${DEMO_TAGID_CLIENT3}')
carte.user = user
carte.save()
print(f'OK reset+assigned {user.email} to {carte.tag_id}')
`);
    console.log('Card 3 setup:', setupResult);
  });

  test.afterAll(async () => {
    // Remettre les cartes 1 et 3 a zero pour le prochain run
    // Carte 1 : le chemin 2 lui associe un user (carte anonyme → formulaire → submit)
    // Carte 3 : le beforeAll lui associe un user (chemin 1)
    // / Reset cards 1 and 3 for the next run
    // Card 1: path 2 assigns a user (anonymous card → form → submit)
    // Card 3: beforeAll assigns a user (path 1)
    const resetResult1 = djangoShell(`
from laboutik.utils.test_helpers import reset_carte
result = reset_carte('${DEMO_TAGID_CLIENT1}')
print(f'OK reset client1: {result}')
`);
    console.log('Card 1 afterAll reset:', resetResult1);

    const resetResult3 = djangoShell(`
from laboutik.utils.test_helpers import reset_carte
result = reset_carte('${DEMO_TAGID_CLIENT3}')
print(f'OK reset client3: {result}')
`);
    console.log('Card 3 afterAll reset:', resetResult3);
  });

  // =========================================================================
  // CHEMIN 5 : ESPECE → "Saisir email" → formulaire → confirmation → PAYER
  // PATH 5: CASH → "Enter email" → form → confirmation → PAY
  // =========================================================================

  test('chemin 5 : espece → saisir email → confirmation → paiement', async ({ page }) => {
    const testEmail = `adh5-${uniqueSuffix}@example.com`;
    await loginAsAdmin(page);
    await naviguerEtAjouterAdhesion(page, adhesionPvUuid);

    // ESPECE → ecran identification
    // / CASH → identification screen
    await page.locator('[data-testid="adhesion-btn-especes"]').click();
    await expect(page.locator('[data-testid="adhesion-choose-id"]')).toBeVisible({ timeout: 10000 });

    // "Saisir email / nom" → formulaire
    // / "Enter email / name" → form
    await page.locator('[data-testid="adhesion-choose-email"]').click();
    await expect(page.locator('[data-testid="adhesion-form"]')).toBeVisible({ timeout: 10000 });

    // Remplir et valider
    // / Fill and validate
    await page.locator('[data-testid="adhesion-input-email"]').fill(testEmail);
    await page.locator('[data-testid="adhesion-input-prenom"]').fill('PrenomCinq');
    await page.locator('[data-testid="adhesion-input-nom"]').fill('NomCinq');
    await page.locator('[data-testid="adhesion-btn-valider"]').click();

    // Confirmation
    await expect(page.locator('[data-testid="adhesion-confirm"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="adhesion-confirm-user"]')).toContainText(testEmail);
    await expect(page.locator('[data-testid="adhesion-confirm-user"]')).toContainText('NOMCINQ');

    // Confirmer le paiement
    // / Confirm payment
    await page.locator('[data-testid="adhesion-btn-confirmer"]').click();
    await expect(page.locator('[data-testid="paiement-succes"]')).toBeVisible({ timeout: 15000 });

    // Verification en base
    // / DB verification
    const dbResult = djangoShell(`
from BaseBillet.models import Membership
from AuthBillet.models import TibilletUser
user = TibilletUser.objects.filter(email='${testEmail}').first()
if user:
    m = Membership.objects.filter(user=user).order_by('-date_added').first()
    if m:
        print(f'OK status={m.status} first={user.first_name} last={user.last_name}')
    else:
        print('NO_MEMBERSHIP')
else:
    print('NO_USER')
`);
    expect(dbResult).toContain('OK');
    console.log('OK chemin 5 : espece → email → confirm → paye. DB:', dbResult);
  });

  // =========================================================================
  // CHEMIN 5 bis : CB → "Saisir email" (verifie que CB route aussi vers identification)
  // PATH 5 bis: CB → "Enter email" (verifies CB also routes to identification)
  // =========================================================================

  test('chemin 5 bis : CB → saisir email → confirmation → paiement', async ({ page }) => {
    const testEmail = `adh5cb-${uniqueSuffix}@example.com`;
    await loginAsAdmin(page);
    await naviguerEtAjouterAdhesion(page, adhesionPvUuid);

    // CB → ecran identification
    // / CB → identification screen
    await page.locator('[data-testid="adhesion-btn-cb"]').click();
    await expect(page.locator('[data-testid="adhesion-choose-id"]')).toBeVisible({ timeout: 10000 });

    // "Saisir email / nom"
    await page.locator('[data-testid="adhesion-choose-email"]').click();
    await expect(page.locator('[data-testid="adhesion-form"]')).toBeVisible({ timeout: 10000 });

    // Remplir et valider
    await page.locator('[data-testid="adhesion-input-email"]').fill(testEmail);
    await page.locator('[data-testid="adhesion-input-prenom"]').fill('PrenomCB');
    await page.locator('[data-testid="adhesion-input-nom"]').fill('NomCB');
    await page.locator('[data-testid="adhesion-btn-valider"]').click();

    // Confirmation → paiement
    await expect(page.locator('[data-testid="adhesion-confirm"]')).toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="adhesion-btn-confirmer"]').click();
    await expect(page.locator('[data-testid="paiement-succes"]')).toBeVisible({ timeout: 15000 });

    console.log('OK chemin 5 bis : CB → email → confirm → paye');
  });

  // =========================================================================
  // CHEMIN 3 : ESPECE → "Scanner carte" → NFC carte avec user → confirmation → PAYER
  // PATH 3: CASH → "Scan card" → NFC card with user → confirmation → PAY
  // =========================================================================

  test('chemin 3 : espece → scanner carte (user connu) → confirmation → paiement', async ({ page }) => {
    await loginAsAdmin(page);
    await naviguerEtAjouterAdhesion(page, adhesionPvUuid);

    // ESPECE → ecran identification
    await page.locator('[data-testid="adhesion-btn-especes"]').click();
    await expect(page.locator('[data-testid="adhesion-choose-id"]')).toBeVisible({ timeout: 10000 });

    // "Scanner carte" → ecran NFC
    await page.locator('[data-testid="adhesion-choose-nfc"]').click();

    // Attendre les boutons de simulation NFC
    // / Wait for NFC simulation buttons
    await expect(page.locator('.nfc-reader-simu-bt').first()).toBeVisible({ timeout: 10000 });

    // Cliquer la carte CLIENT2 (33BC1DAA) qui a un user assigne
    // / Click CLIENT2 card (33BC1DAA) which has an assigned user
    await page.locator(`.nfc-reader-simu-bt[tag-id="${DEMO_TAGID_CLIENT3}"]`).click();

    // → identifier_membre recoit tag_id → trouve carte.user → ecran confirmation directe
    // / → identifier_membre receives tag_id → finds card.user → direct confirmation screen
    await expect(page.locator('[data-testid="adhesion-confirm"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="adhesion-confirm-user"]')).toContainText('carte3-jetable');
    await expect(page.locator('[data-testid="adhesion-confirm-user"]')).toContainText('TESTNFC');
    console.log('OK carte avec user → confirmation directe');

    // Confirmer le paiement
    await page.locator('[data-testid="adhesion-btn-confirmer"]').click();
    await expect(page.locator('[data-testid="paiement-succes"]')).toBeVisible({ timeout: 15000 });
    console.log('OK chemin 3 : espece → scanner carte (user) → confirm → paye');
  });

  // =========================================================================
  // CHEMIN 1 : CASHLESS → NFC carte avec user → confirmation → PAYER
  // PATH 1: CASHLESS → NFC card with user → confirmation → PAY
  // =========================================================================

  test('chemin 1 : cashless → NFC carte avec user → confirmation → paiement', async ({ page }) => {
    await loginAsAdmin(page);
    await naviguerEtAjouterAdhesion(page, adhesionPvUuid);

    // CASHLESS → ecran NFC adhesion directement (pas d'ecran choix identification)
    // / CASHLESS → NFC adhesion screen directly (no identification choice screen)
    await page.locator('[data-testid="adhesion-btn-nfc"]').click();

    // Attendre les boutons NFC et cliquer la carte CLIENT2 (avec user)
    await expect(page.locator('.nfc-reader-simu-bt').first()).toBeVisible({ timeout: 10000 });
    await page.locator(`.nfc-reader-simu-bt[tag-id="${DEMO_TAGID_CLIENT3}"]`).click();

    // → identifier_membre → carte avec user → confirmation directe
    // / → identifier_membre → card with user → direct confirmation
    await expect(page.locator('[data-testid="adhesion-confirm"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="adhesion-confirm-user"]')).toContainText('carte3-jetable');
    await expect(page.locator('[data-testid="adhesion-confirm-user"]')).toContainText('TESTNFC');
    console.log('OK chemin 1 : cashless → NFC → carte avec user → confirmation directe');
    // Note : on ne teste pas le paiement NFC ici (necessite solde tokens TLF).
    // Le paiement NFC est teste dans 39-laboutik-pos-paiement.spec.ts.
    // / Note: we don't test NFC payment here (requires TLF token balance).
    // NFC payment is tested in 39-laboutik-pos-paiement.spec.ts.
  });

  // =========================================================================
  // CHEMIN 2 : CASHLESS → NFC carte anonyme → formulaire → confirmation → PAYER
  // (doit passer AVANT chemin 4 — chemin 4 associe un user a CLIENT1)
  // PATH 2: CASHLESS → NFC anonymous card → form → confirmation → PAY
  // (must run BEFORE path 4 — path 4 assigns a user to CLIENT1)
  // =========================================================================

  test('chemin 2 : cashless → NFC carte anonyme → formulaire → confirmation → paiement', async ({ page }) => {
    const testEmail = `adh2-${uniqueSuffix}@example.com`;
    await loginAsAdmin(page);
    await naviguerEtAjouterAdhesion(page, adhesionPvUuid);

    // CASHLESS → NFC
    await page.locator('[data-testid="adhesion-btn-nfc"]').click();

    // Cliquer la carte CLIENT1 (anonyme)
    await expect(page.locator('.nfc-reader-simu-bt').first()).toBeVisible({ timeout: 10000 });
    await page.locator(`.nfc-reader-simu-bt[tag-id="${DEMO_TAGID_CLIENT1}"]`).click();

    // → carte anonyme → formulaire avec tag_id cache
    // / → anonymous card → form with hidden tag_id
    await expect(page.locator('[data-testid="adhesion-form"]')).toBeVisible({ timeout: 10000 });
    console.log('OK cashless carte anonyme → formulaire');

    // Remplir et valider → confirmation
    await page.locator('[data-testid="adhesion-input-email"]').fill(testEmail);
    await page.locator('[data-testid="adhesion-input-prenom"]').fill('PrenomDeux');
    await page.locator('[data-testid="adhesion-input-nom"]').fill('NomDeux');
    await page.locator('[data-testid="adhesion-btn-valider"]').click();

    // Confirmation affichee (l'email est bien celui saisi)
    // / Confirmation displayed (email matches what was entered)
    await expect(page.locator('[data-testid="adhesion-confirm"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="adhesion-confirm-user"]')).toContainText(testEmail);
    console.log('OK chemin 2 : cashless → carte anonyme → formulaire → confirmation');
    // Note : meme remarque que chemin 1 (pas de solde NFC pour le paiement final).
  });

  // =========================================================================
  // CHEMIN 4 : ESPECE → "Scanner carte" → NFC carte anonyme → formulaire → PAYER
  // (doit passer APRES chemin 2 — chemin 4 associe un user a CLIENT1)
  // PATH 4: CASH → "Scan card" → NFC anonymous card → form → PAY
  // (must run AFTER path 2 — path 4 assigns a user to CLIENT1)
  // =========================================================================

  test('chemin 4 : espece → scanner carte (anonyme) → formulaire → confirmation → paiement', async ({ page }) => {
    const testEmail = `adh4-${uniqueSuffix}@example.com`;
    await loginAsAdmin(page);
    await naviguerEtAjouterAdhesion(page, adhesionPvUuid);

    // ESPECE → identification → scanner carte
    await page.locator('[data-testid="adhesion-btn-especes"]').click();
    await expect(page.locator('[data-testid="adhesion-choose-id"]')).toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="adhesion-choose-nfc"]').click();

    // Attendre les boutons NFC et cliquer la carte CLIENT1 (52BE6543, anonyme)
    // / Wait for NFC buttons and click CLIENT1 card (52BE6543, anonymous)
    await expect(page.locator('.nfc-reader-simu-bt').first()).toBeVisible({ timeout: 10000 });
    await page.locator(`.nfc-reader-simu-bt[tag-id="${DEMO_TAGID_CLIENT1}"]`).click();

    // → identifier_membre recoit tag_id → carte sans user → formulaire avec tag_id cache
    // / → identifier_membre receives tag_id → card without user → form with hidden tag_id
    await expect(page.locator('[data-testid="adhesion-form"]')).toBeVisible({ timeout: 10000 });
    console.log('OK carte anonyme → formulaire affiche');

    // Remplir email/nom/prenom et valider
    await page.locator('[data-testid="adhesion-input-email"]').fill(testEmail);
    await page.locator('[data-testid="adhesion-input-prenom"]').fill('PrenomQuatre');
    await page.locator('[data-testid="adhesion-input-nom"]').fill('NomQuatre');
    await page.locator('[data-testid="adhesion-btn-valider"]').click();

    // Confirmation → paiement
    await expect(page.locator('[data-testid="adhesion-confirm"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="adhesion-confirm-user"]')).toContainText(testEmail);
    await page.locator('[data-testid="adhesion-btn-confirmer"]').click();
    await expect(page.locator('[data-testid="paiement-succes"]')).toBeVisible({ timeout: 15000 });

    console.log('OK chemin 4 : espece → carte anonyme → formulaire → confirm → paye');
  });

  // =========================================================================
  // BOUTON RETOUR — navigation arriere depuis chaque ecran
  // BACK BUTTON — backward navigation from each screen
  // =========================================================================

  test('bouton retour fonctionne depuis ecran identification', async ({ page }) => {
    await loginAsAdmin(page);
    await naviguerEtAjouterAdhesion(page, adhesionPvUuid);

    // ESPECE → identification
    await page.locator('[data-testid="adhesion-btn-especes"]').click();
    await expect(page.locator('[data-testid="adhesion-choose-id"]')).toBeVisible({ timeout: 10000 });

    // RETOUR → l'ecran identification disparait
    await page.locator('[data-testid="adhesion-choose-id"] #bt-retour-layer1').click();
    await expect(page.locator('[data-testid="adhesion-choose-id"]')).not.toBeVisible({ timeout: 5000 });
    console.log('OK RETOUR depuis ecran identification');
  });

  test('bouton retour fonctionne depuis formulaire email', async ({ page }) => {
    await loginAsAdmin(page);
    await naviguerEtAjouterAdhesion(page, adhesionPvUuid);

    // ESPECE → identification → saisir email
    await page.locator('[data-testid="adhesion-btn-especes"]').click();
    await expect(page.locator('[data-testid="adhesion-choose-id"]')).toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="adhesion-choose-email"]').click();
    await expect(page.locator('[data-testid="adhesion-form"]')).toBeVisible({ timeout: 10000 });

    // RETOUR → le formulaire disparait
    await page.locator('[data-testid="adhesion-form"] #bt-retour-layer1').click();
    await expect(page.locator('[data-testid="adhesion-form"]')).not.toBeVisible({ timeout: 5000 });
    console.log('OK RETOUR depuis formulaire email');
  });
});
