import { test, expect } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';
import { env } from './utils/env';
import { fillStripeCard } from './utils/stripe';

/**
 * TEST : Contribution Crowds avec paiement Stripe (direct_debit)
 * TEST: Crowds contribution with Stripe payment (direct_debit)
 *
 * LOCALISATION : tests/playwright/tests/44-crowds-contribution-stripe.spec.ts
 *
 * Ce test couvre le flux complet :
 * 1. Admin active direct_debit sur une initiative existante
 * 2. Contribution financiere → redirection Stripe
 * 3. Paiement Stripe → retour sur le site
 * 4. Verification contribution PAID dans la page initiative
 * 5. Verification LigneArticle dans l'admin Ventes
 * 6. Verification financement dans la section Crowds
 *
 * This test covers the full flow:
 * 1. Admin enables direct_debit on an existing initiative
 * 2. Financial contribution → Stripe redirect
 * 3. Stripe payment → return to site
 * 4. Verify contribution PAID on the initiative page
 * 5. Verify LigneArticle in admin Sales
 * 6. Verify funding in the Crowds section
 */

const contributionAmount = '15';
const contributorName = `E2E Stripe ${Date.now().toString(36)}`;

test.describe('Crowds contribution Stripe / Contribution Crowds Stripe', () => {
  let initiativeUuid: string;
  let initiativeName: string;

  test('Anonymous user sees login prompt / Utilisateur anonyme voit la demande de connexion', async ({ page }) => {

    // FR: Un utilisateur non connecté qui clique sur "Financer" doit voir un popup
    //     l'invitant à se connecter — pas le formulaire de contribution.
    // EN: An anonymous user clicking "Financer" must see a login prompt popup
    //     — not the contribution form.
    await test.step('Naviguer vers une initiative / Navigate to an initiative', async () => {
      await page.goto('/crowd/');
      await page.waitForLoadState('networkidle');

      // Cliquer sur la premiere initiative
      // / Click on the first initiative
      const detailsLink = page.locator('a:has-text("Détails"), a:has-text("Details")').first();
      await expect(detailsLink).toBeVisible();
      await detailsLink.click();
      await page.waitForLoadState('networkidle');
    });

    await test.step('Cliquer sur Financer → popup connexion / Click Fund → login popup', async () => {
      // Cliquer sur le bouton "Financer" (sans être connecté)
      // / Click the "Financer" button (without being logged in)
      const fundButton = page.locator('button:has-text("Financer"), button:has-text("Fund")').first();
      await expect(fundButton).toBeVisible();
      await fundButton.click();

      // Le popup SweetAlert doit demander la connexion, pas le formulaire de contribution
      // / SweetAlert popup must ask for login, not the contribution form
      const popup = page.locator('.swal2-popup');
      await expect(popup).toBeVisible({ timeout: 5000 });

      // Verifier que le popup contient "Connexion" ou "Se connecter" (pas "Montant")
      // / Verify popup contains "Connexion" or "Log in" (not "Montant" / "Amount")
      const popupText = await popup.innerText();
      const est_popup_connexion = (
        popupText.includes('Connexion') ||
        popupText.includes('connecter') ||
        popupText.includes('Log in') ||
        popupText.includes('login')
      );
      expect(est_popup_connexion).toBeTruthy();

      // Le champ montant (#contrib-amt) ne doit PAS etre present
      // / The amount field (#contrib-amt) must NOT be present
      const champMontant = popup.locator('#contrib-amt');
      await expect(champMontant).toHaveCount(0);

      console.log('✓ Utilisateur anonyme voit le popup de connexion (pas le formulaire)');

      // Fermer le popup
      // / Close the popup
      const cancelButton = popup.locator('.swal2-cancel, button:has-text("Annuler"), button:has-text("Cancel")').first();
      if (await cancelButton.isVisible()) {
        await cancelButton.click();
      }
    });
  });

  test('Full flow: direct_debit → Stripe → verify / Flux complet', async ({ page }) => {

    // ──────────────────────────────────────────────────────────
    // Etape 1 : Login admin et activer direct_debit sur une initiative
    // Step 1: Admin login and enable direct_debit on an initiative
    // ──────────────────────────────────────────────────────────
    await test.step('Login admin + activer direct_debit / Enable direct_debit', async () => {
      await loginAsAdmin(page);

      // Aller sur la liste des initiatives dans l'admin
      // / Go to the initiatives list in admin
      await page.goto('/admin/crowds/initiative/');
      await page.waitForLoadState('networkidle');

      // Cliquer sur la premiere initiative disponible
      // / Click on the first available initiative
      const firstRow = page.locator('#result_list tbody tr').first();
      await expect(firstRow).toBeVisible({ timeout: 10000 });

      // Recuperer le nom de l'initiative pour verifications ulterieures
      // / Get the initiative name for later verifications
      const nameLink = firstRow.locator('th a, td a').first();
      initiativeName = (await nameLink.innerText()).trim();
      await nameLink.click();
      await page.waitForLoadState('networkidle');

      // Recuperer l'UUID depuis l'URL (format /admin/crowds/initiative/<uuid>/change/)
      // / Get the UUID from the URL
      const url = page.url();
      const uuidMatch = url.match(/initiative\/([^/]+)\/change/);
      expect(uuidMatch).not.toBeNull();
      initiativeUuid = uuidMatch![1];
      console.log(`✓ Initiative : ${initiativeName} (${initiativeUuid})`);

      // Cocher direct_debit si pas deja coche
      // / Check direct_debit if not already checked
      const directDebitCheckbox = page.locator('input[name="direct_debit"]');
      await expect(directDebitCheckbox).toBeVisible({ timeout: 5000 });

      if (!(await directDebitCheckbox.isChecked())) {
        await directDebitCheckbox.check();
      }

      // Sauvegarder
      // / Save
      const saveButton = page.locator('input[type="submit"][name="_save"], button[type="submit"][name="_save"]').first();
      await saveButton.click();
      await page.waitForLoadState('networkidle');
      console.log('✓ direct_debit active sur l\'initiative');
    });

    // ──────────────────────────────────────────────────────────
    // Etape 2 : Ouvrir l'initiative et contribuer (Stripe)
    // Step 2: Open initiative and contribute (Stripe)
    // ──────────────────────────────────────────────────────────
    await test.step('Contribuer via le formulaire / Contribute via form', async () => {
      // Aller sur la page detail de l'initiative
      // / Go to the initiative detail page
      await page.goto(`/crowd/${initiativeUuid}/`);
      await page.waitForLoadState('networkidle');
      await expect(page.locator('h1')).toContainText(initiativeName);
      console.log('✓ Page detail de l\'initiative chargee');

      // Cliquer sur le bouton "Financer"
      // / Click the "Financer" button
      const fundButton = page.locator('button:has-text("Financer"), button:has-text("Fund")').first();
      await expect(fundButton).toBeVisible();
      await fundButton.click();

      // Remplir le popup SweetAlert2
      // / Fill the SweetAlert2 popup
      const popup = page.locator('.swal2-popup');
      await expect(popup).toBeVisible({ timeout: 5000 });

      await popup.locator('#contrib-name').fill(contributorName);
      await popup.locator('#contrib-desc').fill('Test E2E contribution Stripe');
      await popup.locator('#contrib-amt').fill(contributionAmount);

      // Valider la contribution
      // / Submit the contribution
      const confirmButton = popup.locator('.swal2-confirm');
      await confirmButton.click();

      // Attendre la redirection vers Stripe (le listener htmx:afterOnLoad redirige)
      // / Wait for Stripe redirect (htmx:afterOnLoad listener redirects)
      await page.waitForURL(/checkout\.stripe\.com/, { timeout: 30000 });
      console.log('✓ Redirige vers Stripe checkout');
    });

    // ──────────────────────────────────────────────────────────
    // Etape 3 : Payer sur Stripe et revenir
    // Step 3: Pay on Stripe and return
    // ──────────────────────────────────────────────────────────
    await test.step('Paiement Stripe / Stripe payment', async () => {
      // Remplir le formulaire de paiement Stripe
      // / Fill the Stripe payment form
      await fillStripeCard(page, env.ADMIN_EMAIL);

      // Soumettre le paiement
      // / Submit the payment
      const submitButton = page.locator('button[type="submit"]').first();
      await expect(submitButton).toBeEnabled({ timeout: 20000 });
      await submitButton.click();

      // Attendre le retour vers le site (contribution_stripe_return → redirect /crowd/<uuid>/)
      // / Wait for return to site (contribution_stripe_return → redirect /crowd/<uuid>/)
      await page.waitForURL(
        url => url.hostname.includes('tibillet.localhost'),
        { timeout: 60000 }
      );
      console.log('✓ Paiement Stripe effectue, retour sur le site');
    });

    // ──────────────────────────────────────────────────────────
    // Etape 4 : Verifier la contribution dans la page initiative
    // Step 4: Verify contribution on the initiative page
    // ──────────────────────────────────────────────────────────
    await test.step('Verifier contribution PAID / Verify contribution PAID', async () => {
      // On est redirige vers /crowd/<uuid>/ — attendre le chargement
      // / We're redirected to /crowd/<uuid>/ — wait for load
      await page.waitForLoadState('networkidle');

      // La section financement doit contenir le nom du contributeur
      // / The funding section must contain the contributor name
      const contributionsList = page.locator('#contributions_list');
      await expect(contributionsList).toContainText(contributorName, { timeout: 10000 });

      // Le montant doit etre affiche
      // / The amount must be displayed
      await expect(contributionsList).toContainText(contributionAmount);

      // Le statut doit etre "Payee" ou "Paid" (pas "En attente")
      // / Status must be "Payee" or "Paid" (not "En attente" / "Pending")
      const contributionRow = contributionsList.locator('tr, .list-group-item').filter({ hasText: contributorName });
      await expect(contributionRow.first()).toBeVisible();
      const rowText = await contributionRow.first().innerText();
      const isPaid = rowText.includes('Payée') || rowText.includes('Paid') || rowText.includes('payée');
      expect(isPaid).toBeTruthy();
      console.log('✓ Contribution affichee comme payee dans la page initiative');
    });

    // ──────────────────────────────────────────────────────────
    // Etape 5 : Verifier la LigneArticle dans l'admin Ventes
    //           Statut attendu : "Confirmed" / "Confirmé" (VALID)
    // Step 5: Verify LigneArticle in admin Sales
    //         Expected status: "Confirmed" / "Confirmé" (VALID)
    // ──────────────────────────────────────────────────────────
    await test.step('Verifier LigneArticle VALID dans admin / Verify VALID sales line in admin', async () => {
      await page.goto('/admin/BaseBillet/lignearticle/');
      await page.waitForLoadState('networkidle');

      // Chercher par "crowdfunding" (le produit technique)
      // / Search for "crowdfunding" (the technical product)
      const searchInput = page.locator('input[name="q"]').first();
      await searchInput.fill('crowdfunding');
      await searchInput.press('Enter');
      await page.waitForLoadState('networkidle');

      // Au moins une ligne doit apparaitre
      // / At least one row must appear
      const rows = page.locator('#result_list tbody tr');
      const rowCount = await rows.count();
      expect(rowCount).toBeGreaterThanOrEqual(1);
      console.log(`✓ ${rowCount} LigneArticle(s) "crowdfunding" trouvee(s)`);

      // Verifier qu'une ligne a le montant attendu (15.00)
      // / Verify a row has the expected amount (15.00)
      const bodyText = await page.locator('#result_list').innerText();
      expect(bodyText).toContain('15');
      console.log('✓ Montant 15 trouve dans les ventes');

      // Verifier le statut VALID ("Confirmed" ou "Confirmé") sur la derniere ligne creee
      //     Le tri est par date decroissante (-datetime), donc la premiere ligne est la plus recente.
      // / Verify VALID status ("Confirmed" or "Confirmé") on the most recent line.
      const firstRow = rows.first();
      // FR: Le statut doit etre "CONFIRMED" (VALID) et PAS "PAID BUT NOT CONFIRMED" (PAID)
      // EN: Status must be "CONFIRMED" (VALID) and NOT "PAID BUT NOT CONFIRMED" (PAID)
      const firstRowText = await firstRow.innerText();
      const statut_est_paid_non_confirme = firstRowText.toUpperCase().includes('NOT CONFIRMED');
      expect(statut_est_paid_non_confirme).toBeFalsy();
      console.log('✓ Statut VALID (Confirmed) dans les ventes');
    });

    // ──────────────────────────────────────────────────────────
    // Etape 6 : Verifier le pourcentage de financement mis a jour
    // Step 6: Verify updated funding percentage
    // ──────────────────────────────────────────────────────────
    await test.step('Verifier financement dans Crowds / Verify funding in Crowds', async () => {
      await page.goto(`/crowd/${initiativeUuid}/`);
      await page.waitForLoadState('networkidle');

      // La section financement doit afficher le montant finance
      // / The funding section must display the funded amount
      const fundingSection = page.locator('#financement');
      await expect(fundingSection).toBeVisible();

      const fundingText = await fundingSection.innerText();
      // Le montant finance doit inclure au moins "15" (notre contribution)
      // / The funded amount must include at least "15" (our contribution)
      expect(fundingText).toContain('15');
      console.log('✓ Montant finance visible dans la section financement');
    });

    // ──────────────────────────────────────────────────────────
    // Etape 7 : Nettoyer — desactiver direct_debit
    // Step 7: Cleanup — disable direct_debit
    // ──────────────────────────────────────────────────────────
    await test.step('Desactiver direct_debit / Disable direct_debit', async () => {
      await page.goto(`/admin/crowds/initiative/${initiativeUuid}/change/`);
      await page.waitForLoadState('networkidle');

      const directDebitCheckbox = page.locator('input[name="direct_debit"]');
      if (await directDebitCheckbox.isChecked()) {
        await directDebitCheckbox.uncheck();
      }

      const saveButton = page.locator('input[type="submit"][name="_save"], button[type="submit"][name="_save"]').first();
      await saveButton.click();
      await page.waitForLoadState('networkidle');
      console.log('✓ direct_debit desactive (cleanup)');
    });
  });
});
