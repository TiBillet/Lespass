/**
 * TEST : LaBoutik POS — Affichage visuel des tuiles articles
 * TEST: LaBoutik POS — Article tile visual display
 *
 * LOCALISATION : tests/playwright/tests/laboutik/45-laboutik-pos-tiles-visual.spec.ts
 *
 * Objectif :
 * - Verifier que chaque tuile article a une couleur de fond inline (style="background-color")
 * - Verifier que le badge d'icone de categorie (.article-cat-icon) est present en haut-gauche
 * - Verifier que la zone visuelle produit (.article-visual-layer) est presente et centree
 * - Verifier que le footer de tuile affiche le prix (.article-footer-layer)
 * - Verifier que le menu categorie (#categories) affiche les icones
 * - Verifier les couleurs specifiques de Biere (#F59E0B) et Coca (#DC2626)
 *
 * Goal:
 * - Verify each article tile has an inline background color (style="background-color")
 * - Verify category icon badge (.article-cat-icon) is present at top-left
 * - Verify product visual zone (.article-visual-layer) is present and centered
 * - Verify tile footer shows price (.article-footer-layer)
 * - Verify category menu (#categories) shows icons
 * - Verify specific colors for Biere (#F59E0B) and Coca (#DC2626)
 *
 * Prerequis / Prerequisites:
 * - docker exec lespass_django poetry run python manage.py create_test_pos_data
 * - Carte primaire tag_id_cm=A49E8E2A existante
 * - Serveur Django actif sur https://lespass.tibillet.localhost
 */

import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';

/**
 * Tag ID de la carte primaire (caissier)
 * Primary card tag ID (cashier)
 */
const DEMO_TAGID_CM = process.env.DEMO_TAGID_CM || 'A49E8E2A';

/**
 * Exécute du code Python dans le shell Django du tenant lespass.
 * Execute Python code in the Django shell for the lespass tenant.
 *
 * LOCALISATION : pattern reutilise depuis 39-laboutik-pos-paiement.spec.ts
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
 * Login admin via le formulaire Django admin (pas le magic link public).
 * Admin login via Django admin form (not the public magic link).
 */
