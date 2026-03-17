import { test, expect } from '@playwright/test';
import { loginAsAdmin } from '../utils/auth';
import { execSync } from 'child_process';

/**
 * TEST: LaBoutik POS — Paiements espèces et carte bancaire
 * TEST: LaBoutik POS — Cash and card payment flows
 *
 * LOCALISATION : tests/playwright/tests/39-laboutik-pos-paiement.spec.ts
 *
 * Objectif :
 * - Vérifier qu'un paiement espèces fonctionne (Bière pression 5€)
 * - Vérifier qu'un paiement CB fonctionne après un reset (Coca Cola 3€)
 * - Ces deux paiements consécutifs valident le fix du bug HTMX reset
 *   (hx-post et hx-trigger étaient mutés et jamais restaurés entre deux paiements)
 * - Vérifier que les LigneArticle sont bien créées en base de données
 * - Vérifier dans l'admin /admin/BaseBillet/lignearticle/
 *
 * Prérequis :
 * - La commande `create_test_pos_data` doit avoir été lancée
 * - Le point de vente "Bar" doit exister avec "Bière pression" et "Coca Cola"
 * - La carte primaire tag_id_cm=A49E8E2A doit exister
 *
 * Goal:
 * - Verify cash payment works (Bière pression 5€)
 * - Verify CB payment works after reset (Coca Cola 3€)
 * - These two consecutive payments validate the HTMX reset bug fix
 * - Verify LigneArticle records are created in DB
 * - Verify in admin /admin/BaseBillet/lignearticle/
 */

/**
 * Tag ID de la carte primaire (caissier)
 * Primary card tag ID (cashier)
 */
const DEMO_TAGID_CM = process.env.DEMO_TAGID_CM || 'A49E8E2A';

