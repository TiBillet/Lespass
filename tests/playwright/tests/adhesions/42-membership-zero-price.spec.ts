import { test, expect } from '@playwright/test';
import { loginAs, loginAsAdmin } from '../utils/auth';
import { verifyDbData } from '../utils/db';
import { fillStripeCard } from '../utils/stripe';
import { env } from '../utils/env';

/**
 * TEST : Adhésion prix libre à 0€ et à 1€ sur le même produit
 * / Free price membership at 0€ and 1€ on the same product
 *
 * LOCALISATION : tests/playwright/tests/42-membership-zero-price.spec.ts
 *
 * Contexte :
 * Quand un utilisateur entre 0€ pour un prix libre, le paiement ne doit pas
 * passer par Stripe. L'adhésion doit être validée directement et le template
 * free_confirmed.html doit s'afficher.
 * Quand l'utilisateur entre 1€, Stripe doit prendre le relais normalement.
 *
 * Context:
 * When a user enters 0€ for a free price, payment must NOT go through Stripe.
 * The membership must be validated immediately and free_confirmed.html shown.
 * When the user enters 1€, Stripe must handle it normally.
 *
 * Scénarios couverts / Scenarios covered :
 * 1. Adhésion 0€ → confirmation directe + vérification compte / 0€ → direct confirm + account check
 * 2. Adhésion 1€ → redirection Stripe + paiement / 1€ → Stripe redirect + payment
 *
 * RÉGRESSION : bug où 0€ prix libre envoyait une session Stripe vide
 * / REGRESSION: bug where 0€ free price sent an empty Stripe session
 */

// Suffixe unique par run pour éviter les conflits de nom de produit entre runs
// Unique suffix per run to avoid product name conflicts between runs
const runId = Date.now().toString(36);

// Nom de produit partagé entre les deux tests du describe
// Product name shared between both tests in the describe block
const productName = `Adhésion prix libre 0€ ${runId}`;

// Emails différents pour les deux tests (un user par test)
// Different emails for both tests (one user per test)
const userEmailZero = `test+zero${runId}@pm.me`;
const userEmailStripe = `test+one${runId}@pm.me`;

