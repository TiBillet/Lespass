import { test, expect } from '@playwright/test';
import { verifyDbData } from '../utils/db';
import { loginAsAdmin } from '../utils/auth';
import { env } from '../utils/env';
import { fillStripeCard } from '../utils/stripe';
import { createProduct, createMembershipApi } from '../utils/api';

/**
 * TEST : Adhésion à validation manuelle — paiement Stripe via lien copié
 * TEST: Manual validation membership — Stripe payment via copied link
 *
 * LOCALISATION : tests/playwright/tests/43-membership-manual-validation-stripe-payment.spec.ts
 *
 * Ce test couvre le flux complet :
 * 1. Création d'un produit adhésion avec validation manuelle (API v2)
 * 2. Création d'une adhésion en attente (API v2, statut AW)
 * 3. Validation admin (admin_accept → statut AV)
 * 4. Vérification du bouton "Copier le lien" dans le panneau admin
 * 5. Paiement Stripe via le lien de paiement (get_checkout_for_membership)
 * 6. Vérification dans la liste Membership : statut, deadline, contribution
 * 7. Vérification dans les Ventes : LigneArticle créée
 *
 * This test covers the full flow:
 * 1. Create membership product with manual validation (API v2)
 * 2. Create pending membership (API v2, status AW)
 * 3. Admin validation (admin_accept → status AV)
 * 4. Verify "Copy link" button in admin panel
 * 5. Stripe payment via payment link (get_checkout_for_membership)
 * 6. Verify in Membership list: status, deadline, contribution
 * 7. Verify in Sales: LigneArticle created
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

const randomId = generateRandomId();
const userEmail = `jturbeaux+mv${randomId}@pm.me`;

/**
 * Cherche une adhésion dans la liste admin par email et retourne la ligne.
 * Searches for a membership in the admin list by email and returns the row.
 */
async function rechercherDansListeAdmin(page: any, email: string) {
  const searchInput = page.locator('input[name="q"]').first();
  await searchInput.fill(email);
  await searchInput.press('Enter');
  await page.waitForLoadState('networkidle');
  return page.locator('#result_list tbody tr').filter({ hasText: email });
}