/**
 * Exécute du code Python dans le shell Django du tenant lespass
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

test.describe('LaBoutik POS — Paiements espèces et CB / Cash and card payments', () => {

  /**
   * UUID du point de vente Bar — récupéré dynamiquement depuis la base de données
   * Bar POS UUID — fetched dynamically from the database
   */
  let barPvUuid: string;

  /**
   * Récupère l'UUID du point de vente "Bar" avant tous les tests
   * Fetches the "Bar" POS UUID before all tests
   */
  test.beforeAll(async () => {
    const result = djangoShell(`
from laboutik.models import PointDeVente
pv = PointDeVente.objects.filter(name='Bar').first()
if pv:
    print(f'uuid={pv.uuid}')
else:
    print('NOT_FOUND')
`);
    console.log('Bar PV result:', result);

    const uuidMatch = result.match(/uuid=(.+)/);
    if (!uuidMatch) {
      throw new Error(
        `Point de vente "Bar" introuvable. Lancer create_test_pos_data d'abord. Résultat: ${result}`
      );
    }
    barPvUuid = uuidMatch[1].trim();
    console.log(`✓ Bar POS UUID trouvé : ${barPvUuid}`);
  });

  /**
   * TEST 1 : Deux paiements consécutifs dans la même session
   * TEST 1: Two consecutive payments in the same session
   *
   * Ce test valide le fix du bug HTMX reset :
   * - Premier paiement : Bière pression par espèces
   * - Reset (clic RETOUR)
   * - Deuxième paiement : Coca Cola par CB
   * Le bug faisait que le 2e paiement envoyait directement à /payer/
   * sans passer par /moyens_paiement/ → réponse 400.
   *
   * This test validates the HTMX reset bug fix:
   * - First payment: Bière pression via cash
   * - Reset (RETOUR click)
   * - Second payment: Coca Cola via CB
   * The bug caused the 2nd payment to POST directly to /payer/
   * skipping /moyens_paiement/ → 400 response.
   */
  test('deux paiements consécutifs : espèces puis CB / two consecutive payments: cash then card', async ({ page }) => {

    // --- Connexion admin requise pour accéder à la caisse ---
    // --- Admin login required to access the POS ---
    await loginAsAdmin(page);

    // --- Navigue vers la caisse Bar ---
    // --- Navigate to Bar POS ---
    await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${barPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
    await page.waitForLoadState('networkidle');

    // =========================================================================
    // PAIEMENT 1 : Bière pression par espèces
    // PAYMENT 1: Bière pression via cash
    // =========================================================================

    await test.step('Paiement 1 — Ajouter Biere au panier / Add Biere to cart', async () => {
      // Clique sur la tuile "Biere" dans la liste des articles
      // Click the "Biere" tile in the article list
      const biereTile = page.locator('#products .article-container').filter({ hasText: 'Biere' }).first();
      await expect(biereTile).toBeVisible({ timeout: 10000 });
      await biereTile.click();

      // Attend que l'article apparaisse dans l'addition (liste des articles commandés)
      // Wait for the article to appear in the addition (ordered articles list)
      await expect(page.locator('#addition-list')).toContainText('Biere', { timeout: 5000 });
      console.log('✓ Biere ajoutée au panier');
    });

    await test.step('Paiement 1 — Clic VALIDER et choix ESPÈCE / Click VALIDER and choose CASH', async () => {
      // Clique sur VALIDER pour afficher les modes de paiement
      // Click VALIDER to show payment options
      await page.locator('#bt-valider').click();
      await expect(page.locator('[data-testid="paiement-moyens"]')).toBeVisible({ timeout: 10000 });
      console.log('✓ Panneau des modes de paiement visible');

      // Choisit ESPÈCE
      // Choose CASH
      await page.locator('[data-testid="paiement-moyens"]').getByText('ESPÈCE').click();
      await expect(page.locator('[data-testid="paiement-confirmation"]')).toBeVisible({ timeout: 10000 });
      console.log('✓ Écran de confirmation espèces visible');
    });

    await test.step('Paiement 1 — Confirmer paiement espèces / Confirm cash payment', async () => {
      // Confirme le paiement (le champ "somme donnée" peut rester vide)
      // Confirm payment (the "given sum" field can remain empty)
      await page.locator('#bt-valider-layer2').click();
      await expect(page.locator('[data-testid="paiement-succes"]')).toBeVisible({ timeout: 15000 });

      // Vérifie que l'écran de succès mentionne "espèce"
      // Verify the success screen mentions "espèce"
      const successText = await page.locator('[data-testid="paiement-succes"]').innerText();
      expect(successText.toLowerCase()).toContain('espèce');
      console.log(`✓ Paiement espèces confirmé. Texte : ${successText.substring(0, 80)}`);
    });

    await test.step('Paiement 1 — Retour à la caisse (reset) / Back to POS (reset)', async () => {
      // Clique sur RETOUR pour revenir à la caisse et réinitialiser
      // Click RETOUR to go back to POS and reset
      // Cible spécifiquement le RETOUR dans l'écran de succès (évite le doublon dans #message-no-article)
      // Target specifically the RETOUR inside the success screen (avoids duplicate in #message-no-article)
      await page.locator('[data-testid="paiement-succes"] #bt-retour-layer1').click();

      // Attend que l'écran de succès disparaisse
      // Wait for the success screen to disappear
      await expect(page.locator('[data-testid="paiement-succes"]')).not.toBeVisible({ timeout: 5000 });

      // Le panier doit être vide après le reset
      // The cart should be empty after reset
      await expect(page.locator('[data-testid="addition-empty-placeholder"]')).toBeVisible({ timeout: 5000 });
      console.log('✓ Panier réinitialisé après paiement espèces');
    });

    // =========================================================================
    // PAIEMENT 2 : Coca Cola par CB (valide le fix du bug HTMX reset)
    // PAYMENT 2: Coca Cola via CB (validates the HTMX reset bug fix)
    // =========================================================================

    await test.step('Paiement 2 — Ajouter Coca au panier / Add Coca to cart', async () => {
      // Clique sur la tuile "Coca"
      // Click the "Coca" tile
      const cocaTile = page.locator('#products .article-container').filter({ hasText: 'Coca' }).first();
      await expect(cocaTile).toBeVisible({ timeout: 5000 });
      await cocaTile.click();

      // Attend que l'article apparaisse dans l'addition
      // Wait for the article to appear in the addition
      await expect(page.locator('#addition-list')).toContainText('Coca', { timeout: 5000 });
      console.log('✓ Coca ajouté au panier');
    });

    await test.step('Paiement 2 — Clic VALIDER et choix CB / Click VALIDER and choose CB', async () => {
      // Ce clic était buggé avant le fix : le formulaire HTMX avait hx-post=/payer/
      // et hx-trigger=click (pas restaurés après le 1er paiement)
      // This click was broken before the fix: the HTMX form had hx-post=/payer/
      // and hx-trigger=click (not restored after the 1st payment)
      await page.locator('#bt-valider').click();
      await expect(page.locator('[data-testid="paiement-moyens"]')).toBeVisible({ timeout: 10000 });
      console.log('✓ Panneau des modes de paiement visible (2e paiement — fix validé)');

      // Choisit CB
      // Choose CB
      await page.locator('[data-testid="paiement-moyens"]').getByText('CB').click();
      await expect(page.locator('[data-testid="paiement-confirmation"]')).toBeVisible({ timeout: 10000 });
      console.log('✓ Écran de confirmation CB visible');
    });

    await test.step('Paiement 2 — Confirmer paiement CB / Confirm card payment', async () => {
      // Confirme le paiement CB
      // Confirm the card payment
      await page.locator('#bt-valider-layer2').click();
      await expect(page.locator('[data-testid="paiement-succes"]')).toBeVisible({ timeout: 15000 });

      // Vérifie que l'écran de succès mentionne "carte bancaire"
      // Verify the success screen mentions "carte bancaire"
      const successText = await page.locator('[data-testid="paiement-succes"]').innerText();
      expect(successText.toLowerCase()).toContain('carte bancaire');
      console.log(`✓ Paiement CB confirmé. Texte : ${successText.substring(0, 80)}`);
    });

    await test.step('Paiement 2 — Retour à la caisse / Back to POS', async () => {
      // Cible spécifiquement le RETOUR dans l'écran de succès (évite le doublon dans #message-no-article)
      // Target specifically the RETOUR inside the success screen (avoids duplicate in #message-no-article)
      await page.locator('[data-testid="paiement-succes"] #bt-retour-layer1').click();
      await expect(page.locator('[data-testid="paiement-succes"]')).not.toBeVisible({ timeout: 5000 });
      console.log('✓ Retour à la caisse après paiement CB');
    });

    // =========================================================================
    // VÉRIFICATION EN BASE — LigneArticle créées
    // DB VERIFICATION — LigneArticle records created
    // =========================================================================

    await test.step('Vérification DB — LigneArticle espèces CA (Biere) / DB check — cash CA LigneArticle', async () => {
      // LigneArticle.payment_method = 'CA' pour espèces (Cash)
      // LigneArticle.payment_method = 'CA' for cash payments
      // Produit accessible via : pricesold.productsold.product.name
      // Product accessible via: pricesold.productsold.product.name
      const result = djangoShell(`
from BaseBillet.models import LigneArticle
from django.utils import timezone
from datetime import timedelta
now = timezone.now()
ligne = LigneArticle.objects.filter(
    datetime__gte=now - timedelta(minutes=10),
    payment_method='CA',
    sale_origin='LB',
    pricesold__productsold__product__name='Biere'
).order_by('-datetime').first()
if ligne:
    print(f'pk={str(ligne.pk)[:8]} status={ligne.status} pm={ligne.payment_method}')
else:
    print('NOT_FOUND')
`);
      console.log('DB espèces Biere:', result);
      expect(result).not.toContain('NOT_FOUND');
      expect(result).toContain('pm=CA');
      console.log('✓ LigneArticle espèces Biere confirmée en base');
    });

    await test.step('Vérification DB — LigneArticle CB CC (Coca) / DB check — card CC LigneArticle', async () => {
      // LigneArticle.payment_method = 'CC' pour carte bancaire (Credit Card)
      // LigneArticle.payment_method = 'CC' for card payments
      const result = djangoShell(`
from BaseBillet.models import LigneArticle
from django.utils import timezone
from datetime import timedelta
now = timezone.now()
ligne = LigneArticle.objects.filter(
    datetime__gte=now - timedelta(minutes=10),
    payment_method='CC',
    sale_origin='LB',
    pricesold__productsold__product__name='Coca'
).order_by('-datetime').first()
if ligne:
    print(f'pk={str(ligne.pk)[:8]} status={ligne.status} pm={ligne.payment_method}')
else:
    print('NOT_FOUND')
`);
      console.log('DB CB Coca:', result);
      expect(result).not.toContain('NOT_FOUND');
      expect(result).toContain('pm=CC');
      console.log('✓ LigneArticle CB Coca confirmée en base');
    });
  });

  /**
   * TEST 2 : Vérification admin Django
   * TEST 2: Django admin verification
   *
   * Vérifie que les ventes apparaissent bien dans
   * /admin/BaseBillet/lignearticle/
   * Verifies that sales appear in /admin/BaseBillet/lignearticle/
   */
  test('vérification admin LigneArticle / admin LigneArticle verification', async ({ page }) => {
    await loginAsAdmin(page);

    await test.step('Ouvrir la liste LigneArticle / Open LigneArticle list', async () => {
      await page.goto('/admin/BaseBillet/lignearticle/');
      await page.waitForLoadState('networkidle');

      // Vérifie qu'on est bien sur la page de liste
      // Verify we are on the list page
      const pageContent = await page.innerText('body');
      expect(
        pageContent.toLowerCase().includes('lignearticle') ||
        pageContent.toLowerCase().includes('ligne article') ||
        pageContent.toLowerCase().includes('vente')
      ).toBeTruthy();
      console.log('✓ Page admin LigneArticle accessible');
    });

    await test.step('Chercher Biere / Search Biere', async () => {
      const searchInput = page.locator('input[name="q"]').first();
      await searchInput.fill('Biere');
      await searchInput.press('Enter');
      await page.waitForLoadState('networkidle');

      const rows = page.locator('#result_list tbody tr');
      const rowCount = await rows.count();
      expect(rowCount).toBeGreaterThanOrEqual(1);
      console.log(`✓ ${rowCount} ligne(s) LigneArticle trouvée(s) pour Biere`);
    });

    await test.step('Chercher Coca / Search Coca', async () => {
      const searchInput = page.locator('input[name="q"]').first();
      await searchInput.fill('Coca');
      await searchInput.press('Enter');
      await page.waitForLoadState('networkidle');

      const rows = page.locator('#result_list tbody tr');
      const rowCount = await rows.count();
      expect(rowCount).toBeGreaterThanOrEqual(1);
      console.log(`✓ ${rowCount} ligne(s) LigneArticle trouvée(s) pour Coca`);
    });
  });

});