test.describe('Membership zero price / Adhésion prix libre zéro', () => {

  /**
   * Création du produit une seule fois avant tous les tests du suite
   * / Create the product once before all tests in the suite
   *
   * On utilise request.post directement (pas besoin d'un navigateur)
   * / We use request.post directly (no browser needed)
   */
  test.beforeAll(async ({ request }) => {
    const productResponse = await request.post(`${env.BASE_URL}/api/v2/products/`, {
      headers: {
        Authorization: `Api-Key ${env.API_KEY}`,
        'Content-Type': 'application/json',
      },
      data: {
        '@context': 'https://schema.org',
        '@type': 'Product',
        name: productName,
        // Catégorie adhésion / Membership category
        category: 'Subscription or membership',
        description: 'Adhésion prix libre avec minimum 0€ — test E2E régression bug Stripe.',
        offers: [
          {
            '@type': 'Offer',
            // Prix minimum 0€, prix libre activé / Minimum price 0€, free price enabled
            name: 'Prix Libre (min 0€)',
            price: '0.00',
            priceCurrency: 'EUR',
            freePrice: true,
          },
        ],
      },
    });

    expect(productResponse.ok(), `Création produit échouée : ${await productResponse.text()}`).toBeTruthy();
    console.log(`✓ Produit créé : "${productName}"`);
  });

  /**
   * TEST 1 : Adhésion à 0€
   * / TEST 1: Membership at 0€
   *
   * Flux attendu / Expected flow :
   * 1. Formulaire rempli avec 0€
   * 2. Soumission → PAS de redirection Stripe
   * 3. Template free_confirmed.html affiché dans l'offcanvas
   * 4. Adhésion visible dans la page "mon compte"
   */
  test('0€ : direct confirmation without Stripe / 0€ : confirmation directe sans Stripe', async ({ page }) => {
    test.setTimeout(90000);

    // ─── ÉTAPE 1 : Aller sur la page des adhésions ───────────────────────────
    // / STEP 1: Navigate to the memberships page
    await test.step('Navigate to memberships / Naviguer vers les adhésions', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('domcontentloaded');
    });

    // ─── ÉTAPE 2 : Ouvrir le panneau d'adhésion ──────────────────────────────
    // / STEP 2: Open the subscription panel
    await test.step('Open subscription panel for the product / Ouvrir le panneau pour ce produit', async () => {
      const productCard = page.locator(`.card:has-text("${productName}")`).first();
      await productCard.locator('button:has-text("Subscribe"), button:has-text("Adhérer")').click();
      await page.waitForSelector('#subscribePanel.show', { state: 'visible' });
      console.log('✓ Panneau adhésion ouvert / Subscription panel opened');
    });

    // ─── ÉTAPE 3 : Remplir le formulaire avec 0€ ─────────────────────────────
    // / STEP 3: Fill the form with 0€
    await test.step('Fill form with 0€ / Remplir le formulaire avec 0€', async () => {
      await page.locator('#subscribePanel input[name="email"]').fill(userEmailZero);
      await page.locator('#subscribePanel input[name="confirm-email"]').fill(userEmailZero);
      await page.locator('#subscribePanel input[name="firstname"]').fill('Zero');
      await page.locator('#subscribePanel input[name="lastname"]').fill('Euro');

      // Sélectionner le tarif "Prix Libre" si plusieurs tarifs existent
      // / Select the "Prix Libre" rate if multiple rates exist
      const priceLabelPrixLibre = page.locator('#subscribePanel label:has-text("Prix Libre")').first();
      if (await priceLabelPrixLibre.isVisible()) {
        await priceLabelPrixLibre.click();
      }

      // Remplir le montant avec 0
      // / Fill the amount with 0
      const freePriceInput = page.locator('#subscribePanel input[type="number"]').first();
      await freePriceInput.fill('0');
      console.log('✓ Formulaire rempli avec 0€ / Form filled with 0€');
    });

    // ─── ÉTAPE 4 : Soumettre et vérifier le template de confirmation ──────────
    // / STEP 4: Submit and verify the confirmation template
    await test.step('Submit and verify free_confirmed template / Soumettre et vérifier le template gratuit', async () => {
      await page.locator('#membership-submit').click();

      // Le template free_confirmed.html doit s'afficher dans l'offcanvas
      // PAS de redirection Stripe — on reste sur la même page
      // / The free_confirmed.html template must appear in the offcanvas
      // / NO Stripe redirect — we stay on the same page
      await expect(
        page.locator('text=Adhésion confirmée !').or(page.locator('text=Membership confirmed'))
      ).toBeVisible({ timeout: 15000 });

      console.log('✓ Template de confirmation gratuite affiché / Free confirmation template shown');

      // Vérifier qu'on n'a PAS été redirigé vers Stripe
      // / Verify we were NOT redirected to Stripe
      expect(page.url()).not.toContain('stripe.com');
      console.log('✓ Pas de redirection Stripe / No Stripe redirect');
    });

    // ─── ÉTAPE 5 : Vérifier en base de données ───────────────────────────────
    // / STEP 5: Verify in database
    await test.step('Verify in DB / Vérifier en base', async () => {
      const dbResult = await verifyDbData({
        type: 'membership',
        email: userEmailZero,
        product: productName,
      });

      expect(dbResult, 'Adhésion introuvable en DB').not.toBeNull();
      expect(dbResult?.status).toBe('success');

      // Status 'A' = ONCE = adhésion confirmée sans paiement (Membership.ONCE = 'A', PaymentMethod.FREE)
      // / Status 'A' = ONCE = membership confirmed without payment (Membership.ONCE = 'A', PaymentMethod.FREE)
      expect(dbResult?.membership_status).toBe('A');
      console.log(`✓ DB OK — status: ${dbResult?.membership_status}`);
    });

    // ─── ÉTAPE 6 : Se connecter et vérifier la page "mon compte" ─────────────
    // / STEP 6: Login and verify the "my account" page
    await test.step('Login and check account page / Connexion et vérification compte', async () => {
      // Le TEST MODE permet la connexion sans valider l'email
      // / TEST MODE allows login without email validation
      await loginAs(page, userEmailZero);

      // La page des adhésions du compte est /my_account/membership/ (action DRF)
      // / The account memberships page is /my_account/membership/ (DRF action)
      await page.goto('/my_account/membership/');
      await page.waitForLoadState('domcontentloaded');

      // L'adhésion doit apparaître dans la liste (h3.card-title dans membership_card.html)
      // / The membership must appear in the list (h3.card-title in membership_card.html)
      await expect(
        page.locator(`h3.card-title:has-text("${productName}")`)
          .or(page.locator(`text=${productName}`))
      ).toBeVisible({ timeout: 10000 });

      console.log('✓ Adhésion visible dans le compte / Membership visible in account');
    });

    // ─── ÉTAPE 7 : Vérifier dans l'admin Ventes (LigneArticle) ───────────────
    // / STEP 7: Verify in admin Sales (LigneArticle)
    await test.step('Admin: verify sale line at 0€ / Admin : vérifier la ligne de vente à 0€', async () => {
      // Vider les cookies pour sortir de la session utilisateur avant de se connecter en admin
      // Nécessaire car loginAs ne gère pas le cas "déjà connecté"
      // / Clear cookies to exit the user session before logging in as admin
      // / Necessary because loginAs doesn't handle the "already logged in" case
      await page.context().clearCookies();

      await loginAsAdmin(page);

      // L'URL de recherche admin : /admin/BaseBillet/lignearticle/?q=<email>
      // search_fields inclut membership__user__email pour les adhésions sans Stripe
      // / Admin search URL: /admin/BaseBillet/lignearticle/?q=<email>
      // / search_fields includes membership__user__email for memberships without Stripe
      await page.goto(`/admin/BaseBillet/lignearticle/?q=${encodeURIComponent(userEmailZero)}`);
      await page.waitForLoadState('domcontentloaded');

      // La ligne de vente doit apparaître dans le tableau admin
      // / The sale line must appear in the admin table
      await expect(page.locator(`text=${userEmailZero}`)).toBeVisible({ timeout: 10000 });

      const adminTableRows = page.locator('table#result_list tbody tr');
      expect(await adminTableRows.count()).toBeGreaterThan(0);

      // Cibler la colonne "Valeur" via sa classe CSS field-amount_decimal
      // dround(0) retourne 0 (int falsy) → affiche "0"
      // / Target the "Value" column via its CSS class field-amount_decimal
      // / dround(0) returns 0 (falsy int) → shows "0"
      const firstRow = adminTableRows.first();
      await expect(firstRow.locator('td.field-amount_decimal')).toHaveText('0');

      console.log('✓ Admin Ventes : ligne 0€ présente / Admin Sales: 0€ line found');
    });
  });

  /**
   * TEST 2 : Adhésion à 1€ sur le même produit → Stripe
   * / TEST 2: Membership at 1€ on the same product → Stripe
   *
   * Flux attendu / Expected flow :
   * 1. Formulaire rempli avec 1€
   * 2. Soumission → redirection vers checkout.stripe.com
   * 3. Stripe affiche 1€
   * 4. Paiement complété avec carte de test
   * 5. Vérification en base
   */
  test('1€ : Stripe payment on the same product / 1€ : paiement Stripe sur le même produit', async ({ page }) => {
    test.setTimeout(120000);

    // ─── ÉTAPE 1 : Aller sur la page des adhésions ───────────────────────────
    // / STEP 1: Navigate to the memberships page
    await test.step('Navigate to memberships / Naviguer vers les adhésions', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('domcontentloaded');
    });

    // ─── ÉTAPE 2 : Ouvrir le panneau d'adhésion ──────────────────────────────
    // / STEP 2: Open the subscription panel
    await test.step('Open subscription panel / Ouvrir le panneau adhésion', async () => {
      const productCard = page.locator(`.card:has-text("${productName}")`).first();
      await productCard.locator('button:has-text("Subscribe"), button:has-text("Adhérer")').click();
      await page.waitForSelector('#subscribePanel.show', { state: 'visible' });
      console.log('✓ Panneau adhésion ouvert / Subscription panel opened');
    });

    // ─── ÉTAPE 3 : Remplir le formulaire avec 1€ ─────────────────────────────
    // / STEP 3: Fill the form with 1€
    await test.step('Fill form with 1€ / Remplir le formulaire avec 1€', async () => {
      await page.locator('#subscribePanel input[name="email"]').fill(userEmailStripe);
      await page.locator('#subscribePanel input[name="confirm-email"]').fill(userEmailStripe);
      await page.locator('#subscribePanel input[name="firstname"]').fill('One');
      await page.locator('#subscribePanel input[name="lastname"]').fill('Euro');

      const priceLabelPrixLibre = page.locator('#subscribePanel label:has-text("Prix Libre")').first();
      if (await priceLabelPrixLibre.isVisible()) {
        await priceLabelPrixLibre.click();
      }

      // 1€ → doit déclencher la session Stripe
      // / 1€ → must trigger a Stripe session
      const freePriceInput = page.locator('#subscribePanel input[type="number"]').first();
      await freePriceInput.fill('1');
      console.log('✓ Formulaire rempli avec 1€ / Form filled with 1€');
    });

    // ─── ÉTAPE 4 : Soumettre et vérifier la redirection Stripe ───────────────
    // / STEP 4: Submit and verify Stripe redirect
    await test.step('Submit and check Stripe redirect / Soumettre et vérifier la redirection Stripe', async () => {
      await page.locator('#membership-submit').click();

      // Attendre la redirection vers checkout.stripe.com
      // / Wait for redirect to checkout.stripe.com
      await page.waitForURL(/checkout\.stripe\.com/, { timeout: 40000 });
      console.log('✓ Redirigé vers Stripe / Redirected to Stripe');

      // Vérifier que Stripe affiche 1,00 €
      // / Verify Stripe shows 1.00€
      await page.waitForSelector('text=/Card information|Informations de carte/i', { timeout: 20000 });
      const stripePageText = await page.locator('body').innerText();
      expect(stripePageText).toMatch(/1[.,]00/);
      console.log('✓ Stripe affiche 1€ / Stripe shows 1€');
    });

    // ─── ÉTAPE 5 : Compléter le paiement Stripe ──────────────────────────────
    // / STEP 5: Complete the Stripe payment
    await test.step('Complete Stripe payment / Compléter le paiement Stripe', async () => {
      await fillStripeCard(page, userEmailStripe);

      const stripeSubmitButton = page.locator('button[type="submit"]').first();
      await expect(stripeSubmitButton).toBeEnabled({ timeout: 20000 });
      await stripeSubmitButton.click();

      // Attendre le retour sur lespass.tibillet.localhost
      // / Wait for return to lespass.tibillet.localhost
      await page.waitForURL(
        url => url.hostname.includes('tibillet.localhost') || url.hostname.includes('lespass.tibillet.localhost'),
        { timeout: 60000 }
      );
      console.log('✓ Paiement Stripe complété / Stripe payment completed');
    });

    // ─── ÉTAPE 6 : Vérifier en base de données ───────────────────────────────
    // / STEP 6: Verify in database
    await test.step('Verify in DB / Vérifier en base', async () => {
      const dbResult = await verifyDbData({
        type: 'membership',
        email: userEmailStripe,
        product: productName,
      });

      expect(dbResult, 'Adhésion introuvable en DB').not.toBeNull();
      expect(dbResult?.status).toBe('success');
      expect(dbResult?.membership_status).toBeTruthy();
      console.log(`✓ DB OK — status: ${dbResult?.membership_status}`);
    });

    // ─── ÉTAPE 7 : Vérifier dans l'admin Ventes (LigneArticle) ───────────────
    // / STEP 7: Verify in admin Sales (LigneArticle)
    await test.step('Admin: verify sale line at 1€ / Admin : vérifier la ligne de vente à 1€', async () => {
      // Vider les cookies pour sortir de la session utilisateur avant de se connecter en admin
      // / Clear cookies to exit the user session before logging in as admin
      await page.context().clearCookies();

      await loginAsAdmin(page);

      // Recherche dans /admin/BaseBillet/lignearticle/ par email
      // search_fields inclut paiement_stripe__user__email pour les paiements Stripe
      // / Search in /admin/BaseBillet/lignearticle/ by email
      // / search_fields includes paiement_stripe__user__email for Stripe payments
      await page.goto(`/admin/BaseBillet/lignearticle/?q=${encodeURIComponent(userEmailStripe)}`);
      await page.waitForLoadState('domcontentloaded');

      // La ligne de vente Stripe doit apparaître
      // / The Stripe sale line must appear
      await expect(page.locator(`text=${userEmailStripe}`)).toBeVisible({ timeout: 10000 });

      const adminTableRows = page.locator('table#result_list tbody tr');
      expect(await adminTableRows.count()).toBeGreaterThan(0);

      // Cibler la colonne "Valeur" via sa classe CSS field-amount_decimal
      // dround(100 centimes) = Decimal('1.00') → affiche "1.00"
      // / Target the "Value" column via its CSS class field-amount_decimal
      // / dround(100 cents) = Decimal('1.00') → shows "1.00"
      const firstRow = adminTableRows.first();
      await expect(firstRow.locator('td.field-amount_decimal')).toHaveText('1.00');

      console.log('✓ Admin Ventes : ligne 1.00€ présente / Admin Sales: 1.00€ line found');
    });
  });

});
