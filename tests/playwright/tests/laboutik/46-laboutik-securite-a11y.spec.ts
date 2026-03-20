import { test, expect } from '@playwright/test';
import { loginAsAdmin } from '../utils/auth';
import { execSync } from 'child_process';

/**
 * TEST: LaBoutik POS — Sécurité (XSS, validation prix libre) + Accessibilité
 * TEST: LaBoutik POS — Security (XSS, free price validation) + Accessibility
 *
 * LOCALISATION : tests/playwright/tests/laboutik/46-laboutik-securite-a11y.spec.ts
 *
 * Couvre :
 * - Fix XSS tarif.js : l'overlay multi-tarif affiche les noms sans injection HTML
 * - Validation prix libre côté client : erreur si montant < minimum
 * - Validation prix libre côté client : accepte si montant >= minimum
 * - Accessibilité : aria-live="polite" sur #addition-list
 * - Accessibilité : role="alert" + aria-live="assertive" sur les messages d'erreur
 *
 * Covers:
 * - XSS fix in tarif.js: multi-rate overlay displays names without HTML injection
 * - Client-side free price validation: error if amount < minimum
 * - Client-side free price validation: accepts if amount >= minimum
 * - Accessibility: aria-live="polite" on #addition-list
 * - Accessibility: role="alert" + aria-live="assertive" on error messages
 *
 * Prérequis / Prerequisites:
 * - La commande `create_test_pos_data` doit avoir été lancée
 * - Le PV "Adhesions" doit exister avec un produit multi-tarif (prix libre)
 * - La carte primaire tag_id_cm=A49E8E2A doit exister
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

test.describe('LaBoutik POS — Sécurité + Accessibilité / Security + Accessibility', () => {

  /**
   * UUID du point de vente Adhesions — récupéré dynamiquement
   * Adhesions POS UUID — fetched dynamically
   */
  let adhesionsPvUuid: string;

  /**
   * Récupère l'UUID du PV "Adhesions" avant tous les tests
   * Fetches the "Adhesions" POS UUID before all tests
   */
  test.beforeAll(async () => {
    const result = djangoShell(`
from laboutik.models import PointDeVente
pv = PointDeVente.objects.filter(comportement='A').first()
if pv:
    print(f'uuid={pv.uuid}')
else:
    print('NOT_FOUND')
`);
    console.log('Adhesions PV result:', result);

    const uuidMatch = result.match(/uuid=(.+)/);
    if (!uuidMatch) {
      throw new Error(
        `Point de vente Adhesions introuvable. Lancer create_test_pos_data d'abord. Résultat: ${result}`
      );
    }
    adhesionsPvUuid = uuidMatch[1].trim();
    console.log(`✓ Adhesions POS UUID trouvé : ${adhesionsPvUuid}`);
  });

  // =========================================================================
  // TEST 1 : Accessibilité — attributs aria-live
  // TEST 1: Accessibility — aria-live attributes
  // =========================================================================

  test('aria-live polite sur le panier / aria-live polite on cart', async ({ page }) => {

    await loginAsAdmin(page);

    // --- Navigue vers la caisse Adhesions ---
    // --- Navigate to Adhesions POS ---
    await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${adhesionsPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
    await page.waitForLoadState('networkidle');

    await test.step('Vérifie aria-live="polite" sur #addition-list / Check aria-live on cart', async () => {
      const additionList = page.locator('#addition-list');
      await expect(additionList).toBeVisible({ timeout: 10000 });
      const ariaLive = await additionList.getAttribute('aria-live');
      expect(ariaLive).toBe('polite');
      console.log('✓ aria-live="polite" sur #addition-list');
    });

    await test.step('Vérifie que #messages existe / Check #messages exists', async () => {
      const messages = page.locator('#messages');
      // #messages existe mais est caché (vide) au chargement
      // #messages exists but is hidden (empty) at load
      await expect(messages).toBeAttached();
      console.log('✓ #messages existe dans le DOM');
    });
  });

  // =========================================================================
  // TEST 2 : XSS — overlay tarif affiche les noms correctement
  // TEST 2: XSS — tarif overlay displays names correctly
  // =========================================================================

  test('overlay tarif multi-tarif sans injection HTML / tarif overlay without HTML injection', async ({ page }) => {

    await loginAsAdmin(page);

    await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${adhesionsPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
    await page.waitForLoadState('networkidle');

    await test.step('Clic sur article multi-tarif / Click multi-rate article', async () => {
      // Cherche un article avec data-tarifs contenant plus d'un tarif
      // Find an article with data-tarifs containing multiple rates
      const multiTarifArticle = page.locator('[data-tarifs]').first();
      await expect(multiTarifArticle).toBeVisible({ timeout: 10000 });
      await multiTarifArticle.click();

      // L'overlay tarif doit apparaître
      // The tarif overlay must appear
      await expect(page.locator('[data-testid="tarif-overlay"]')).toBeVisible({ timeout: 5000 });
      console.log('✓ Overlay tarif visible');
    });

    await test.step('Vérifie que les noms sont du texte pur (pas de HTML) / Check names are pure text', async () => {
      // Le titre de l'overlay ne doit pas contenir de balises HTML
      // The overlay title must not contain HTML tags
      const titre = page.locator('.tarif-overlay-title');
      const titreHtml = await titre.innerHTML();
      const titreText = await titre.textContent();

      // Si escapeHtml fonctionne, innerHTML === textContent (pas de balises)
      // If escapeHtml works, innerHTML === textContent (no tags)
      expect(titreHtml).toBe(titreText);
      console.log(`✓ Titre overlay : "${titreText}" (pas de HTML injecté)`);

      // Vérifie chaque label de bouton tarif
      // Check each tarif button label
      const labels = page.locator('.tarif-btn-label');
      const nbLabels = await labels.count();
      expect(nbLabels).toBeGreaterThan(0);

      for (let i = 0; i < nbLabels; i++) {
        const label = labels.nth(i);
        const labelHtml = await label.innerHTML();
        const labelText = await label.textContent();
        expect(labelHtml).toBe(labelText);
      }
      console.log(`✓ ${nbLabels} labels de tarif vérifiés (texte pur)`);
    });

    await test.step('Vérifie le bouton RETOUR et fermeture / Check RETOUR button and close', async () => {
      await page.locator('[data-testid="tarif-btn-retour"]').click();
      // L'overlay doit disparaître
      // The overlay must disappear
      await expect(page.locator('[data-testid="tarif-overlay"]')).not.toBeVisible({ timeout: 3000 });
      console.log('✓ Overlay fermé par RETOUR');
    });
  });

  // =========================================================================
  // TEST 3 : Validation prix libre côté client
  // TEST 3: Client-side free price validation
  // =========================================================================

  test('validation client prix libre : rejet et acceptation / client-side free price validation', async ({ page }) => {

    await loginAsAdmin(page);

    await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${adhesionsPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
    await page.waitForLoadState('networkidle');

    // Ouvrir l'overlay tarif sur un article avec prix libre
    // Open the tarif overlay on an article with free price
    await test.step('Ouvrir overlay sur article prix libre / Open overlay on free price article', async () => {
      const multiTarifArticle = page.locator('[data-tarifs]').first();
      await expect(multiTarifArticle).toBeVisible({ timeout: 10000 });
      await multiTarifArticle.click();
      await expect(page.locator('[data-testid="tarif-overlay"]')).toBeVisible({ timeout: 5000 });
    });

    await test.step('Montant sous le minimum → erreur / Amount below minimum → error', async () => {
      // Cherche l'input du prix libre
      // Find the free price input
      const freeInput = page.locator('.tarif-free-input');
      await expect(freeInput).toBeVisible({ timeout: 5000 });

      // Récupère le minimum depuis l'attribut min de l'input
      // Get the minimum from the input's min attribute
      const minimumStr = await freeInput.getAttribute('min');
      const minimum = parseFloat(minimumStr || '1');

      // Saisir un montant sous le minimum
      // Enter an amount below the minimum
      const montantInvalide = (minimum / 2).toFixed(2);
      await freeInput.fill(montantInvalide);

      // Cliquer OK
      // Click OK
      const okButton = page.locator('.tarif-free-validate');
      await okButton.click();

      // Le message d'erreur doit apparaître
      // The error message must appear
      const errorMessage = page.locator('.tarif-free-error');
      await expect(errorMessage).toContainText('Minimum', { timeout: 3000 });

      // L'input doit avoir la classe d'erreur
      // The input must have the error class
      await expect(freeInput).toHaveClass(/tarif-input-error/);

      // L'overlay est TOUJOURS visible (pas de fermeture)
      // The overlay is STILL visible (not closed)
      await expect(page.locator('[data-testid="tarif-overlay"]')).toBeVisible();
      console.log(`✓ Montant ${montantInvalide}€ rejeté, erreur affichée`);
    });

    await test.step('Montant valide → ajout au panier / Valid amount → added to cart', async () => {
      // Saisir un montant valide (>= minimum)
      // Enter a valid amount (>= minimum)
      const freeInput = page.locator('.tarif-free-input');
      const minimumStr = await freeInput.getAttribute('min');
      const minimum = parseFloat(minimumStr || '1');
      const montantValide = (minimum * 2).toFixed(2);

      await freeInput.fill(montantValide);

      const okButton = page.locator('.tarif-free-validate');
      await okButton.click();

      // L'overlay doit se fermer
      // The overlay must close
      await expect(page.locator('[data-testid="tarif-overlay"]')).not.toBeVisible({ timeout: 5000 });

      // L'article doit apparaître dans le panier
      // The article must appear in the cart
      await expect(page.locator('#addition-list')).not.toContainText('Panier vide', { timeout: 5000 });
      console.log(`✓ Montant ${montantValide}€ accepté, article ajouté au panier`);
    });
  });

  // NOTE : le test role="alert" sur hx_messages.html n'est pas pertinent en E2E
  // car hx_messages.html est un partial HTMX injecté via innerHTML dans #messages.
  // La navigation pleine page vers un PV invalide ne charge pas cette mécanique.
  // Le role="alert" est vérifié dans les tests pytest (test_validation_prix_libre.py)
  // via les réponses HTTP 400 qui retournent ce template.
  // / The role="alert" test on hx_messages.html is not relevant in E2E
  // because hx_messages.html is an HTMX partial injected via innerHTML into #messages.
  // Full page navigation to an invalid PV does not use this mechanism.
  // The role="alert" is verified in pytest tests (test_validation_prix_libre.py)
  // via HTTP 400 responses that return this template.
});