/**
 * TEST: LaBoutik POS — Paiement NFC cashless
 * TEST: LaBoutik POS — NFC cashless payment
 *
 * LOCALISATION : tests/playwright/tests/39-laboutik-pos-paiement.spec.ts
 *
 * Objectif :
 * - Vérifier le paiement NFC via le bouton de simulation NFCSIMU
 * - Vérifier le nouveau solde affiché après paiement
 * - Vérifier le cas "Carte inconnue" (tag non enregistré en base)
 * - Vérifier la LigneArticle avec payment_method=LE (LOCAL_EURO) en base
 *
 * Prérequis :
 * - DEMO=1 dans l'environnement (active les boutons de simulation NFC)
 * - create_test_pos_data doit avoir été lancé (cartes CLIENT1, CLIENT2)
 *
 * Goal:
 * - Verify NFC payment via NFCSIMU simulation button
 * - Verify new balance displayed after payment
 * - Verify "Carte inconnue" case (unregistered tag)
 * - Verify LigneArticle with payment_method=LE (LOCAL_EURO) in DB
 */

const DEMO_TAGID_CLIENT1 = process.env.DEMO_TAGID_CLIENT1 || '52BE6543';
const DEMO_TAGID_CLIENT2 = process.env.DEMO_TAGID_CLIENT2 || 'C63A0A4C';
// CLIENT3 : toujours remis à zéro par create_test_pos_data → utilisé pour "solde insuffisant"
// CLIENT3: always reset to 0 by create_test_pos_data → used for "insufficient balance"
const DEMO_TAGID_CLIENT3 = process.env.DEMO_TAGID_CLIENT3 || 'D74B1B5D';
// CLIENT4 : jamais créé en base → utilisé pour "carte inconnue"
// CLIENT4: never created in DB → used for "unknown card"
const DEMO_TAGID_CLIENT4 = process.env.DEMO_TAGID_CLIENT4 || 'E85C2C6E';