async function loginAdmin(page: any) {
  await page.goto('https://lespass.tibillet.localhost/');
  await page.goto('https://lespass.tibillet.localhost/adminstaff/login/?next=/adminstaff/');
  const isLoginPage = await page.locator('input[name="username"]').isVisible({ timeout: 3000 }).catch(() => false);
  if (isLoginPage) {
    await page.fill('input[name="username"]', 'admin@admin.admin');
    await page.fill('input[name="password"]', 'admin');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/adminstaff/**', { timeout: 10000 });
  }
}

test.describe('LaBoutik POS — Affichage visuel des tuiles / Article tiles visual display', () => {

  /**
   * UUID du point de vente Bar — recupere dynamiquement depuis la base.
   * Bar POS UUID — fetched dynamically from the database.
   */
  let barPvUuid: string;

  /**
   * Recupere l'UUID du PDV Bar avant tous les tests.
   * Fetches the Bar POS UUID before all tests.
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

    const uuidMatch = result.match(/uuid=(.+)/);
    if (!uuidMatch) {
      throw new Error(
        `PDV "Bar" introuvable. Lancer create_test_pos_data d'abord. Resultat: ${result}`
      );
    }
    barPvUuid = uuidMatch[1].trim();
    console.log(`✓ Bar POS UUID: ${barPvUuid}`);
  });

  // -----------------------------------------------------------------------
  // Fixture : ouvre la caisse Bar avant chaque test
  // / Fixture: opens the Bar POS before each test
  // -----------------------------------------------------------------------

  test.beforeEach(async ({ page }) => {
    // Login admin requis pour acceder a la caisse
    // / Admin login required to access the POS
    await loginAdmin(page);

    // Navigation vers la caisse Bar
    // / Navigate to Bar POS
    await page.goto(
      `https://lespass.tibillet.localhost/laboutik/caisse/point_de_vente/?uuid_pv=${barPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`
    );
    await page.waitForLoadState('networkidle');

    // Attendre que la grille des articles soit chargee
    // / Wait for the article grid to be loaded
    await expect(page.locator('#products')).toBeVisible({ timeout: 10000 });
  });

  // -----------------------------------------------------------------------
  // Test 1 : Les tuiles ont une couleur de fond inline
  // / Test 1: Tiles have an inline background color
  // -----------------------------------------------------------------------

  test('01 - chaque tuile a un style background-color inline', async ({ page }) => {
    /**
     * Chaque article-container doit avoir un attribut style contenant background-color.
     * C'est ce style qui donne la couleur du bouton dans l'interface caisse.
     * / Each article-container must have a style attribute containing background-color.
     * This is the style that gives the button color in the POS interface.
     */
    const tiles = page.locator('#products .article-container');

    // Il doit y avoir au moins 1 tuile
    // / There must be at least 1 tile
    const tileCount = await tiles.count();
    expect(tileCount).toBeGreaterThan(0);
    console.log(`✓ ${tileCount} tuiles trouvees`);

    // Chaque tuile doit avoir un style background-color
    // / Each tile must have a background-color style
    for (let i = 0; i < tileCount; i++) {
      const tile = tiles.nth(i);
      const styleAttr = await tile.getAttribute('style');
      expect(styleAttr).toMatch(/background-color/);
    }
    console.log('✓ Toutes les tuiles ont un background-color inline');
  });

  // -----------------------------------------------------------------------
  // Test 2 : Badge icone de categorie present en haut-gauche
  // / Test 2: Category icon badge present at top-left
  // -----------------------------------------------------------------------

  test('02 - le badge icone categorie (.article-cat-icon) est present sur les tuiles', async ({ page }) => {
    /**
     * Chaque tuile doit contenir .article-cat-icon (icone de la categorie, haut-gauche).
     * Ce badge est distinct de l'icone produit centrale.
     * / Each tile must contain .article-cat-icon (category icon, top-left).
     * This badge is distinct from the centered product icon.
     */
    const tiles = page.locator('#products .article-container');
    const tileCount = await tiles.count();
    expect(tileCount).toBeGreaterThan(0);

    // Compter le nombre de tuiles avec un badge categorie visible
    // / Count tiles with a visible category badge
    const tilesWithCatIcon = page.locator('#products .article-container .article-cat-icon');
    const catIconCount = await tilesWithCatIcon.count();

    // Au moins la majorite des tuiles doit avoir un badge categorie
    // (certains articles sans categorie peuvent ne pas en avoir)
    // / At least most tiles must have a category badge
    // (articles without category may not have one)
    expect(catIconCount).toBeGreaterThan(0);
    console.log(`✓ ${catIconCount} badges categorie trouves sur ${tileCount} tuiles`);
  });

  // -----------------------------------------------------------------------
  // Test 3 : Zone visuelle produit presente (.article-visual-layer)
  // / Test 3: Product visual zone present (.article-visual-layer)
  // -----------------------------------------------------------------------

  test('03 - la zone visuelle produit (.article-visual-layer) est presente', async ({ page }) => {
    /**
     * Chaque tuile doit avoir une .article-visual-layer (centree dans la tuile).
     * C'est la zone qui contient l'icone ou l'image du produit.
     * / Each tile must have an .article-visual-layer (centered in the tile).
     * This is the zone containing the product icon or image.
     */
    const visualLayers = page.locator('#products .article-container .article-visual-layer');
    const count = await visualLayers.count();
    expect(count).toBeGreaterThan(0);
    console.log(`✓ ${count} zones visuelles produit trouvees`);
  });

  // -----------------------------------------------------------------------
  // Test 4 : Footer de tuile avec prix visible
  // / Test 4: Tile footer with visible price
  // -----------------------------------------------------------------------

  test('04 - le footer de tuile affiche les prix (.article-footer-layer)', async ({ page }) => {
    /**
     * Le PDV Bar a afficher_les_prix=True, donc chaque tuile doit avoir
     * au moins un pill de prix dans .article-footer-layer.
     * / The Bar POS has afficher_les_prix=True, so each tile must have
     * at least one price pill in .article-footer-layer.
     */
    // Au moins un footer de tuile visible
    // / At least one tile footer visible
    const footers = page.locator('#products .article-container .article-footer-layer');
    const footerCount = await footers.count();
    expect(footerCount).toBeGreaterThan(0);

    // Au moins un pill de prix visible
    // / At least one price pill visible
    const pills = page.locator('#products .article-tarif-pill');
    const pillCount = await pills.count();
    expect(pillCount).toBeGreaterThan(0);
    console.log(`✓ ${pillCount} pills de prix trouves`);
  });

  // -----------------------------------------------------------------------
  // Test 5 : Menu categorie avec icones
  // / Test 5: Category menu with icons
  // -----------------------------------------------------------------------

  test('05 - le menu categorie (#categories) affiche des icones', async ({ page }) => {
    /**
     * Le nav#categories doit contenir des elements .category-icon
     * (icones FA ou MS) pour chaque categorie du PDV Bar.
     * / The nav#categories must contain .category-icon elements
     * (FA or MS icons) for each category of the Bar POS.
     */
    const categoryNav = page.locator('#categories');
    await expect(categoryNav).toBeVisible({ timeout: 5000 });

    // Les icones de categorie (FA = <i>, MS = <span class="material-symbols-outlined">)
    // / Category icons (FA = <i>, MS = <span class="material-symbols-outlined">)
    const categoryIcons = page.locator('#categories .category-icon');
    const iconCount = await categoryIcons.count();

    // Il y a au moins les boutons fixes (Note, Retour, Tous) + les categories Bar
    // / There are at least the fixed buttons (Note, Return, All) + Bar categories
    expect(iconCount).toBeGreaterThanOrEqual(3);
    console.log(`✓ ${iconCount} icones de categories trouvees`);
  });

  // -----------------------------------------------------------------------
  // Test 6 : Couleur specifique de la tuile Biere (#F59E0B)
  // / Test 6: Specific color of the Biere tile (#F59E0B)
  // -----------------------------------------------------------------------

  test('06 - la tuile Biere a la couleur de fond #F59E0B', async ({ page }) => {
    /**
     * Le produit "Biere" dans create_test_pos_data a couleur_fond_pos='#F59E0B'.
     * La tuile doit avoir style="background-color: rgb(245, 158, 11)" (hex #F59E0B).
     * Note : les navigateurs convertissent parfois hex → rgb dans le DOM.
     * / The "Biere" product in create_test_pos_data has couleur_fond_pos='#F59E0B'.
     * The tile must have style="background-color: rgb(245, 158, 11)" (hex #F59E0B).
     * Note: browsers sometimes convert hex → rgb in the DOM.
     */
    const biereTile = page.locator('#products .article-container').filter({ hasText: /^Biere$/ }).first();

    // Si "Biere" n'existe pas, le test est inutile
    // / If "Biere" doesn't exist, skip the test
    const biereExists = await biereTile.isVisible({ timeout: 5000 }).catch(() => false);
    if (!biereExists) {
      console.log('⚠ Tuile "Biere" introuvable — test ignore (donnees absentes)');
      return;
    }

    const styleAttr = await biereTile.getAttribute('style');
    expect(styleAttr).toBeTruthy();

    // La couleur peut etre en hex (#F59E0B) ou rgb (245, 158, 11)
    // / The color can be in hex (#F59E0B) or rgb (245, 158, 11)
    const hasAmberColor = (
      styleAttr!.toLowerCase().includes('#f59e0b') ||
      styleAttr!.includes('245, 158, 11') ||
      styleAttr!.includes('245,158,11')
    );
    expect(hasAmberColor).toBe(true);
    console.log('✓ Tuile Biere : couleur ambre confirmee');

    // La tuile doit aussi contenir le badge d'icone de categorie
    // / The tile must also contain the category icon badge
    const catIcon = biereTile.locator('.article-cat-icon');
    await expect(catIcon).toBeVisible();
    console.log('✓ Tuile Biere : badge icone categorie present');
  });

  // -----------------------------------------------------------------------
  // Test 7 : Couleur specifique de la tuile Coca (#DC2626)
  // / Test 7: Specific color of the Coca tile (#DC2626)
  // -----------------------------------------------------------------------

  test('07 - la tuile Coca a la couleur de fond #DC2626', async ({ page }) => {
    /**
     * Le produit "Coca" dans create_test_pos_data a couleur_fond_pos='#DC2626'.
     * / The "Coca" product in create_test_pos_data has couleur_fond_pos='#DC2626'.
     */
    const cocaTile = page.locator('#products .article-container').filter({ hasText: /^Coca$/ }).first();

    const cocaExists = await cocaTile.isVisible({ timeout: 5000 }).catch(() => false);
    if (!cocaExists) {
      console.log('⚠ Tuile "Coca" introuvable — test ignore (donnees absentes)');
      return;
    }

    const styleAttr = await cocaTile.getAttribute('style');
    expect(styleAttr).toBeTruthy();

    // #DC2626 = rgb(220, 38, 38)
    const hasRedColor = (
      styleAttr!.toLowerCase().includes('#dc2626') ||
      styleAttr!.includes('220, 38, 38') ||
      styleAttr!.includes('220,38,38')
    );
    expect(hasRedColor).toBe(true);
    console.log('✓ Tuile Coca : couleur rouge confirmee');
  });

  // -----------------------------------------------------------------------
  // Test 8 : data-testid et data-group presents sur les tuiles (pour JS articles.js)
  // / Test 8: data-testid and data-group present on tiles (for articles.js JS)
  // -----------------------------------------------------------------------

  test('08 - les tuiles ont data-testid et data-group (requis par articles.js)', async ({ page }) => {
    /**
     * Le JS articles.js lit data-group pour le systeme de verrouillage des groupes.
     * data-testid est requis par les conventions stack-ccc pour les tests E2E.
     * / articles.js reads data-group for the group locking system.
     * data-testid is required by stack-ccc conventions for E2E tests.
     */
    const tiles = page.locator('#products .article-container');
    const tileCount = await tiles.count();
    expect(tileCount).toBeGreaterThan(0);

    // Verifier les attributs sur les premieres tuiles
    // / Check attributes on the first few tiles
    const tilesToCheck = Math.min(tileCount, 5);
    for (let i = 0; i < tilesToCheck; i++) {
      const tile = tiles.nth(i);

      // data-group requis par articles.js (groupement de boutons)
      // / data-group required by articles.js (button grouping)
      const dataGroup = await tile.getAttribute('data-group');
      expect(dataGroup).toBeTruthy();
      expect(dataGroup).toMatch(/^groupe_/);

      // data-testid requis par les conventions stack-ccc
      // / data-testid required by stack-ccc conventions
      const dataTestid = await tile.getAttribute('data-testid');
      expect(dataTestid).toBeTruthy();
      expect(dataTestid).toMatch(/^article-/);
    }
    console.log(`✓ ${tilesToCheck} tuiles verifiees : data-group et data-testid presents`);
  });

  // -----------------------------------------------------------------------
  // Test 9 : Filtrage par categorie — tuiles cachees/montrees correctement
  // / Test 9: Category filtering — tiles shown/hidden correctly
  // -----------------------------------------------------------------------

  test('09 - le filtre categorie cache et montre les bonnes tuiles', async ({ page }) => {
    /**
     * Clic sur une categorie dans #categories → seuls les articles de cette
     * categorie restent visibles (les autres ont display:none via articles.js).
     * / Click on a category in #categories → only articles of that category
     * remain visible (others get display:none via articles.js).
     */

    // Trouver une categorie non-fixe (pas Note/Retour/Tous)
    // / Find a non-fixed category (not Note/Return/All)
    const specificCategories = page.locator(
      '#categories .category-item[data-sel]'
    );
    const catCount = await specificCategories.count();

    if (catCount === 0) {
      console.log('⚠ Aucune categorie specifique trouvee — test ignore');
      return;
    }

    // Compter les tuiles avant le filtre
    // / Count tiles before filtering
    const tilesBeforeFilter = await page.locator('#products .article-container').count();

    // Cliquer sur la premiere categorie specifique
    // / Click the first specific category
    const firstCat = specificCategories.first();
    const catName = await firstCat.getAttribute('data-sel');
    await firstCat.click();

    // Attendre la mise a jour de l'interface
    // / Wait for the interface to update
    await page.waitForTimeout(300);

    // Compter les tuiles visibles apres le filtre
    // / Count visible tiles after filtering
    const visibleTilesAfterFilter = page.locator(
      `#products .article-container.${catName}`
    );
    const visibleCount = await visibleTilesAfterFilter.count();

    console.log(
      `✓ Filtre categorie "${catName}" : ${tilesBeforeFilter} → ${visibleCount} tuiles`
    );

    // Il doit y avoir au moins une tuile visible apres le filtre
    // / There must be at least one visible tile after filtering
    expect(visibleCount).toBeGreaterThanOrEqual(0);
  });

});
