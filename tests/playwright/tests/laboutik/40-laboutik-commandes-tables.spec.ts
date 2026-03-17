import { test, expect } from '@playwright/test';
import { loginAsAdmin } from '../utils/auth';
import { execSync } from 'child_process';

// Feature "commandes tables" non terminée — tests mis en skip
// / "Table orders" feature not done yet — tests skipped
test.skip();

/**
 * TEST: LaBoutik POS — Commandes et tables (mode restaurant)
 * TEST: LaBoutik POS — Orders and tables (restaurant mode)
 *
 * LOCALISATION : tests/playwright/tests/40-laboutik-commandes-tables.spec.ts
 *
 * Objectif :
 * - Vérifier l'UI de sélection de tables (PV restaurant)
 * - Vérifier le lifecycle complet d'une commande via l'API CommandeViewSet
 *   (ouvrir → ajouter articles → servir → payer → vérif DB)
 * - Vérifier l'annulation d'une commande et la libération de table
 * - Vérifier les cas d'erreur (annuler une commande payée, table multi-commandes)
 *
 * Prérequis :
 * - create_test_pos_data doit avoir été lancé
 * - Le PV "Restaurant" doit exister avec accepte_commandes=True
 * - Au moins une Table doit exister
 *
 * Goal:
 * - Verify table selection UI (restaurant PV)
 * - Verify full order lifecycle via CommandeViewSet API
 *   (open → add articles → serve → pay → DB check)
 * - Verify order cancellation and table freeing
 * - Verify error cases (cancel paid order, multi-order table)
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

/**
 * Données de test récupérées en beforeAll
 * Test data fetched in beforeAll
 */
let restaurantPvUuid: string;
let tableUuid: string;
let tableName: string;
let pizzaProductUuid: string;
let pizzaPriceUuid: string;
let cafeProductUuid: string;
let cafePriceUuid: string;
let burgerProductUuid: string;
let burgerPriceUuid: string;

