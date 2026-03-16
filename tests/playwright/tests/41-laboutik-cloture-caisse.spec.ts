import { test, expect } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';
import { execSync } from 'child_process';

/**
 * TEST: LaBoutik POS — Clôture de caisse (Phase 5)
 * TEST: LaBoutik POS — Cash register closure (Phase 5)
 *
 * LOCALISATION : tests/playwright/tests/41-laboutik-cloture-caisse.spec.ts
 *
 * Objectif :
 * - Faire des paiements espèces, CB et NFC pour créer des LigneArticle variées
 * - Déclencher la clôture de caisse via POST /laboutik/caisse/cloturer/
 * - Vérifier le rapport (data-testid, totaux par moyen de paiement, ventilation TVA)
 * - Vérifier la ClotureCaisse en DB avec rapport_json complet
 * - Vérifier que les tables OCCUPEE sont passées LIBRE
 * - Vérifier que les commandes OPEN sont annulées
 *
 * Goal:
 * - Make cash, CB and NFC payments to create varied LigneArticle records
 * - Trigger cash register closure via POST /laboutik/caisse/cloturer/
 * - Verify the report (data-testid, totals by payment method, VAT breakdown)
 * - Verify ClotureCaisse in DB with complete rapport_json
 * - Verify OCCUPIED tables are freed
 * - Verify OPEN orders are cancelled
 *
 * Prérequis / Prerequisites:
 * - create_test_pos_data must have been run
 * - Bar POS must exist with "Biere" and "Coca" products
 * - Primary card A49E8E2A must exist
 * - A CarteCashless with sufficient balance for NFC payment
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

test.describe('LaBoutik POS — Clôture de caisse / Cash register closure', () => {

  /**
   * UUID du point de vente Bar — récupéré dynamiquement depuis la base de données
   * Bar POS UUID — fetched dynamically from the database
   */
  let barPvUuid: string;

  /**
   * Timestamp ISO avant les paiements — utilisé comme datetime_ouverture
   * ISO timestamp before payments — used as datetime_ouverture
   */
  let timestampAvantPaiement: string;

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
    console.log(`Bar POS UUID trouvé : ${barPvUuid}`);

    // Récupérer le timestamp courant depuis Django (évite les décalages)
    // Get current timestamp from Django (avoids timezone mismatch)
    const tsResult = djangoShell(`
from django.utils import timezone
print(timezone.now().isoformat())
`);
    timestampAvantPaiement = tsResult.split('\n').pop()!.trim();
    console.log(`Timestamp avant paiement : ${timestampAvantPaiement}`);
  });

  /**
   * TEST 1 : 3 types de paiement (espèces + CB + NFC) puis clôture
   * TEST 1: 3 payment types (cash + card + NFC) then closure
   *
   * FLUX / FLOW :
   * 1. Login admin → naviguer vers la caisse Bar
   * 2. Payer Biere par espèces
   * 3. Payer Coca par CB
   * 4. Créer une LigneArticle NFC directement en base (simulation paiement cashless)
   * 5. POST /laboutik/caisse/cloturer/
   * 6. Vérifier le rapport HTML (data-testid, totaux)
   * 7. Vérifier la ClotureCaisse en DB (rapport_json : par_moyen_paiement, par_produit, par_tva)
   */
  test('3 paiements puis clôture complète / 3 payments then full closure', async ({ page }) => {

    // --- Connexion admin ---
    // --- Admin login ---
    await loginAsAdmin(page);
    await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${barPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
    await page.waitForLoadState('networkidle');

    // =========================================================================
    // PAIEMENT 1 : Biere par espèces
    // PAYMENT 1: Biere via cash
    // =========================================================================

    await test.step('Paiement espèces — Biere / Cash payment — Biere', async () => {
      const biereTile = page.locator('#products .article-container').filter({ hasText: 'Biere' }).first();
      await expect(biereTile).toBeVisible({ timeout: 10000 });
      await biereTile.click();
      await expect(page.locator('#addition-list')).toContainText('Biere', { timeout: 5000 });

      await page.locator('#bt-valider').click();
      await expect(page.locator('[data-testid="paiement-moyens"]')).toBeVisible({ timeout: 10000 });
      await page.locator('[data-testid="paiement-moyens"]').getByText('ESPÈCE').click();
      await expect(page.locator('[data-testid="paiement-confirmation"]')).toBeVisible({ timeout: 10000 });
      await page.locator('#bt-valider-layer2').click();
      await expect(page.locator('[data-testid="paiement-succes"]')).toBeVisible({ timeout: 15000 });
      console.log('Paiement 1 : espèces Biere OK');

      // Retour
      await page.locator('[data-testid="paiement-succes"] #bt-retour-layer1').click();
      await expect(page.locator('[data-testid="paiement-succes"]')).not.toBeVisible({ timeout: 5000 });
    });

    // =========================================================================
    // PAIEMENT 2 : Coca par CB
    // PAYMENT 2: Coca via card
    // =========================================================================

    await test.step('Paiement CB — Coca / Card payment — Coca', async () => {
      const cocaTile = page.locator('#products .article-container').filter({ hasText: 'Coca' }).first();
      await expect(cocaTile).toBeVisible({ timeout: 5000 });
      await cocaTile.click();
      await expect(page.locator('#addition-list')).toContainText('Coca', { timeout: 5000 });

      await page.locator('#bt-valider').click();
      await expect(page.locator('[data-testid="paiement-moyens"]')).toBeVisible({ timeout: 10000 });
      await page.locator('[data-testid="paiement-moyens"]').getByText('CB').click();
      await expect(page.locator('[data-testid="paiement-confirmation"]')).toBeVisible({ timeout: 10000 });
      await page.locator('#bt-valider-layer2').click();
      await expect(page.locator('[data-testid="paiement-succes"]')).toBeVisible({ timeout: 15000 });
      console.log('Paiement 2 : CB Coca OK');

      // Retour
      await page.locator('[data-testid="paiement-succes"] #bt-retour-layer1').click();
      await expect(page.locator('[data-testid="paiement-succes"]')).not.toBeVisible({ timeout: 5000 });
    });

    // =========================================================================
    // PAIEMENT 3 : NFC (via DB directe — pas de hardware NFC en test)
    // PAYMENT 3: NFC (via direct DB — no NFC hardware in test)
    // =========================================================================

    await test.step('Créer paiement NFC en base / Create NFC payment in DB', async () => {
      // Créer une LigneArticle avec payment_method=LOCAL_EURO pour simuler un paiement NFC
      // Create a LigneArticle with payment_method=LOCAL_EURO to simulate NFC payment
      const result = djangoShell(`
from BaseBillet.models import LigneArticle, Product, Price, PriceSold, ProductSold, SaleOrigin, PaymentMethod
from decimal import Decimal

# Récupérer le produit Biere pour le NFC
# Get the Biere product for NFC
product = Product.objects.filter(name='Biere').first()
price = product.prices.first()

# Créer ProductSold + PriceSold pour la LigneArticle NFC
# Create ProductSold + PriceSold for the NFC LigneArticle
product_sold, _ = ProductSold.objects.get_or_create(
    product=product,
    defaults={'name': product.name, 'categorie_article': product.categorie_article},
)
price_sold, _ = PriceSold.objects.get_or_create(
    productsold=product_sold,
    price=price,
    prix=price.prix,
)
# Créer la LigneArticle NFC (500 centimes = 5€)
# Create the NFC LigneArticle (500 cents = 5€)
ligne = LigneArticle.objects.create(
    pricesold=price_sold,
    qty=1,
    amount=500,
    payment_method=PaymentMethod.LOCAL_EURO,
    sale_origin=SaleOrigin.LABOUTIK,
    status=LigneArticle.VALID,
)
print(f'nfc_ok pk={str(ligne.pk)[:8]} pm={ligne.payment_method} amount={ligne.amount}')
`);
      console.log('NFC DB result:', result);
      expect(result).toContain('nfc_ok');
      expect(result).toContain('pm=LE');
      console.log('Paiement 3 : NFC simulé en base OK');
    });

    // =========================================================================
    // CLÔTURE : POST /laboutik/caisse/cloturer/
    // CLOSURE: POST /laboutik/caisse/cloturer/
    // =========================================================================

    await test.step('Clôture de caisse / Cash register closure', async () => {
      const csrfToken = await page.evaluate(() => {
        const meta = document.querySelector('[name=csrfmiddlewaretoken]') as HTMLInputElement;
        if (meta) return meta.value;
        const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
      });

      const responseHtml = await page.evaluate(
        async ([url, csrf, dtOuverture, uuidPv]) => {
          const formData = new FormData();
          formData.append('datetime_ouverture', dtOuverture);
          formData.append('uuid_pv', uuidPv);
          const response = await fetch(url, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrf },
            body: formData,
          });
          return { status: response.status, html: await response.text() };
        },
        ['/laboutik/caisse/cloturer/', csrfToken, timestampAvantPaiement, barPvUuid]
      );

      expect(responseHtml.status).toBe(200);
      console.log(`Clôture POST status: ${responseHtml.status}`);

      // Injecter le HTML du rapport dans la page
      // Inject the report HTML into the page
      await page.evaluate((html) => {
        const container = document.createElement('div');
        container.id = 'cloture-test-container';
        container.innerHTML = html;
        document.body.appendChild(container);
      }, responseHtml.html);

      // Vérifier les data-testid du rapport
      // Verify report data-testid attributes
      await expect(page.locator('[data-testid="cloture-rapport"]')).toBeVisible({ timeout: 5000 });
      await expect(page.locator('[data-testid="cloture-totaux"]')).toBeVisible();
      await expect(page.locator('[data-testid="cloture-total-especes"]')).toBeVisible();
      await expect(page.locator('[data-testid="cloture-total-cb"]')).toBeVisible();
      await expect(page.locator('[data-testid="cloture-total-nfc"]')).toBeVisible();
      await expect(page.locator('[data-testid="cloture-total-general"]')).toBeVisible();

      // Les 3 totaux doivent être > 0 (espèces, CB, NFC)
      // All 3 totals must be > 0 (cash, card, NFC)
      const espText = await page.locator('[data-testid="cloture-total-especes"]').innerText();
      const cbText = await page.locator('[data-testid="cloture-total-cb"]').innerText();
      const nfcText = await page.locator('[data-testid="cloture-total-nfc"]').innerText();
      console.log(`Espèces: ${espText} | CB: ${cbText} | NFC: ${nfcText}`);

      expect(espText).not.toContain(': 0.0');
      expect(cbText).not.toContain(': 0.0');
      expect(nfcText).not.toContain(': 0.0');
      console.log('Rapport : 3 types de paiement avec totaux > 0');
    });

    // =========================================================================
    // VÉRIFICATIONS DB — rapport_json complet (moyen paiement, produit, TVA)
    // DB VERIFICATION — complete rapport_json (payment method, product, VAT)
    // =========================================================================

    await test.step('Vérif DB — totaux par moyen de paiement / DB check — totals by payment method', async () => {
      const result = djangoShell(`
from laboutik.models import ClotureCaisse
from django.utils import timezone
from datetime import timedelta
now = timezone.now()
cloture = ClotureCaisse.objects.filter(
    datetime_cloture__gte=now - timedelta(minutes=5),
).order_by('-datetime_cloture').first()
if cloture:
    r = cloture.rapport_json
    mp = r.get('par_moyen_paiement', {})
    print(f'especes={mp.get("especes", 0)} cb={mp.get("cb", 0)} nfc={mp.get("nfc", 0)}')
    print(f'total_general={cloture.total_general} nb_tx={cloture.nombre_transactions}')
else:
    print('NOT_FOUND')
`);
      console.log('DB par_moyen_paiement:', result);
      expect(result).not.toContain('NOT_FOUND');
      // Vérifier que chaque moyen de paiement a un montant > 0
      // Verify each payment method has amount > 0
      expect(result).toMatch(/especes=\d+/);
      expect(result).toMatch(/cb=\d+/);
      expect(result).toMatch(/nfc=\d+/);
      expect(result).not.toMatch(/especes=0\b/);
      expect(result).not.toMatch(/cb=0\b/);
      expect(result).not.toMatch(/nfc=0\b/);
      console.log('3 moyens de paiement avec montants > 0 en DB');
    });

    await test.step('Vérif DB — ventilation TVA / DB check — VAT breakdown', async () => {
      const result = djangoShell(`
from laboutik.models import ClotureCaisse
from django.utils import timezone
from datetime import timedelta
now = timezone.now()
cloture = ClotureCaisse.objects.filter(
    datetime_cloture__gte=now - timedelta(minutes=5),
).order_by('-datetime_cloture').first()
if cloture:
    r = cloture.rapport_json
    par_tva = r.get('par_tva', {})
    print(f'nb_taux={len(par_tva)}')
    for taux, data in par_tva.items():
        print(f'tva_{taux}: ht={data["total_ht"]} tva={data["total_tva"]} ttc={data["total_ttc"]}')
else:
    print('NOT_FOUND')
`);
      console.log('DB par_tva:', result);
      expect(result).not.toContain('NOT_FOUND');
      // Au moins un taux TVA doit être présent
      // At least one VAT rate must be present
      expect(result).toMatch(/nb_taux=\d+/);
      expect(result).not.toContain('nb_taux=0');
      console.log('Ventilation TVA présente dans rapport_json');
    });

    await test.step('Vérif DB — rapport par produit / DB check — report by product', async () => {
      const result = djangoShell(`
from laboutik.models import ClotureCaisse
from django.utils import timezone
from datetime import timedelta
now = timezone.now()
cloture = ClotureCaisse.objects.filter(
    datetime_cloture__gte=now - timedelta(minutes=5),
).order_by('-datetime_cloture').first()
if cloture:
    r = cloture.rapport_json
    par_produit = r.get('par_produit', {})
    print(f'nb_produits={len(par_produit)}')
    for nom, data in par_produit.items():
        print(f'produit={nom} total={data["total"]} qty={data["qty"]}')
else:
    print('NOT_FOUND')
`);
      console.log('DB par_produit:', result);
      expect(result).not.toContain('NOT_FOUND');
      // Au moins 2 produits (Biere + Coca)
      // At least 2 products (Biere + Coca)
      expect(result).toContain('produit=Biere');
      expect(result).toContain('produit=Coca');
      console.log('Rapport par produit : Biere et Coca présents');
    });
  });

  /**
   * TEST 2 : Vérification admin Django — ClotureCaisse visible
   * TEST 2: Django admin verification — ClotureCaisse visible
   */
  test('vérification admin ClotureCaisse / admin ClotureCaisse verification', async ({ page }) => {
    await loginAsAdmin(page);

    await page.goto('/admin/laboutik/cloturecaisse/');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('body')).not.toContainText('Page not found');
    await expect(page.locator('body')).not.toContainText('Not Found');

    const rows = page.locator('#result_list tbody tr');
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);
    console.log(`Admin ClotureCaisse : ${rowCount} clôture(s) visible(s)`);
  });

  /**
   * TEST 3 : La clôture ferme les tables et annule les commandes
   * TEST 3: Closure frees tables and cancels orders
   */
  test('clôture ferme tables et annule commandes / closure frees tables and cancels orders', async ({ page }) => {
    await loginAsAdmin(page);

    // Créer une table OCCUPEE et une commande OPEN en base
    // Create an OCCUPIED table and an OPEN order in DB
    const setupResult = djangoShell(`
from laboutik.models import Table, CategorieTable, CommandeSauvegarde
import uuid as uuid_mod

cat, _ = CategorieTable.objects.get_or_create(
    name='[PW-test-cloture] Salle',
    defaults={'icon': 'bi-house'},
)
table = Table.objects.create(
    name=f'[PW-test-cloture] T{uuid_mod.uuid4().hex[:4]}',
    categorie=cat,
    statut=Table.OCCUPEE,
)
commande = CommandeSauvegarde.objects.create(
    table=table,
    statut=CommandeSauvegarde.OPEN,
)
print(f'table_pk={table.pk} table_statut={table.statut} commande_pk={commande.pk} commande_statut={commande.statut}')
`);
    console.log('Setup tables/commandes:', setupResult);
    expect(setupResult).toContain('table_statut=O');
    expect(setupResult).toContain('commande_statut=OP');

    const tablePkMatch = setupResult.match(/table_pk=(\S+)/);
    const commandePkMatch = setupResult.match(/commande_pk=(\S+)/);
    const tablePk = tablePkMatch ? tablePkMatch[1] : '';
    const commandePk = commandePkMatch ? commandePkMatch[1] : '';

    // Naviguer vers la caisse pour le CSRF
    // Navigate to POS for CSRF
    await page.goto(`/laboutik/caisse/point_de_vente/?uuid_pv=${barPvUuid}&tag_id_cm=${DEMO_TAGID_CM}`);
    await page.waitForLoadState('networkidle');

    const csrfToken = await page.evaluate(() => {
      const meta = document.querySelector('[name=csrfmiddlewaretoken]') as HTMLInputElement;
      if (meta) return meta.value;
      const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
      return cookie ? cookie.split('=')[1] : '';
    });

    // Clôture avec datetime_ouverture = 12h avant (couvre toute la journée)
    // Closure with datetime_ouverture = 12h ago (covers the whole day)
    const tsNow = djangoShell(`
from django.utils import timezone
from datetime import timedelta
print((timezone.now() - timedelta(hours=12)).isoformat())
`).split('\n').pop()!.trim();

    const responseHtml = await page.evaluate(
      async ([url, csrf, dtOuverture, uuidPv]) => {
        const formData = new FormData();
        formData.append('datetime_ouverture', dtOuverture);
        formData.append('uuid_pv', uuidPv);
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrf },
          body: formData,
        });
        return { status: response.status };
      },
      ['/laboutik/caisse/cloturer/', csrfToken, tsNow, barPvUuid]
    );

    expect(responseHtml.status).toBe(200);
    console.log('Clôture POST status:', responseHtml.status);

    await test.step('Table LIBRE après clôture / Table FREE after closure', async () => {
      const result = djangoShell(`
from laboutik.models import Table
table = Table.objects.filter(pk='${tablePk}').first()
if table:
    print(f'statut={table.statut}')
else:
    print('NOT_FOUND')
`);
      console.log('DB table:', result);
      expect(result).toContain('statut=L');
    });

    await test.step('Commande annulée après clôture / Order cancelled after closure', async () => {
      const result = djangoShell(`
from laboutik.models import CommandeSauvegarde
cmd = CommandeSauvegarde.objects.filter(pk='${commandePk}').first()
if cmd:
    print(f'statut={cmd.statut}')
else:
    print('NOT_FOUND')
`);
      console.log('DB commande:', result);
      // CommandeSauvegarde.CANCEL = 'AN'
      expect(result).toContain('statut=AN');
    });

    // Nettoyage / Cleanup
    djangoShell(`
from laboutik.models import Table, CategorieTable, CommandeSauvegarde
CommandeSauvegarde.objects.filter(pk='${commandePk}').delete()
Table.objects.filter(pk='${tablePk}').delete()
CategorieTable.objects.filter(name='[PW-test-cloture] Salle').delete()
`);
  });
});