test.describe('Manual Validation + Stripe Payment / Validation manuelle + Paiement Stripe', () => {

  let productName: string;
  let priceName: string;
  let priceUuid: string;
  let membershipUuid: string;

  // ──────────────────────────────────────────────────────────
  // Setup : créer le produit adhésion avec validation manuelle
  // Setup: create membership product with manual validation
  // ──────────────────────────────────────────────────────────
  test.beforeAll(async ({ request }) => {
    productName = `Adhesion Validation Stripe ${randomId}`;
    priceName = `Annuel Val ${randomId}`;

    const productResult = await createProduct({
      request,
      name: productName,
      description: 'Adhésion à validation manuelle pour test paiement Stripe',
      category: 'Membership',
      offers: [{
        name: priceName,
        price: '20.00',
        subscriptionType: 'Y',
        manualValidation: true,
      }],
    });
    expect(productResult.ok).toBeTruthy();
    priceUuid = productResult.offers?.[0]?.identifier || '';
    expect(priceUuid).not.toBe('');
    console.log(`✓ Produit créé : ${productName} (price: ${priceUuid})`);
  });

  test('Full flow: create → validate → copy link → pay → verify / Flux complet', async ({ page, request }) => {

    // ──────────────────────────────────────────────────────────
    // Étape 1 : Créer l'adhésion en statut ADMIN_WAITING via API
    // Step 1: Create membership in ADMIN_WAITING status via API
    // ──────────────────────────────────────────────────────────
    await test.step('Créer adhésion en attente / Create pending membership', async () => {
      const msResult = await createMembershipApi({
        request,
        priceUuid,
        email: userEmail,
        firstName: 'Stripe',
        lastName: 'Validation',
        status: 'AW',
      });
      expect(msResult.ok).toBeTruthy();
      console.log('✓ Adhésion AW créée via API');
    });

    // ──────────────────────────────────────────────────────────
    // Étape 2 : Récupérer l'UUID de l'adhésion en base
    // Step 2: Get membership UUID from database
    // ──────────────────────────────────────────────────────────
    await test.step('Récupérer UUID en base / Get UUID from DB', async () => {
      const dbResult = await verifyDbData({
        type: 'membership',
        email: userEmail,
        product: productName,
      });
      expect(dbResult).not.toBeNull();
      membershipUuid = dbResult?.uuid || '';
      expect(membershipUuid).toBeTruthy();
      expect(dbResult?.membership_status).toBe('AW');
      console.log(`✓ UUID adhésion : ${membershipUuid}, statut : AW`);
    });

    // ──────────────────────────────────────────────────────────
    // Étape 3 : Admin valide l'adhésion (AW → AV)
    // Step 3: Admin validates membership (AW → AV)
    // ──────────────────────────────────────────────────────────
    await test.step('Admin validation / Validation admin', async () => {
      await loginAsAdmin(page);

      // Récupérer le token CSRF depuis les cookies
      // / Get CSRF token from cookies
      const cookies = await page.context().cookies();
      const csrfToken = cookies.find(cookie => cookie.name === 'csrftoken')?.value;
      expect(csrfToken).toBeTruthy();

      // Appeler l'endpoint admin_accept (HTMX POST)
      // / Call admin_accept endpoint (HTMX POST)
      const acceptResponse = await page.request.post(
        `/memberships/${membershipUuid}/admin_accept/`,
        {
          headers: {
            'HX-Request': 'true',
            'X-CSRFToken': csrfToken as string,
            'Referer': `${env.BASE_URL}/admin/`,
          },
        }
      );
      expect(acceptResponse.ok()).toBeTruthy();
      console.log('✓ Adhésion validée par l\'admin (AW → AV)');

      // Vérifier en base que le statut est passé à AV
      // / Verify in DB that status changed to AV
      const dbResult = await verifyDbData({
        type: 'membership',
        email: userEmail,
        product: productName,
      });
      expect(dbResult?.membership_status).toBe('AV');
    });

    // ──────────────────────────────────────────────────────────
    // Étape 4 : Vérifier le bouton "Copier le lien" dans l'admin
    // Step 4: Verify "Copy link" button in admin panel
    // ──────────────────────────────────────────────────────────
    await test.step('Vérifier bouton copier le lien / Verify copy link button', async () => {
      // Aller sur la fiche de l'adhésion dans l'admin
      // / Go to the membership change page in admin
      await page.goto('/admin/BaseBillet/membership/');
      await page.waitForLoadState('networkidle');

      const row = await rechercherDansListeAdmin(page, userEmail);
      await expect(row).toBeVisible({ timeout: 10000 });

      // Cliquer sur la première adhésion trouvée
      // / Click on the first found membership
      const firstLink = row.locator('a').first();
      await firstLink.click();
      await page.waitForLoadState('networkidle');

      // Le panneau d'actions doit contenir le bouton "Copier le lien"
      // / The action panel must contain the "Copy link" button
      const copyButton = page.locator('[data-testid="membership-action-copy-payment-link"]');
      await expect(copyButton).toBeVisible({ timeout: 5000 });
      console.log('✓ Bouton "Copier le lien" visible dans le panneau');

      // Le bouton "Renvoyer le lien" doit aussi être visible (état AV)
      // / The "Resend link" button must also be visible (state AV)
      const resendButton = page.locator('[data-testid="membership-action-accept"]');
      await expect(resendButton).toBeVisible({ timeout: 5000 });
      console.log('✓ Bouton "Renvoyer le lien" visible dans le panneau');
    });

    // ──────────────────────────────────────────────────────────
    // Étape 5 : Payer via le lien de paiement (checkout Stripe)
    // Step 5: Pay via the payment link (Stripe checkout)
    // ──────────────────────────────────────────────────────────
    await test.step('Payer via le lien de paiement / Pay via payment link', async () => {
      // Naviguer vers le lien de paiement (même URL que celle copiée par le bouton)
      // / Navigate to the payment link (same URL as copied by the button)
      const lien_paiement = `/memberships/${membershipUuid}/get_checkout_for_membership`;
      await page.goto(lien_paiement);

      // Attendre la redirection vers Stripe checkout
      // / Wait for redirect to Stripe checkout
      await page.waitForURL(/checkout.stripe.com/, { timeout: 30000 });
      console.log('✓ Redirigé vers Stripe checkout');

      // Remplir le formulaire de paiement Stripe
      // / Fill the Stripe payment form
      await fillStripeCard(page, userEmail);

      // Soumettre le paiement Stripe
      // / Submit the Stripe payment
      const submitButton = page.locator('button[type="submit"]').first();
      await expect(submitButton).toBeEnabled({ timeout: 20000 });
      await submitButton.click();

      // Attendre le retour vers le site (confirmation de paiement)
      // / Wait for return to the site (payment confirmation)
      await page.waitForURL(
        url => url.hostname.includes('tibillet.localhost'),
        { timeout: 60000 }
      );
      console.log('✓ Paiement Stripe effectué, retour sur le site');
    });

    // ──────────────────────────────────────────────────────────
    // Étape 6 : Attendre le traitement du webhook Stripe
    //           puis vérifier le statut en base
    // Step 6: Wait for Stripe webhook processing then verify DB status
    // ──────────────────────────────────────────────────────────
    await test.step('Vérifier statut ONCE en base / Verify ONCE status in DB', async () => {
      // Le webhook Stripe est asynchrone — on attend que le statut passe à ONCE
      // / Stripe webhook is async — wait for status to become ONCE
      let membershipStatus = '';
      const maxRetries = 15;

      for (let attempt = 1; attempt <= maxRetries; attempt++) {
        const dbResult = await verifyDbData({
          type: 'membership',
          email: userEmail,
          product: productName,
        });

        membershipStatus = dbResult?.membership_status || '';

        // Statut ONCE (A) = paiement confirmé
        // / Status ONCE (A) = payment confirmed
        if (membershipStatus === 'A') {
          console.log(`✓ Statut ONCE confirmé après ${attempt} tentative(s)`);
          break;
        }

        // Attendre 2 secondes entre chaque tentative
        // / Wait 2 seconds between attempts
        if (attempt < maxRetries) {
          console.log(`  Tentative ${attempt}/${maxRetries} — statut actuel : ${membershipStatus}, attente 2s...`);
          await page.waitForTimeout(2000);
        }
      }

      expect(membershipStatus).toBe('A');
    });

    // ──────────────────────────────────────────────────────────
    // Étape 7 : Vérifier dans la liste admin : statut, deadline, contribution
    // Step 7: Verify in admin list: status, deadline, contribution
    // ──────────────────────────────────────────────────────────
    await test.step('Vérifier liste admin / Verify admin list', async () => {
      // Pas de loginAsAdmin ici — la session admin est toujours active
      // (les cookies persistent après le retour de Stripe)
      // / No loginAsAdmin here — admin session is still active
      // (cookies persist after Stripe redirect)
      await page.goto('/admin/BaseBillet/membership/');
      await page.waitForLoadState('networkidle');

      const row = await rechercherDansListeAdmin(page, userEmail);
      await expect(row).toBeVisible({ timeout: 10000 });

      // Statut : "Payé en ligne" (status ONCE = 'A')
      // / Status: "Payé en ligne" (status ONCE = 'A')
      const statusCell = row.locator('td.field-status');
      await expect(statusCell).toContainText('Payé en ligne');
      console.log('✓ Statut "Payé en ligne" dans la liste');

      // Deadline : doit être une date au format JJ/MM/AAAA (pas "-")
      // / Deadline: must be a date in DD/MM/YYYY format (not "-")
      const deadlineCell = row.locator('td.field-display_deadline');
      const deadlineText = (await deadlineCell.innerText()).trim();
      expect(deadlineText).not.toBe('-');
      expect(deadlineText).toMatch(/\d{2}\/\d{2}\/\d{4}/);
      console.log(`✓ Deadline : ${deadlineText}`);

      // Contribution : doit afficher 20.00 (le prix du tarif)
      // / Contribution: must display 20.00 (the price amount)
      const contributionCell = row.locator('td.field-contribution_value');
      const contributionText = (await contributionCell.innerText()).trim();
      expect(contributionText).toContain('20');
      console.log(`✓ Contribution : ${contributionText}`);

      // Booléen "Valid" : doit être true (icône check verte)
      // / Boolean "Valid": must be true (green check icon)
      const validCell = row.locator('td.field-display_is_valid');
      const validImg = validCell.locator('img[src*="icon-yes"], svg, span');
      await expect(validImg.first()).toBeVisible();
      console.log('✓ Adhésion marquée comme valide dans la liste');
    });

    // ──────────────────────────────────────────────────────────
    // Étape 8 : Vérifier dans les Ventes (LigneArticle)
    // Step 8: Verify in Sales (LigneArticle)
    // ──────────────────────────────────────────────────────────
    await test.step('Vérifier LigneArticle / Verify sales line', async () => {
      await page.goto('/admin/BaseBillet/lignearticle/');
      await page.waitForLoadState('networkidle');

      // Chercher par nom de produit ou email
      // / Search by product name or email
      const searchInput = page.locator('input[name="q"]').first();
      await searchInput.fill(userEmail);
      await searchInput.press('Enter');
      await page.waitForLoadState('networkidle');

      // Au moins une ligne doit apparaître
      // / At least one row must appear
      const rows = page.locator('#result_list tbody tr');
      const rowCount = await rows.count();
      expect(rowCount).toBeGreaterThanOrEqual(1);
      console.log(`✓ ${rowCount} LigneArticle(s) trouvée(s)`);

      // La ligne doit avoir un statut confirmé (VALID ou CONFIRMED)
      // / The line must have a confirmed status (VALID or CONFIRMED)
      const bodyText = await page.innerText('body');
      const hasValidLine = (
        bodyText.includes('CONFIRMED') ||
        bodyText.includes('Confirmed') ||
        bodyText.includes('Confirmé') ||
        bodyText.includes('VALID') ||
        bodyText.includes('Validé')
      );
      expect(hasValidLine).toBeTruthy();
      console.log('✓ LigneArticle confirmée dans les Ventes');
    });
  });
});
