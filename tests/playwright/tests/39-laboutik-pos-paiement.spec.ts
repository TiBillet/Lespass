import { test, expect } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';
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
      await expect(page.locator('#addition-list')).toBeEmpty({ timeout: 5000 });
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
   * TEST 2 : Vérification dans l'admin Django
   * TEST 2: Verification in Django admin
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