test.describe('LaBoutik POS — Paiement NFC cashless / NFC cashless payment', () => {

  let barPvUuid: string;

  /**
   * Setup : crée l'asset TLF, un wallet pour CLIENT1, et crédite le wallet
   * Setup: creates TLF asset, a wallet for CLIENT1, and credits the wallet
   */
  test.beforeAll(async () => {
    // S'assurer que les données POS existent
    // Ensure POS test data exists
    djangoShell(`from django.core.management import call_command; call_command('create_test_pos_data')`);

    // Récupérer l'UUID du point de vente Bar
    // Get Bar POS UUID
    const pvResult = djangoShell(`
from laboutik.models import PointDeVente
pv = PointDeVente.objects.filter(name='Bar').first()
if pv:
    print(f'uuid={pv.uuid}')
else:
    print('NOT_FOUND')
`);
    const uuidMatch = pvResult.match(/uuid=(.+)/);
    if (!uuidMatch) {
      throw new Error(`Point de vente "Bar" introuvable. Résultat: ${pvResult}`);
    }
    barPvUuid = uuidMatch[1].trim();

    // Créer l'asset TLF + wallet + créditer pour CLIENT1
    // Create TLF asset + wallet + credit for CLIENT1
    const setupResult = djangoShell(`
from AuthBillet.models import Wallet
from QrcodeCashless.models import CarteCashless
from Customers.models import Client
from fedow_core.models import Asset
from fedow_core.services import WalletService
from django.db import transaction as db_transaction
tenant = Client.objects.get(schema_name='lespass')
wallet_lieu, _ = Wallet.objects.get_or_create(name='[pw_test] Lieu NFC')
Asset.objects.filter(tenant_origin=tenant, category='TLF', active=True).update(active=False)
asset_tlf = Asset.objects.filter(name='[pw_test] TestCoin', tenant_origin=tenant).first()
if asset_tlf:
    asset_tlf.active = True
    asset_tlf.wallet_origin = wallet_lieu
    asset_tlf.save(update_fields=['active', 'wallet_origin'])
else:
    asset_tlf = Asset.objects.create(name='[pw_test] TestCoin', tenant_origin=tenant, category='TLF', currency_code='EUR', wallet_origin=wallet_lieu, active=True)
wallet_client, _ = Wallet.objects.get_or_create(name='[pw_test] Client1 NFC')
carte = CarteCashless.objects.get(tag_id='${DEMO_TAGID_CLIENT1}')
carte.wallet_ephemere = wallet_client
carte.user = None
carte.save(update_fields=['wallet_ephemere', 'user'])
with db_transaction.atomic():
    WalletService.crediter(wallet=wallet_client, asset=asset_tlf, montant_en_centimes=5000)
solde = WalletService.obtenir_solde(wallet=wallet_client, asset=asset_tlf)
print(f'SETUP_OK solde={solde}')
`);
    console.log('NFC setup:', setupResult);
    expect(setupResult).toContain('SETUP_OK');

    // CLIENT3 est remis à zéro par create_test_pos_data (user et wallet_ephemere supprimés).
    // Aucun setup supplémentaire nécessaire — le wallet sera créé vide à la première lecture NFC.
    // CLIENT3 is reset to zero by create_test_pos_data (user and wallet_ephemere deleted).
    // No extra setup needed — wallet will be created empty on first NFC read.
  });

  /**
   * TEST 3 : Paiement NFC via simulation CASHLESS
   * TEST 3: NFC payment via CASHLESS simulation
   *
   * Flux : Biere → VALIDER → CASHLESS → sim CLIENT1 → succès + nouveau solde
   * Flow: Biere → VALIDER → CASHLESS → sim CLIENT1 → success + new balance
   */
  test('paiement NFC cashless avec solde suffisant / NFC cashless payment with sufficient balance', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${barPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
    await page.waitForLoadState('networkidle');

    await test.step('Ajouter Biere au panier / Add Biere to cart', async () => {
      const biereTile = page.locator('#products .article-container').filter({ hasText: 'Biere' }).first();
      await expect(biereTile).toBeVisible({ timeout: 10000 });
      await biereTile.click();
      await expect(page.locator('#addition-list')).toContainText('Biere', { timeout: 5000 });
      console.log('✓ Biere ajoutée au panier');
    });

    await test.step('VALIDER puis choisir CASHLESS / VALIDER then choose CASHLESS', async () => {
      await page.locator('#bt-valider').click();
      await expect(page.locator('[data-testid="paiement-moyens"]')).toBeVisible({ timeout: 10000 });
      console.log('✓ Panneau des modes de paiement visible');

      // Cliquer sur CASHLESS — déclenche le chargement du lecteur NFC
      // Click CASHLESS — triggers NFC reader loading
      await page.locator('[data-testid="paiement-moyens"]').getByText('CASHLESS').click();
    });

    await test.step('Attendre les boutons NFC simulation / Wait for NFC sim buttons', async () => {
      // En mode DEMO, des boutons de simulation NFC apparaissent dans #nfc-simu-tag
      // In DEMO mode, NFC simulation buttons appear in #nfc-simu-tag
      await expect(page.locator('.nfc-reader-simu-bt').first()).toBeVisible({ timeout: 10000 });
      console.log('✓ Boutons de simulation NFC visibles');
    });

    await test.step('Cliquer sur Carte client 1 / Click Carte client 1', async () => {
      // Le bouton de simulation a l'attribut tag-id avec le tag_id de la carte
      // The simulation button has the tag-id attribute with the card's tag_id
      await page.locator(`.nfc-reader-simu-bt[tag-id="${DEMO_TAGID_CLIENT1}"]`).click();

      // Vérifier que l'écran de succès apparaît
      // Verify the success screen appears
      await expect(page.locator('[data-testid="paiement-succes"]')).toBeVisible({ timeout: 15000 });
      console.log('✓ Écran de succès NFC visible');
    });

    await test.step('Vérifier nouveau solde affiché / Verify displayed new balance', async () => {
      // Le bloc NFC-specific doit être présent avec le nouveau solde
      // The NFC-specific block must be present with the new balance
      await expect(page.locator('[data-testid="paiement-nfc-succes"]')).toBeVisible();
      await expect(page.locator('[data-testid="paiement-nfc-solde"]')).toBeVisible();

      const soldeText = await page.locator('[data-testid="paiement-nfc-solde"]').innerText();
      console.log(`✓ Nouveau solde NFC affiché : ${soldeText}`);

      // Le solde doit être un nombre (peut être décimal)
      // The balance must be a number (may be decimal)
      expect(parseFloat(soldeText)).not.toBeNaN();
    });

    await test.step('Retour à la caisse / Back to POS', async () => {
      await page.locator('[data-testid="paiement-succes"] #bt-retour-layer1').click();
      await expect(page.locator('[data-testid="paiement-succes"]')).not.toBeVisible({ timeout: 5000 });
      await expect(page.locator('[data-testid="addition-empty-placeholder"]')).toBeVisible({ timeout: 5000 });
      console.log('✓ Retour à la caisse après paiement NFC');
    });

    // Vérification en base : LigneArticle avec payment_method=LE (LOCAL_EURO)
    // DB verification: LigneArticle with payment_method=LE (LOCAL_EURO)
    await test.step('Vérification DB — LigneArticle NFC (LE) / DB check — NFC LigneArticle (LE)', async () => {
      const result = djangoShell(`
from BaseBillet.models import LigneArticle
from django.utils import timezone
from datetime import timedelta
now = timezone.now()
ligne = LigneArticle.objects.filter(
    datetime__gte=now - timedelta(minutes=5),
    payment_method='LE',
    sale_origin='LB',
    pricesold__productsold__product__name='Biere'
).order_by('-datetime').first()
if ligne:
    print(f'pk={str(ligne.pk)[:8]} status={ligne.status} pm={ligne.payment_method} amount={ligne.amount}')
else:
    print('NOT_FOUND')
`);
      console.log('DB NFC Biere:', result);
      expect(result).not.toContain('NOT_FOUND');
      expect(result).toContain('pm=LE');
      console.log('✓ LigneArticle NFC (LE) Biere confirmée en base');
    });

    // Vérification en base : Transaction fedow_core SALE
    // DB verification: fedow_core SALE Transaction
    await test.step('Vérification DB — Transaction SALE fedow_core / DB check — fedow_core SALE Transaction', async () => {
      const result = djangoShell(`
from fedow_core.models import Transaction
from QrcodeCashless.models import CarteCashless
from django.utils import timezone
from datetime import timedelta
now = timezone.now()
carte = CarteCashless.objects.get(tag_id='${DEMO_TAGID_CLIENT1}')
tx = Transaction.objects.filter(
    action=Transaction.SALE,
    card=carte,
    datetime__gte=now - timedelta(minutes=5),
).order_by('-id').first()
if tx:
    print(f'tx_id={tx.pk} amount={tx.amount} action={tx.action}')
else:
    print('NOT_FOUND')
`);
      console.log('DB Transaction SALE:', result);
      expect(result).not.toContain('NOT_FOUND');
      expect(result).toContain('action=SAL');
      console.log('✓ Transaction SALE fedow_core confirmée en base');
    });
  });

  /**
   * TEST 4 : Paiement NFC carte inconnue
   * TEST 4: NFC payment with unknown card
   *
   * CLIENT4 (E85C2C6E par défaut) n'est jamais créé en base par create_test_pos_data.
   * Cliquer dessus doit afficher "Carte inconnue".
   *
   * CLIENT4 (E85C2C6E by default) is never created in DB by create_test_pos_data.
   * Clicking it should display "Carte inconnue".
   */
  test('paiement NFC carte inconnue / NFC payment with unknown card', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${barPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
    await page.waitForLoadState('networkidle');

    await test.step('Ajouter Biere et choisir CASHLESS / Add Biere and choose CASHLESS', async () => {
      const biereTile = page.locator('#products .article-container').filter({ hasText: 'Biere' }).first();
      await expect(biereTile).toBeVisible({ timeout: 10000 });
      await biereTile.click();
      await expect(page.locator('#addition-list')).toContainText('Biere', { timeout: 5000 });

      await page.locator('#bt-valider').click();
      await expect(page.locator('[data-testid="paiement-moyens"]')).toBeVisible({ timeout: 10000 });

      await page.locator('[data-testid="paiement-moyens"]').getByText('CASHLESS').click();
      await expect(page.locator('.nfc-reader-simu-bt').first()).toBeVisible({ timeout: 10000 });
    });

    await test.step('Cliquer Carte inconnue (CLIENT4, inexistante en DB) / Click unknown card (CLIENT4, not in DB)', async () => {
      // CLIENT4 n'existe jamais en base — le serveur doit répondre "Carte inconnue"
      // CLIENT4 is never in DB — server must respond "Carte inconnue"
      const client4Btn = page.locator(`.nfc-reader-simu-bt[tag-id="${DEMO_TAGID_CLIENT4}"]`);
      await expect(client4Btn).toBeVisible();
      await client4Btn.click();

      // Le message "Carte inconnue" doit apparaître dans #messages
      // The "Carte inconnue" message should appear in #messages
      await expect(page.locator('#messages')).toContainText('Carte inconnue', { timeout: 10000 });
      console.log('✓ Message "Carte inconnue" affiché pour carte non enregistrée');
    });
  });

  /**
   * TEST 5 : Paiement NFC avec solde insuffisant
   * TEST 5: NFC payment with insufficient balance
   *
   * CLIENT2 a un wallet avec 1 centime seulement.
   * Un produit a 5€ doit afficher "Fonds insuffisants" / "Il manque".
   *
   * CLIENT2 has a wallet with only 1 cent.
   * A product at 5€ should display "Fonds insuffisants" / "Il manque".
   */
  test('paiement NFC solde insuffisant / NFC payment with insufficient balance', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${barPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
    await page.waitForLoadState('networkidle');

    await test.step('Ajouter Biere et choisir CASHLESS / Add Biere and choose CASHLESS', async () => {
      // Ajouter Biere (5€) au panier — le solde de CLIENT2 est de 1 centime
      // Add Biere (5€) to cart — CLIENT2 balance is only 1 cent
      const biereTile = page.locator('#products .article-container').filter({ hasText: 'Biere' }).first();
      await expect(biereTile).toBeVisible({ timeout: 10000 });
      await biereTile.click();
      await expect(page.locator('#addition-list')).toContainText('Biere', { timeout: 5000 });

      await page.locator('#bt-valider').click();
      await expect(page.locator('[data-testid="paiement-moyens"]')).toBeVisible({ timeout: 10000 });

      // Choisir CASHLESS pour declencher le lecteur NFC
      // Choose CASHLESS to trigger the NFC reader
      await page.locator('[data-testid="paiement-moyens"]').getByText('CASHLESS').click();
      await expect(page.locator('.nfc-reader-simu-bt').first()).toBeVisible({ timeout: 10000 });
      console.log('✓ Boutons NFC simulation visibles');
    });

    await test.step('Cliquer Carte client 3 (solde insuffisant) / Click Carte client 3 (insufficient balance)', async () => {
      // CLIENT3 est toujours remis à zéro par create_test_pos_data — solde garanti à 0
      // CLIENT3 is always reset to zero by create_test_pos_data — balance guaranteed at 0
      await page.locator(`.nfc-reader-simu-bt[tag-id="${DEMO_TAGID_CLIENT3}"]`).click();

      // Le message "Fonds insuffisants" doit apparaitre
      // The "Fonds insuffisants" message should appear
      await expect(page.locator('[data-testid="paiement-nfc-insuffisant"]')).toBeVisible({ timeout: 15000 });
      console.log('✓ Écran "Fonds insuffisants" visible');

      // Verifier que "Il manque" est affiche avec un montant
      // Verify that "Il manque" is displayed with an amount
      await expect(page.locator('[data-testid="paiement-nfc-insuffisant"]')).toContainText('Il manque');
      console.log('✓ Message "Il manque" affiché');
    });

    await test.step('Vérification DB — aucune Transaction SALE / DB check — no SALE Transaction', async () => {
      // Aucune transaction ne doit avoir ete creee pour CLIENT2
      // No transaction should have been created for CLIENT2
      const result = djangoShell(`
from fedow_core.models import Transaction
from QrcodeCashless.models import CarteCashless
from django.utils import timezone
from datetime import timedelta
now = timezone.now()
carte = CarteCashless.objects.get(tag_id='${DEMO_TAGID_CLIENT3}')
tx = Transaction.objects.filter(
    action=Transaction.SALE,
    card=carte,
    datetime__gte=now - timedelta(minutes=2),
).order_by('-id').first()
if tx:
    print(f'FOUND tx_id={tx.pk}')
else:
    print('NO_TX_FOUND')
`);
      console.log('DB Transaction CLIENT3:', result);
      expect(result).toContain('NO_TX_FOUND');
      console.log('✓ Aucune Transaction SALE créée pour CLIENT2 (solde insuffisant)');
    });
  });

  /**
   * TEST 6 : Paiement NFC puis especes consecutifs (validation reset)
   * TEST 6: NFC then cash consecutive payments (reset validation)
   *
   * Valide que le formulaire HTMX est correctement reinitialise apres un
   * paiement NFC, et qu'un paiement especes fonctionne ensuite.
   * Ce test est l'equivalent du test 1 (especes puis CB) mais pour NFC.
   *
   * Validates that the HTMX form is correctly reset after an NFC payment,
   * and that a cash payment works afterwards.
   * This test is the NFC equivalent of test 1 (cash then card).
   */
  test('paiement NFC puis espèces consécutifs / NFC then cash consecutive payments', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${barPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
    await page.waitForLoadState('networkidle');

    // =========================================================================
    // PAIEMENT A : Biere par NFC (CLIENT1)
    // PAYMENT A: Biere via NFC (CLIENT1)
    // =========================================================================

    await test.step('Paiement A — Biere par NFC / Payment A — Biere via NFC', async () => {
      const biereTile = page.locator('#products .article-container').filter({ hasText: 'Biere' }).first();
      await expect(biereTile).toBeVisible({ timeout: 10000 });
      await biereTile.click();
      await expect(page.locator('#addition-list')).toContainText('Biere', { timeout: 5000 });

      await page.locator('#bt-valider').click();
      await expect(page.locator('[data-testid="paiement-moyens"]')).toBeVisible({ timeout: 10000 });

      await page.locator('[data-testid="paiement-moyens"]').getByText('CASHLESS').click();
      await expect(page.locator('.nfc-reader-simu-bt').first()).toBeVisible({ timeout: 10000 });

      await page.locator(`.nfc-reader-simu-bt[tag-id="${DEMO_TAGID_CLIENT1}"]`).click();
      await expect(page.locator('[data-testid="paiement-succes"]')).toBeVisible({ timeout: 15000 });
      console.log('✓ Paiement NFC réussi');
    });

    await test.step('Paiement A — Retour à la caisse / Payment A — Back to POS', async () => {
      await page.locator('[data-testid="paiement-succes"] #bt-retour-layer1').click();
      await expect(page.locator('[data-testid="paiement-succes"]')).not.toBeVisible({ timeout: 5000 });
      await expect(page.locator('[data-testid="addition-empty-placeholder"]')).toBeVisible({ timeout: 5000 });
      console.log('✓ Panier réinitialisé après paiement NFC');
    });

    // =========================================================================
    // PAIEMENT B : Coca par especes (apres reset NFC)
    // PAYMENT B: Coca via cash (after NFC reset)
    // =========================================================================

    await test.step('Paiement B — Coca par espèces / Payment B — Coca via cash', async () => {
      // Ce paiement valide que le formulaire HTMX est bien reinitialise
      // apres un paiement NFC (hx-post, hx-trigger restaures)
      // This payment validates that the HTMX form is correctly reset
      // after an NFC payment (hx-post, hx-trigger restored)
      const cocaTile = page.locator('#products .article-container').filter({ hasText: 'Coca' }).first();
      await expect(cocaTile).toBeVisible({ timeout: 5000 });
      await cocaTile.click();
      await expect(page.locator('#addition-list')).toContainText('Coca', { timeout: 5000 });

      await page.locator('#bt-valider').click();
      await expect(page.locator('[data-testid="paiement-moyens"]')).toBeVisible({ timeout: 10000 });
      console.log('✓ Panneau des modes de paiement visible (après reset NFC)');

      // Choisir ESPECE
      // Choose CASH
      await page.locator('[data-testid="paiement-moyens"]').getByText('ESPÈCE').click();
      await expect(page.locator('[data-testid="paiement-confirmation"]')).toBeVisible({ timeout: 10000 });

      // Confirmer le paiement
      // Confirm payment
      await page.locator('#bt-valider-layer2').click();
      await expect(page.locator('[data-testid="paiement-succes"]')).toBeVisible({ timeout: 15000 });

      // Verifier que l'ecran de succes mentionne "espece"
      // Verify the success screen mentions "espece"
      const successText = await page.locator('[data-testid="paiement-succes"]').innerText();
      expect(successText.toLowerCase()).toContain('espèce');
      console.log(`✓ Paiement espèces confirmé après NFC. Texte : ${successText.substring(0, 80)}`);
    });

    await test.step('Paiement B — Retour à la caisse / Payment B — Back to POS', async () => {
      await page.locator('[data-testid="paiement-succes"] #bt-retour-layer1').click();
      await expect(page.locator('[data-testid="paiement-succes"]')).not.toBeVisible({ timeout: 5000 });
      console.log('✓ Retour à la caisse — séquence NFC puis espèces validée');
    });
  });

  /**
   * TEST 7 : Deux paiements NFC consécutifs (validation reset NFC → NFC)
   * TEST 7: Two consecutive NFC payments (NFC → NFC reset validation)
   *
   * Valide que le formulaire HTMX est correctement réinitialisé entre
   * deux paiements NFC consécutifs. Le test 6 couvrait NFC→espèces,
   * celui-ci couvre NFC→NFC.
   *
   * Validates that the HTMX form is correctly reset between two
   * consecutive NFC payments. Test 6 covered NFC→cash,
   * this one covers NFC→NFC.
   */
  test('deux paiements NFC consécutifs / two consecutive NFC payments', async ({ page }) => {
    // Recréditer CLIENT1 pour s'assurer qu'il a assez de solde
    // Re-credit CLIENT1 to ensure sufficient balance
    djangoShell(`
from AuthBillet.models import Wallet
from Customers.models import Client
from fedow_core.models import Asset
from fedow_core.services import WalletService
from django.db import transaction as db_transaction
tenant = Client.objects.get(schema_name='lespass')
asset_tlf = Asset.objects.filter(name='[pw_test] TestCoin', tenant_origin=tenant, active=True).first()
wallet_client = Wallet.objects.get(name='[pw_test] Client1 NFC')
with db_transaction.atomic():
    WalletService.crediter(wallet=wallet_client, asset=asset_tlf, montant_en_centimes=5000)
solde = WalletService.obtenir_solde(wallet=wallet_client, asset=asset_tlf)
print(f'CREDIT_OK solde={solde}')
`);

    await loginAsAdmin(page);
    await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${barPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
    await page.waitForLoadState('networkidle');

    // =========================================================================
    // PAIEMENT A : Eau par NFC (1.50€)
    // PAYMENT A: Eau via NFC (1.50€)
    // =========================================================================

    await test.step('Paiement A — Eau par NFC / Payment A — Eau via NFC', async () => {
      const eauTile = page.locator('#products .article-container').filter({ hasText: 'Eau' }).first();
      await expect(eauTile).toBeVisible({ timeout: 10000 });
      await eauTile.click();
      await expect(page.locator('#addition-list')).toContainText('Eau', { timeout: 5000 });

      await page.locator('#bt-valider').click();
      await expect(page.locator('[data-testid="paiement-moyens"]')).toBeVisible({ timeout: 10000 });

      await page.locator('[data-testid="paiement-moyens"]').getByText('CASHLESS').click();
      await expect(page.locator('.nfc-reader-simu-bt').first()).toBeVisible({ timeout: 10000 });

      await page.locator(`.nfc-reader-simu-bt[tag-id="${DEMO_TAGID_CLIENT1}"]`).click();
      await expect(page.locator('[data-testid="paiement-succes"]')).toBeVisible({ timeout: 15000 });
      console.log('✓ Paiement NFC Eau réussi');
    });

    await test.step('Paiement A — Retour à la caisse / Payment A — Back to POS', async () => {
      await page.locator('[data-testid="paiement-succes"] #bt-retour-layer1').click();
      await expect(page.locator('[data-testid="paiement-succes"]')).not.toBeVisible({ timeout: 5000 });
      await expect(page.locator('[data-testid="addition-empty-placeholder"]')).toBeVisible({ timeout: 5000 });
      console.log('✓ Panier réinitialisé après 1er paiement NFC');
    });

    // =========================================================================
    // PAIEMENT B : Coca par NFC (3€) — valide le reset NFC → NFC
    // PAYMENT B: Coca via NFC (3€) — validates NFC → NFC reset
    // =========================================================================

    await test.step('Paiement B — Coca par NFC / Payment B — Coca via NFC', async () => {
      // Ce paiement valide que le formulaire HTMX est bien réinitialisé
      // après un paiement NFC précédent (hx-post, hx-trigger restaurés)
      // This payment validates that the HTMX form is correctly reset
      // after a previous NFC payment (hx-post, hx-trigger restored)
      const cocaTile = page.locator('#products .article-container').filter({ hasText: 'Coca' }).first();
      await expect(cocaTile).toBeVisible({ timeout: 5000 });
      await cocaTile.click();
      await expect(page.locator('#addition-list')).toContainText('Coca', { timeout: 5000 });

      await page.locator('#bt-valider').click();
      await expect(page.locator('[data-testid="paiement-moyens"]')).toBeVisible({ timeout: 10000 });
      console.log('✓ Panneau des modes de paiement visible (2e paiement NFC — reset validé)');

      await page.locator('[data-testid="paiement-moyens"]').getByText('CASHLESS').click();
      await expect(page.locator('.nfc-reader-simu-bt').first()).toBeVisible({ timeout: 10000 });

      await page.locator(`.nfc-reader-simu-bt[tag-id="${DEMO_TAGID_CLIENT1}"]`).click();
      await expect(page.locator('[data-testid="paiement-succes"]')).toBeVisible({ timeout: 15000 });
      console.log('✓ 2e paiement NFC Coca réussi — séquence NFC→NFC validée');
    });

    await test.step('Paiement B — Retour et vérification DB / Payment B — Back and DB check', async () => {
      await page.locator('[data-testid="paiement-succes"] #bt-retour-layer1').click();
      await expect(page.locator('[data-testid="paiement-succes"]')).not.toBeVisible({ timeout: 5000 });

      // Vérifier que les 2 transactions SALE existent en base
      // Verify both SALE transactions exist in DB
      const result = djangoShell(`
from fedow_core.models import Transaction
from QrcodeCashless.models import CarteCashless
from django.utils import timezone
from datetime import timedelta
now = timezone.now()
carte = CarteCashless.objects.get(tag_id='${DEMO_TAGID_CLIENT1}')
txs = Transaction.objects.filter(
    action=Transaction.SALE,
    card=carte,
    datetime__gte=now - timedelta(minutes=3),
).order_by('-id')
print(f'tx_count={txs.count()}')
for tx in txs[:2]:
    print(f'  tx_id={tx.pk} amount={tx.amount}')
`);
      console.log('DB Transactions NFC→NFC:', result);
      // Au moins 2 transactions récentes
      // At least 2 recent transactions
      const countMatch = result.match(/tx_count=(\d+)/);
      expect(countMatch).toBeTruthy();
      expect(parseInt(countMatch![1])).toBeGreaterThanOrEqual(2);
      console.log('✓ 2+ Transactions SALE NFC confirmées en base');
    });
  });

  /**
   * TEST 8 : Paiement NFC multi-articles avec vérification solde exact
   * TEST 8: NFC multi-item payment with exact balance verification
   *
   * Ajoute Chips (2€) + Cacahuetes (1.50€) = 3.50€ total.
   * Vérifie le solde en base AVANT et APRÈS le paiement.
   * Le solde doit diminuer de exactement 350 centimes.
   *
   * Adds Chips (2€) + Cacahuetes (1.50€) = 3.50€ total.
   * Verifies balance in DB BEFORE and AFTER payment.
   * Balance must decrease by exactly 350 cents.
   */
  test('paiement NFC multi-articles vérifie solde / NFC multi-item payment verifies balance', async ({ page }) => {
    // Recréditer CLIENT1 et noter le solde exact avant paiement
    // Re-credit CLIENT1 and note exact balance before payment
    const soldeAvantResult = djangoShell(`
from AuthBillet.models import Wallet
from Customers.models import Client
from fedow_core.models import Asset
from fedow_core.services import WalletService
from django.db import transaction as db_transaction
tenant = Client.objects.get(schema_name='lespass')
asset_tlf = Asset.objects.filter(name='[pw_test] TestCoin', tenant_origin=tenant, active=True).first()
wallet_client = Wallet.objects.get(name='[pw_test] Client1 NFC')
with db_transaction.atomic():
    WalletService.crediter(wallet=wallet_client, asset=asset_tlf, montant_en_centimes=5000)
solde = WalletService.obtenir_solde(wallet=wallet_client, asset=asset_tlf)
print(f'SOLDE_AVANT={solde}')
`);
    const soldeAvantMatch = soldeAvantResult.match(/SOLDE_AVANT=(\d+)/);
    expect(soldeAvantMatch).toBeTruthy();
    const soldeAvant = parseInt(soldeAvantMatch![1]);
    console.log(`Solde CLIENT1 avant paiement : ${soldeAvant} centimes`);

    await loginAsAdmin(page);
    await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${barPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
    await page.waitForLoadState('networkidle');

    await test.step('Ajouter Chips + Cacahuetes au panier / Add Chips + Cacahuetes to cart', async () => {
      // Ajouter Chips (2€)
      // Add Chips (2€)
      const chipsTile = page.locator('#products .article-container').filter({ hasText: 'Chips' }).first();
      await expect(chipsTile).toBeVisible({ timeout: 10000 });
      await chipsTile.click();
      await expect(page.locator('#addition-list')).toContainText('Chips', { timeout: 5000 });
      console.log('✓ Chips ajoutés au panier');

      // Ajouter Cacahuetes (1.50€)
      // Add Cacahuetes (1.50€)
      const cacaTile = page.locator('#products .article-container').filter({ hasText: 'Cacahuetes' }).first();
      await expect(cacaTile).toBeVisible({ timeout: 5000 });
      await cacaTile.click();
      await expect(page.locator('#addition-list')).toContainText('Cacahuetes', { timeout: 5000 });
      console.log('✓ Cacahuetes ajoutés au panier');
    });

    await test.step('Payer par NFC / Pay via NFC', async () => {
      await page.locator('#bt-valider').click();
      await expect(page.locator('[data-testid="paiement-moyens"]')).toBeVisible({ timeout: 10000 });

      await page.locator('[data-testid="paiement-moyens"]').getByText('CASHLESS').click();
      await expect(page.locator('.nfc-reader-simu-bt').first()).toBeVisible({ timeout: 10000 });

      await page.locator(`.nfc-reader-simu-bt[tag-id="${DEMO_TAGID_CLIENT1}"]`).click();
      await expect(page.locator('[data-testid="paiement-succes"]')).toBeVisible({ timeout: 15000 });

      // Vérifier que le nouveau solde est affiché
      // Verify the new balance is displayed
      await expect(page.locator('[data-testid="paiement-nfc-solde"]')).toBeVisible();
      const soldeAffiche = await page.locator('[data-testid="paiement-nfc-solde"]').innerText();
      console.log(`✓ Paiement NFC multi-articles réussi. Solde affiché : ${soldeAffiche}`);
    });

    await test.step('Retour et vérification solde exact en DB / Back and exact balance DB check', async () => {
      await page.locator('[data-testid="paiement-succes"] #bt-retour-layer1').click();
      await expect(page.locator('[data-testid="paiement-succes"]')).not.toBeVisible({ timeout: 5000 });

      // Vérifier que le solde a diminué de exactement 350 centimes (2€ + 1.50€)
      // Verify balance decreased by exactly 350 cents (2€ + 1.50€)
      const soldeApresResult = djangoShell(`
from AuthBillet.models import Wallet
from Customers.models import Client
from fedow_core.models import Asset
from fedow_core.services import WalletService
tenant = Client.objects.get(schema_name='lespass')
asset_tlf = Asset.objects.filter(name='[pw_test] TestCoin', tenant_origin=tenant, active=True).first()
wallet_client = Wallet.objects.get(name='[pw_test] Client1 NFC')
solde = WalletService.obtenir_solde(wallet=wallet_client, asset=asset_tlf)
print(f'SOLDE_APRES={solde}')
`);
      const soldeApresMatch = soldeApresResult.match(/SOLDE_APRES=(\d+)/);
      expect(soldeApresMatch).toBeTruthy();
      const soldeApres = parseInt(soldeApresMatch![1]);

      // Chips (2€ = 200c) + Cacahuetes (1.50€ = 150c) = 350 centimes
      const montantAttendu = 350;
      const difference = soldeAvant - soldeApres;
      console.log(`Solde avant: ${soldeAvant}c, après: ${soldeApres}c, diff: ${difference}c, attendu: ${montantAttendu}c`);
      expect(difference).toBe(montantAttendu);
      console.log('✓ Solde diminué de exactement 350 centimes (Chips 2€ + Cacahuetes 1.50€)');

      // Vérifier les 2 LigneArticle créées
      // Verify both LigneArticle records created
      const lignesResult = djangoShell(`
from BaseBillet.models import LigneArticle
from django.utils import timezone
from datetime import timedelta
now = timezone.now()
lignes = LigneArticle.objects.filter(
    datetime__gte=now - timedelta(minutes=3),
    payment_method='LE',
    sale_origin='LB',
).order_by('-datetime')
noms = [l.pricesold.productsold.product.name for l in lignes[:4]]
print(f'lignes={len(noms)} noms={",".join(noms)}')
`);
      console.log('DB LigneArticle multi-articles:', lignesResult);
      expect(lignesResult).toContain('Chips');
      expect(lignesResult).toContain('Cacahuetes');
      console.log('✓ LigneArticle Chips + Cacahuetes confirmées en base');
    });
  });
});