test.describe('LaBoutik POS — Commandes et tables / Orders and tables', () => {

  test.beforeAll(async () => {
    // S'assurer que les données POS existent
    // Ensure POS test data exists
    djangoShell(`from django.core.management import call_command; call_command('create_test_pos_data')`);

    // Récupérer les données Restaurant PV, table, et produits
    // Fetch Restaurant PV, table, and product data
    const setupResult = djangoShell(`
from laboutik.models import PointDeVente, Table
from BaseBillet.models import Price
pv = PointDeVente.objects.filter(accepte_commandes=True).first()
if not pv:
    print('NO_PV')
else:
    print(f'pv_uuid={pv.uuid}')
    table = Table.objects.filter(archive=False).first()
    if table:
        print(f'table_uuid={table.uuid}')
        print(f'table_name={table.name}')
    products = pv.products.filter(methode_caisse__isnull=False)
    for prod in products:
        price = Price.objects.filter(product=prod, publish=True, asset__isnull=True).order_by('order').first()
        if price:
            print(f'product={prod.name}|{prod.uuid}|{price.uuid}|{price.prix}')
`);
    console.log('Setup result:', setupResult);

    const pvMatch = setupResult.match(/pv_uuid=(.+)/);
    if (!pvMatch) throw new Error(`PV Restaurant introuvable. Résultat: ${setupResult}`);
    restaurantPvUuid = pvMatch[1].trim();

    const tableMatch = setupResult.match(/table_uuid=(.+)/);
    if (!tableMatch) throw new Error(`Table introuvable. Résultat: ${setupResult}`);
    tableUuid = tableMatch[1].trim();

    const tableNameMatch = setupResult.match(/table_name=(.+)/);
    if (tableNameMatch) tableName = tableNameMatch[1].trim();

    // Parser les produits
    // Parse products
    const productLines = setupResult.split('\n').filter(l => l.startsWith('product='));
    for (const line of productLines) {
      const parts = line.replace('product=', '').split('|');
      const name = parts[0];
      const prodUuid = parts[1];
      const priceUuid = parts[2];
      if (name === 'Pizza') {
        pizzaProductUuid = prodUuid;
        pizzaPriceUuid = priceUuid;
      } else if (name === 'Cafe') {
        cafeProductUuid = prodUuid;
        cafePriceUuid = priceUuid;
      } else if (name === 'Burger') {
        burgerProductUuid = prodUuid;
        burgerPriceUuid = priceUuid;
      }
    }

    if (!pizzaProductUuid || !cafeProductUuid || !burgerProductUuid) {
      throw new Error(`Produits manquants. Pizza=${pizzaProductUuid}, Cafe=${cafeProductUuid}, Burger=${burgerProductUuid}`);
    }
    console.log(`✓ PV=${restaurantPvUuid}, Table=${tableUuid} (${tableName}), Pizza=${pizzaProductUuid}, Cafe=${cafeProductUuid}, Burger=${burgerProductUuid}`);
  });

  /**
   * Nettoyer la table avant chaque test (la remettre LIBRE, annuler les commandes ouvertes)
   * Clean up the table before each test (set it back to LIBRE, cancel open orders)
   */
  test.beforeEach(async () => {
    djangoShell(`
from laboutik.models import Table, CommandeSauvegarde
table = Table.objects.get(uuid='${tableUuid}')
table.statut = Table.LIBRE
table.save(update_fields=['statut'])
CommandeSauvegarde.objects.filter(
    table=table,
    statut__in=[CommandeSauvegarde.OPEN, CommandeSauvegarde.SERVED],
).update(statut=CommandeSauvegarde.CANCEL)
`);
  });

  // ==========================================================================
  // TEST 1 : UI — Sélection de tables
  // TEST 1: UI — Table selection
  // ==========================================================================

  test('UI sélection de tables : affichage et navigation / table selection UI: display and navigation', async ({ page }) => {
    // Désactiver service_direct pour voir la page de sélection de tables
    // Disable service_direct to see the table selection page
    djangoShell(`
from laboutik.models import PointDeVente
pv = PointDeVente.objects.get(uuid='${restaurantPvUuid}')
pv.service_direct = False
pv.save(update_fields=['service_direct'])
`);

    await loginAsAdmin(page);

    await test.step('PV Restaurant affiche les tables / Restaurant PV shows tables', async () => {
      // Naviguer vers le PV Restaurant (accepte_commandes=True, service_direct=False)
      // Navigate to Restaurant PV (accepte_commandes=True, service_direct=False)
      await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${restaurantPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
      await page.waitForLoadState('networkidle');

      // Le PV restaurant affiche la page de sélection de tables
      // Restaurant PV shows the table selection page
      await expect(page.locator('#tables-container')).toBeVisible({ timeout: 10000 });

      // Au moins un bouton de table doit être visible
      // At least one table button must be visible
      const tableBoutons = page.locator('.table-bouton');
      const count = await tableBoutons.count();
      expect(count).toBeGreaterThanOrEqual(1);
      console.log(`✓ ${count} table(s) affichée(s) dans le sélecteur`);

      // Vérifier que le nom de la table de test est visible
      // Verify the test table name is visible
      await expect(page.locator('.table-bouton').filter({ hasText: tableName })).toBeVisible();
      console.log(`✓ Table "${tableName}" visible`);
    });

    await test.step('Clic sur une table charge le POS / Clicking a table loads the POS', async () => {
      // Cliquer sur la table de test
      // Click the test table
      await page.locator('.table-bouton').filter({ hasText: tableName }).click();
      await page.waitForLoadState('networkidle');

      // L'interface POS doit se charger (pas la page tables)
      // The POS interface must load (not the tables page)
      await expect(page.locator('[data-testid="caisse-pv-interface"]')).toBeVisible({ timeout: 10000 });
      console.log('✓ Interface POS chargée après clic sur table');

      // Le titre doit mentionner la table
      // The title must mention the table
      const headerText = await page.locator('header').innerText();
      expect(headerText).toContain(tableName);
      console.log(`✓ Header contient "${tableName}"`);
    });

    await test.step('Service direct contourne les tables / Direct service bypasses tables', async () => {
      // Retourner à la sélection de tables
      // Go back to table selection
      await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${restaurantPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
      await page.waitForLoadState('networkidle');
      await expect(page.locator('#tables-container')).toBeVisible({ timeout: 10000 });

      // Cliquer sur SERVICE DIRECT
      // Click SERVICE DIRECT
      await page.locator('.test-service-direct').click();
      await page.waitForLoadState('networkidle');

      // L'interface POS doit se charger directement
      // The POS interface must load directly
      await expect(page.locator('[data-testid="caisse-pv-interface"]')).toBeVisible({ timeout: 10000 });
      console.log('✓ Service direct charge le POS sans tables');

      // Restaurer service_direct=True pour ne pas casser les autres tests
      // Restore service_direct=True to not break other tests
      djangoShell(`
from laboutik.models import PointDeVente
pv = PointDeVente.objects.get(uuid='${restaurantPvUuid}')
pv.service_direct = True
pv.save(update_fields=['service_direct'])
`);
    });
  });

  // ==========================================================================
  // TEST 2 : API — Lifecycle complet d'une commande
  // TEST 2: API — Full order lifecycle
  // ==========================================================================

  test('lifecycle complet : ouvrir → ajouter → servir → payer espèces / full lifecycle: open → add → serve → pay cash', async ({ page }) => {
    await loginAsAdmin(page);

    // On a besoin d'une page chargée pour avoir le cookie de session
    // We need a loaded page to have the session cookie
    await page.goto(`/laboutik/caisse/`);
    await page.waitForLoadState('networkidle');

    let commandeUuid: string;

    await test.step('Ouvrir commande (Pizza + Cafe) / Open order (Pizza + Cafe)', async () => {
      // POST /laboutik/commande/ouvrir/ avec JSON
      // POST /laboutik/commande/ouvrir/ with JSON
      const csrfToken = await page.evaluate(() => {
        const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
      });

      const response = await page.request.post('/laboutik/commande/ouvrir/', {
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        data: {
          table_uuid: tableUuid,
          uuid_pv: restaurantPvUuid,
          articles: [
            { product_uuid: pizzaProductUuid, price_uuid: pizzaPriceUuid, qty: 1 },
            { product_uuid: cafeProductUuid, price_uuid: cafePriceUuid, qty: 2 },
          ],
        },
      });

      expect(response.status()).toBe(201);
      const body = await response.text();
      expect(body.toLowerCase()).toContain('commande');
      console.log('✓ Commande créée (201)');
    });

    await test.step('Vérif DB : commande OPEN, table OCCUPEE / DB check: order OPEN, table OCCUPIED', async () => {
      const result = djangoShell(`
from laboutik.models import Table, CommandeSauvegarde, ArticleCommandeSauvegarde
table = Table.objects.get(uuid='${tableUuid}')
cmd = CommandeSauvegarde.objects.filter(table=table, statut=CommandeSauvegarde.OPEN).order_by('-datetime').first()
if cmd:
    nb_articles = cmd.articles.count()
    print(f'CMD_UUID={cmd.uuid}')
    print(f'CMD_STATUT={cmd.statut}')
    print(f'TABLE_STATUT={table.statut}')
    print(f'NB_ARTICLES={nb_articles}')
    for art in cmd.articles.all():
        print(f'ART={art.product.name}|qty={art.qty}|statut={art.statut}|rap={art.reste_a_payer}')
else:
    print('NO_CMD')
`);
      console.log('DB ouvrir:', result);
      expect(result).not.toContain('NO_CMD');
      expect(result).toContain('CMD_STATUT=OP');
      expect(result).toContain('TABLE_STATUT=O');
      expect(result).toContain('NB_ARTICLES=2');
      expect(result).toContain('ART=Pizza');
      expect(result).toContain('ART=Cafe');

      // Extraire l'UUID de la commande pour les étapes suivantes
      // Extract order UUID for the next steps
      const uuidMatch = result.match(/CMD_UUID=(.+)/);
      expect(uuidMatch).toBeTruthy();
      commandeUuid = uuidMatch![1].trim();
      console.log(`✓ Commande ${commandeUuid} OPEN, table OCCUPEE, 2 articles`);
    });

    await test.step('Ajouter Burger à la commande / Add Burger to order', async () => {
      const csrfToken = await page.evaluate(() => {
        const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
      });

      const response = await page.request.post(`/laboutik/commande/ajouter/${commandeUuid}/`, {
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        data: [
          { product_uuid: burgerProductUuid, price_uuid: burgerPriceUuid, qty: 1 },
        ],
      });

      expect(response.status()).toBe(200);
      console.log('✓ Burger ajouté à la commande');
    });

    await test.step('Vérif DB : 3 articles / DB check: 3 articles', async () => {
      const result = djangoShell(`
from laboutik.models import CommandeSauvegarde
cmd = CommandeSauvegarde.objects.get(uuid='${commandeUuid}')
nb = cmd.articles.count()
noms = [a.product.name for a in cmd.articles.all()]
print(f'NB={nb} NOMS={",".join(noms)}')
`);
      console.log('DB ajouter:', result);
      expect(result).toContain('NB=3');
      expect(result).toContain('Burger');
      console.log('✓ 3 articles dans la commande (Pizza, Cafe, Burger)');
    });

    await test.step('Marquer servie / Mark as served', async () => {
      const csrfToken = await page.evaluate(() => {
        const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
      });

      const response = await page.request.post(`/laboutik/commande/servir/${commandeUuid}/`, {
        headers: {
          'X-CSRFToken': csrfToken,
        },
      });

      expect(response.status()).toBe(200);
      console.log('✓ Commande marquée comme servie');
    });

    await test.step('Vérif DB : commande SERVED, table SERVIE / DB check: order SERVED, table SERVED', async () => {
      const result = djangoShell(`
from laboutik.models import Table, CommandeSauvegarde, ArticleCommandeSauvegarde
cmd = CommandeSauvegarde.objects.get(uuid='${commandeUuid}')
table = Table.objects.get(uuid='${tableUuid}')
statuts_articles = list(cmd.articles.values_list('statut', flat=True))
print(f'CMD_STATUT={cmd.statut}')
print(f'TABLE_STATUT={table.statut}')
print(f'ART_STATUTS={",".join(statuts_articles)}')
`);
      console.log('DB servir:', result);
      expect(result).toContain('CMD_STATUT=SV');
      expect(result).toContain('TABLE_STATUT=S');
      // Tous les articles doivent être SERVI (SV), pas EN_ATTENTE (AT) ni EN_COURS (EC)
      // All articles must be SERVED (SV), not WAITING (AT) or IN_PROGRESS (EC)
      const artStatutsMatch = result.match(/ART_STATUTS=(.+)/);
      expect(artStatutsMatch).toBeTruthy();
      const artStatuts = artStatutsMatch![1].split(',');
      for (const s of artStatuts) {
        expect(s.trim()).toBe('SV');
      }
      console.log('✓ Commande SERVED, table SERVIE, articles SERVI');
    });

    await test.step('Payer par espèces / Pay with cash', async () => {
      const csrfToken = await page.evaluate(() => {
        const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
      });

      // Total = Pizza 12€ + Cafe 2€×2 + Burger 11€ = 27€
      // Somme donnée : 3000 centimes (30€)
      // Total = Pizza 12€ + Cafe 2€×2 + Burger 11€ = 27€
      // Given sum: 3000 cents (30€)
      const response = await page.request.post(`/laboutik/commande/payer/${commandeUuid}/`, {
        headers: {
          'X-CSRFToken': csrfToken,
        },
        form: {
          moyen_paiement: 'espece',
          uuid_pv: restaurantPvUuid,
          given_sum: '3000',
        },
      });

      expect(response.status()).toBe(200);
      const body = await response.text();
      // L'écran de succès doit contenir "paiement-succes"
      // The success screen must contain "paiement-succes"
      expect(body).toContain('paiement-succes');
      console.log('✓ Paiement espèces réussi');
    });

    await test.step('Vérif DB : PAID, table LIBRE, LigneArticle / DB check: PAID, table FREE, LigneArticle', async () => {
      const result = djangoShell(`
from laboutik.models import Table, CommandeSauvegarde
from BaseBillet.models import LigneArticle
from django.utils import timezone
from datetime import timedelta
cmd = CommandeSauvegarde.objects.get(uuid='${commandeUuid}')
table = Table.objects.get(uuid='${tableUuid}')
now = timezone.now()
lignes = LigneArticle.objects.filter(
    datetime__gte=now - timedelta(minutes=3),
    payment_method='CA',
    sale_origin='LB',
).order_by('-datetime')
noms_lignes = [l.pricesold.productsold.product.name for l in lignes[:5]]
print(f'CMD_STATUT={cmd.statut}')
print(f'TABLE_STATUT={table.statut}')
print(f'LIGNES={len(noms_lignes)} NOMS={",".join(noms_lignes)}')
`);
      console.log('DB payer:', result);
      expect(result).toContain('CMD_STATUT=PA');
      expect(result).toContain('TABLE_STATUT=L');
      expect(result).toContain('Pizza');
      expect(result).toContain('Cafe');
      expect(result).toContain('Burger');
      console.log('✓ Commande PAID, table LIBRE, LigneArticle Pizza+Cafe+Burger créées');
    });
  });

  // ==========================================================================
  // TEST 3 : API — Annuler une commande libère la table
  // TEST 3: API — Cancelling an order frees the table
  // ==========================================================================

  test('annuler une commande libère la table / cancelling an order frees the table', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto(`/laboutik/caisse/`);
    await page.waitForLoadState('networkidle');

    let commandeUuid: string;

    await test.step('Ouvrir commande / Open order', async () => {
      const csrfToken = await page.evaluate(() => {
        const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
      });

      const response = await page.request.post('/laboutik/commande/ouvrir/', {
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        data: {
          table_uuid: tableUuid,
          uuid_pv: restaurantPvUuid,
          articles: [
            { product_uuid: cafeProductUuid, price_uuid: cafePriceUuid, qty: 1 },
          ],
        },
      });
      expect(response.status()).toBe(201);

      // Récupérer l'UUID de la commande
      // Get the order UUID
      const result = djangoShell(`
from laboutik.models import Table, CommandeSauvegarde
table = Table.objects.get(uuid='${tableUuid}')
cmd = CommandeSauvegarde.objects.filter(table=table, statut=CommandeSauvegarde.OPEN).order_by('-datetime').first()
print(f'UUID={cmd.uuid}')
print(f'TABLE_STATUT={table.statut}')
`);
      const match = result.match(/UUID=(.+)/);
      expect(match).toBeTruthy();
      commandeUuid = match![1].trim();
      expect(result).toContain('TABLE_STATUT=O');
      console.log(`✓ Commande ${commandeUuid} ouverte, table OCCUPEE`);
    });

    await test.step('Annuler la commande / Cancel the order', async () => {
      const csrfToken = await page.evaluate(() => {
        const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
      });

      const response = await page.request.post(`/laboutik/commande/annuler/${commandeUuid}/`, {
        headers: {
          'X-CSRFToken': csrfToken,
        },
      });
      expect(response.status()).toBe(200);
      console.log('✓ Commande annulée (200)');
    });

    await test.step('Vérif DB : CANCEL, table LIBRE / DB check: CANCEL, table FREE', async () => {
      const result = djangoShell(`
from laboutik.models import Table, CommandeSauvegarde, ArticleCommandeSauvegarde
cmd = CommandeSauvegarde.objects.get(uuid='${commandeUuid}')
table = Table.objects.get(uuid='${tableUuid}')
statuts_articles = list(cmd.articles.values_list('statut', flat=True))
print(f'CMD_STATUT={cmd.statut}')
print(f'TABLE_STATUT={table.statut}')
print(f'ART_STATUTS={",".join(statuts_articles)}')
`);
      console.log('DB annuler:', result);
      expect(result).toContain('CMD_STATUT=AN');
      expect(result).toContain('TABLE_STATUT=L');
      // Tous les articles doivent être ANNULE (AN)
      // All articles must be CANCELLED (AN)
      const artStatuts = result.match(/ART_STATUTS=(.+)/);
      expect(artStatuts).toBeTruthy();
      const statuts = artStatuts![1].split(',');
      for (const s of statuts) {
        expect(s.trim()).toBe('AN');
      }
      console.log('✓ Commande CANCEL, table LIBRE, articles ANNULE');
    });
  });

  // ==========================================================================
  // TEST 4 : API — Annuler une commande payée est interdit
  // TEST 4: API — Cancelling a paid order is forbidden
  // ==========================================================================

  test('annuler une commande payée retourne 400 / cancelling a paid order returns 400', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto(`/laboutik/caisse/`);
    await page.waitForLoadState('networkidle');

    // Créer et payer une commande en DB
    // Create and pay an order in DB
    const result = djangoShell(`
from laboutik.models import Table, CommandeSauvegarde, ArticleCommandeSauvegarde
from BaseBillet.models import Product, Price
table = Table.objects.get(uuid='${tableUuid}')
produit = Product.objects.get(uuid='${cafeProductUuid}')
prix = Price.objects.get(uuid='${cafePriceUuid}')
cmd = CommandeSauvegarde.objects.create(
    table=table,
    statut=CommandeSauvegarde.PAID,
    commentaire='[pw_test] commande payee',
)
ArticleCommandeSauvegarde.objects.create(
    commande=cmd, product=produit, price=prix, qty=1,
    reste_a_payer=0, reste_a_servir=0,
    statut=ArticleCommandeSauvegarde.SERVI,
)
print(f'UUID={cmd.uuid}')
`);
    const match = result.match(/UUID=(.+)/);
    expect(match).toBeTruthy();
    const commandePaidUuid = match![1].trim();
    console.log(`✓ Commande PAID ${commandePaidUuid} créée en DB`);

    await test.step('POST annuler → 400 / POST cancel → 400', async () => {
      const csrfToken = await page.evaluate(() => {
        const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
      });

      const response = await page.request.post(`/laboutik/commande/annuler/${commandePaidUuid}/`, {
        headers: {
          'X-CSRFToken': csrfToken,
        },
      });
      expect(response.status()).toBe(400);
      const body = await response.text();
      expect(body.toLowerCase()).toContain('annul');
      console.log('✓ Annulation refusée (400) pour commande payée');
    });
  });

  // ==========================================================================
  // TEST 5 : API — Table reste occupée si autre commande ouverte
  // TEST 5: API — Table stays occupied if another order is open
  // ==========================================================================

  test('table reste occupée si autre commande ouverte / table stays occupied if another open order', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto(`/laboutik/caisse/`);
    await page.waitForLoadState('networkidle');

    let commande1Uuid: string;
    let commande2Uuid: string;

    await test.step('Ouvrir 2 commandes sur la même table / Open 2 orders on the same table', async () => {
      const csrfToken = await page.evaluate(() => {
        const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
      });

      // Commande 1 : Pizza
      // Order 1: Pizza
      const r1 = await page.request.post('/laboutik/commande/ouvrir/', {
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        data: {
          table_uuid: tableUuid,
          uuid_pv: restaurantPvUuid,
          articles: [{ product_uuid: pizzaProductUuid, price_uuid: pizzaPriceUuid, qty: 1 }],
        },
      });
      expect(r1.status()).toBe(201);

      // Commande 2 : Cafe
      // Order 2: Cafe
      const r2 = await page.request.post('/laboutik/commande/ouvrir/', {
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        data: {
          table_uuid: tableUuid,
          uuid_pv: restaurantPvUuid,
          articles: [{ product_uuid: cafeProductUuid, price_uuid: cafePriceUuid, qty: 1 }],
        },
      });
      expect(r2.status()).toBe(201);

      // Récupérer les UUIDs des 2 commandes
      // Get the UUIDs of both orders
      const result = djangoShell(`
from laboutik.models import Table, CommandeSauvegarde
table = Table.objects.get(uuid='${tableUuid}')
cmds = CommandeSauvegarde.objects.filter(
    table=table, statut=CommandeSauvegarde.OPEN,
).order_by('datetime')
for cmd in cmds:
    print(f'CMD={cmd.uuid}')
`);
      const uuids = result.split('\n').filter(l => l.startsWith('CMD=')).map(l => l.replace('CMD=', '').trim());
      expect(uuids.length).toBeGreaterThanOrEqual(2);
      commande1Uuid = uuids[0];
      commande2Uuid = uuids[1];
      console.log(`✓ 2 commandes ouvertes : ${commande1Uuid}, ${commande2Uuid}`);
    });

    await test.step('Annuler commande 1 → table reste OCCUPEE / Cancel order 1 → table stays OCCUPIED', async () => {
      const csrfToken = await page.evaluate(() => {
        const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
      });

      const response = await page.request.post(`/laboutik/commande/annuler/${commande1Uuid}/`, {
        headers: { 'X-CSRFToken': csrfToken },
      });
      expect(response.status()).toBe(200);

      const result = djangoShell(`
from laboutik.models import Table
table = Table.objects.get(uuid='${tableUuid}')
print(f'TABLE_STATUT={table.statut}')
`);
      console.log('DB après annulation cmd1:', result);
      // La table doit rester OCCUPEE car commande 2 est encore OPEN
      // Table must stay OCCUPIED because order 2 is still OPEN
      expect(result).toContain('TABLE_STATUT=O');
      console.log('✓ Table reste OCCUPEE après annulation de la commande 1');
    });

    await test.step('Annuler commande 2 → table LIBRE / Cancel order 2 → table FREE', async () => {
      const csrfToken = await page.evaluate(() => {
        const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
      });

      const response = await page.request.post(`/laboutik/commande/annuler/${commande2Uuid}/`, {
        headers: { 'X-CSRFToken': csrfToken },
      });
      expect(response.status()).toBe(200);

      const result = djangoShell(`
from laboutik.models import Table
table = Table.objects.get(uuid='${tableUuid}')
print(f'TABLE_STATUT={table.statut}')
`);
      console.log('DB après annulation cmd2:', result);
      // Plus aucune commande ouverte → table LIBRE
      // No more open orders → table FREE
      expect(result).toContain('TABLE_STATUT=L');
      console.log('✓ Table LIBRE après annulation des 2 commandes');
    });
  });

  // ==========================================================================
  // TEST 6 : UI — Flow complet table → ajout articles → paiement espèces
  // TEST 6: UI — Full flow table → add articles → cash payment
  // ==========================================================================

  test('UI flow complet : table → articles → payer espèces / UI full flow: table → articles → pay cash', async ({ page }) => {
    // Désactiver service_direct pour voir les tables
    // Disable service_direct to see the tables
    djangoShell(`
from laboutik.models import PointDeVente
pv = PointDeVente.objects.get(uuid='${restaurantPvUuid}')
pv.service_direct = False
pv.save(update_fields=['service_direct'])
`);

    await loginAsAdmin(page);

    await test.step('Sélectionner la table / Select the table', async () => {
      await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${restaurantPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
      await page.waitForLoadState('networkidle');

      // Vérifier que la barre de statut de la table est verte (LIBRE = --vert02)
      // Verify the table status bar is green (LIBRE = --vert02)
      const tableBtn = page.locator('.table-bouton').filter({ hasText: tableName });
      await expect(tableBtn).toBeVisible({ timeout: 10000 });
      const statusBar = tableBtn.locator('.table-etat');
      const bgStyle = await statusBar.getAttribute('style');
      expect(bgStyle).toContain('--vert02');
      console.log('✓ Table affichée avec statut vert (LIBRE)');

      // Cliquer sur la table
      // Click the table
      await tableBtn.click();
      await page.waitForLoadState('networkidle');
      await expect(page.locator('[data-testid="caisse-pv-interface"]')).toBeVisible({ timeout: 10000 });
      console.log('✓ POS chargé depuis la table');
    });

    await test.step('Ajouter Pizza au panier / Add Pizza to cart', async () => {
      const pizzaTile = page.locator('#products .article-container').filter({ hasText: 'Pizza' }).first();
      await expect(pizzaTile).toBeVisible({ timeout: 10000 });
      await pizzaTile.click();
      await expect(page.locator('#addition-list')).toContainText('Pizza', { timeout: 5000 });
      console.log('✓ Pizza ajoutée au panier');
    });

    await test.step('Ajouter Cafe au panier / Add Cafe to cart', async () => {
      const cafeTile = page.locator('#products .article-container').filter({ hasText: 'Cafe' }).first();
      await expect(cafeTile).toBeVisible({ timeout: 5000 });
      await cafeTile.click();
      await expect(page.locator('#addition-list')).toContainText('Cafe', { timeout: 5000 });
      console.log('✓ Cafe ajouté au panier');
    });

    await test.step('VALIDER → ESPÈCE → confirmer / VALIDER → CASH → confirm', async () => {
      await page.locator('#bt-valider').click();
      await expect(page.locator('[data-testid="paiement-moyens"]')).toBeVisible({ timeout: 10000 });
      console.log('✓ Panneau des modes de paiement visible');

      await page.locator('[data-testid="paiement-moyens"]').getByText('ESPÈCE').click();
      await expect(page.locator('[data-testid="paiement-confirmation"]')).toBeVisible({ timeout: 10000 });
      console.log('✓ Écran de confirmation espèces');

      await page.locator('#bt-valider-layer2').click();
      await expect(page.locator('[data-testid="paiement-succes"]')).toBeVisible({ timeout: 15000 });

      const successText = await page.locator('[data-testid="paiement-succes"]').innerText();
      expect(successText.toLowerCase()).toContain('espèce');
      console.log(`✓ Paiement espèces réussi depuis table. Texte : ${successText.substring(0, 80)}`);
    });

    await test.step('Vérif DB — LigneArticle Pizza + Cafe / DB check — Pizza + Cafe LigneArticle', async () => {
      const result = djangoShell(`
from BaseBillet.models import LigneArticle
from django.utils import timezone
from datetime import timedelta
now = timezone.now()
lignes = LigneArticle.objects.filter(
    datetime__gte=now - timedelta(minutes=3),
    payment_method='CA',
    sale_origin='LB',
).order_by('-datetime')
noms = [l.pricesold.productsold.product.name for l in lignes[:5]]
print(f'LIGNES={len(noms)} NOMS={",".join(noms)}')
`);
      console.log('DB LigneArticle:', result);
      expect(result).toContain('Pizza');
      expect(result).toContain('Cafe');
      console.log('✓ LigneArticle Pizza + Cafe confirmées en base');
    });

    await test.step('Retour aux tables — vérifier statut / Back to tables — check status', async () => {
      // Retourner à la page de sélection de tables
      // Go back to the table selection page
      await page.locator('[data-testid="paiement-succes"] #bt-retour-layer1').click();
      await expect(page.locator('[data-testid="paiement-succes"]')).not.toBeVisible({ timeout: 5000 });

      // Recharger la page tables pour vérifier le statut
      // Reload the tables page to check the status
      await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${restaurantPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
      await page.waitForLoadState('networkidle');

      // La table doit toujours être LIBRE (le paiement via PaiementViewSet
      // ne change pas le statut de la table — seul CommandeViewSet le fait)
      // Table should still be FREE (payment via PaiementViewSet
      // does not change table status — only CommandeViewSet does)
      const tableBtn = page.locator('.table-bouton').filter({ hasText: tableName });
      await expect(tableBtn).toBeVisible({ timeout: 10000 });
      const statusBar = tableBtn.locator('.table-etat');
      const bgStyle = await statusBar.getAttribute('style');
      expect(bgStyle).toContain('--vert02');
      console.log('✓ Table toujours LIBRE (paiement direct ne change pas le statut table)');

      // Restaurer service_direct
      // Restore service_direct
      djangoShell(`
from laboutik.models import PointDeVente
pv = PointDeVente.objects.get(uuid='${restaurantPvUuid}')
pv.service_direct = True
pv.save(update_fields=['service_direct'])
`);
    });
  });

  // ==========================================================================
  // TEST 7 : UI — Couleurs de statut des tables (vert/rouge/orange)
  // TEST 7: UI — Table status colors (green/red/orange)
  // ==========================================================================

  test('UI couleurs de statut des tables / UI table status colors', async ({ page }) => {
    // Désactiver service_direct
    // Disable service_direct
    djangoShell(`
from laboutik.models import PointDeVente
pv = PointDeVente.objects.get(uuid='${restaurantPvUuid}')
pv.service_direct = False
pv.save(update_fields=['service_direct'])
`);

    await loginAsAdmin(page);

    await test.step('Table LIBRE → barre verte / FREE table → green bar', async () => {
      // La table est LIBRE (nettoyée par beforeEach)
      // Table is FREE (cleaned by beforeEach)
      await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${restaurantPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
      await page.waitForLoadState('networkidle');

      const tableBtn = page.locator('.table-bouton').filter({ hasText: tableName });
      const statusBar = tableBtn.locator('.table-etat');
      const bgStyle = await statusBar.getAttribute('style');
      expect(bgStyle).toContain('--vert02');
      console.log('✓ LIBRE → barre verte (--vert02)');
    });

    await test.step('Table OCCUPEE → barre rouge / OCCUPIED table → red bar', async () => {
      // Passer la table en OCCUPEE via DB
      // Set the table to OCCUPIED via DB
      djangoShell(`
from laboutik.models import Table
table = Table.objects.get(uuid='${tableUuid}')
table.statut = Table.OCCUPEE
table.save(update_fields=['statut'])
`);

      await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${restaurantPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
      await page.waitForLoadState('networkidle');

      const tableBtn = page.locator('.table-bouton').filter({ hasText: tableName });
      const statusBar = tableBtn.locator('.table-etat');
      const bgStyle = await statusBar.getAttribute('style');
      expect(bgStyle).toContain('--rouge01');
      console.log('✓ OCCUPEE → barre rouge (--rouge01)');
    });

    await test.step('Table SERVIE → barre orange / SERVED table → orange bar', async () => {
      // Passer la table en SERVIE via DB
      // Set the table to SERVED via DB
      djangoShell(`
from laboutik.models import Table
table = Table.objects.get(uuid='${tableUuid}')
table.statut = Table.SERVIE
table.save(update_fields=['statut'])
`);

      await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${restaurantPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
      await page.waitForLoadState('networkidle');

      const tableBtn = page.locator('.table-bouton').filter({ hasText: tableName });
      const statusBar = tableBtn.locator('.table-etat');
      const bgStyle = await statusBar.getAttribute('style');
      expect(bgStyle).toContain('--orange01');
      console.log('✓ SERVIE → barre orange (--orange01)');

      // Restaurer service_direct
      // Restore service_direct
      djangoShell(`
from laboutik.models import PointDeVente
pv = PointDeVente.objects.get(uuid='${restaurantPvUuid}')
pv.service_direct = True
pv.save(update_fields=['service_direct'])
`);
    });
  });
});
