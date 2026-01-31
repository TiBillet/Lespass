import { test, expect } from '@playwright/test';
import { env } from './utils/env';
import { loginAsAdmin } from './utils/auth';

/**
 * TEST: Crowds participation popup
 * TEST : Popup participation crowds
 *
 * Objective / Objectif:
 * - Open the participation popup and validate the pro-bono + covenant flow.
 * - Ouvrir le popup de participation et valider le flow pro-bono + règles.
 */
test.describe('Crowds participation popup / Popup participation crowds', () => {
  test('should validate pro-bono toggle and covenant requirement / doit valider pro-bono et les règles', async ({ page }) => {
    
    // Step 1: Login / Étape 1 : Connexion
    await test.step('Login as admin / Connexion admin', async () => {
      await loginAsAdmin(page);
    });

    // Step 2: Go to the crowds list / Étape 2 : Aller sur la liste crowds
    await test.step('Navigate to crowds / Naviguer vers les crowds', async () => {
      await page.goto('/crowd/');
      await page.waitForLoadState('networkidle');
      console.log('✓ On crowds list / Sur la liste des crowds');
    });

    // Step 3: Open the first details page / Étape 3 : Ouvrir le premier détail
    await test.step('Open initiative details / Ouvrir les détails de l\'initiative', async () => {
      // Find the first "Détails" or "Details" link
      const detailsLink = page.locator('a:has-text("Détails"), a:has-text("Details")').first();
      await expect(detailsLink).toBeVisible();
      await detailsLink.click();
      await page.waitForLoadState('networkidle');
      await expect(page).toHaveURL(/\/crowd\//);
    });

    // Step 4: Open the participation popup / Étape 4 : Ouvrir le popup de participation
    await test.step('Open participation popup / Ouvrir le popup de participation', async () => {
      const participateButton = page.locator('button:has-text("Participer"), button:has-text("Participate")').first();
      await expect(participateButton).toBeVisible();
      await participateButton.click();
      
      const popup = page.locator('.swal2-popup');
      await expect(popup).toBeVisible();
    });

    // Step 5: Validate popup basics / Étape 5 : Valider les éléments du popup
    await test.step('Validate popup elements / Valider les éléments du popup', async () => {
      const popup = page.locator('.swal2-popup');
      
      // Use a more flexible selector for the link (can be translated or slightly different)
      // On utilise un sélecteur plus souple pour le lien (peut être traduit)
      const covenantLink = popup.locator('a[href*="movilab.org"], a:has-text("Règles"), a:has-text("Covenant")');
      await expect(covenantLink).toBeVisible();
      await expect(covenantLink).toHaveAttribute('target', '_blank');

      const proBonoToggle = popup.locator('#part-pro-bono');
      const amountWrap = popup.locator('#part-amt-wrap');
      
      // Initially Pro-bono is checked and amount is hidden
      await expect(proBonoToggle).toBeChecked();
      await expect(amountWrap).toBeHidden();
      
      console.log('✓ Popup basics validated / Éléments de base du popup validés');
    });

    // Step 6: Toggle pro-bono to reveal amount / Étape 6 : Désactiver pro-bono pour montrer le montant
    await test.step('Toggle pro-bono / Basculer le pro-bono', async () => {
      const popup = page.locator('.swal2-popup');
      const proBonoToggle = popup.locator('#part-pro-bono');
      const amountWrap = popup.locator('#part-amt-wrap');

      await proBonoToggle.click();
      await expect(proBonoToggle).not.toBeChecked();
      await expect(amountWrap).toBeVisible();
      console.log('✓ Pro-bono toggled / Pro-bono basculé');
    });

    // Step 7: Submit without accepting covenant / Étape 7 : Envoyer sans accepter les règles
    await test.step('Submit without covenant / Envoyer sans les règles', async () => {
      const popup = page.locator('.swal2-popup');
      await popup.locator('#part-desc').fill('Test participation E2E');
      
      const submit = popup.locator('.swal2-confirm');
      await submit.click();

      // Should show validation message
      const validationMsg = popup.locator('.swal2-validation-message');
      await expect(validationMsg).toBeVisible();
      console.log('✓ Validation message shown / Message de validation affiché');
    });

    // Step 8: Accept covenant and submit / Étape 8 : Accepter les règles et envoyer
    await test.step('Accept covenant and submit / Accepter les règles et envoyer', async () => {
      const popup = page.locator('.swal2-popup');
      await popup.locator('#part-covenant').check();
      await popup.locator('#part-amt').fill('10');
      
      const submit = popup.locator('.swal2-confirm');
      await submit.click();
      
      await expect(popup).toBeHidden();
      console.log('✓ Participation submitted / Participation envoyée');
    });

    // Step 9: Verify label in table / Étape 9 : Vérifier l'affichage
    await test.step('Verify participation in list / Vérifier la participation dans la liste', async () => {
      const participationList = page.locator('#participations_list');
      // The label should contain "Pro-bono" or whatever is configured
      await expect(participationList).toContainText(/Pro-bono|Test participation E2E/i);
    });

    // Step 10: Mark completed / Étape 10 : Marquer terminé
    await test.step('Mark as completed / Marquer comme terminé', async () => {
      const markButton = page.locator('button:has-text("Marquer terminé"), button:has-text("Mark completed")').first();
      await expect(markButton).toBeVisible();
      await markButton.click();

      const completionPopup = page.locator('.swal2-popup');
      await expect(completionPopup).toBeVisible();
      await expect(completionPopup.locator('#part-time-unit')).toBeVisible();

      await completionPopup.locator('#part-time-value').fill('1');
      await completionPopup.locator('#part-time-unit').selectOption('days');
      await completionPopup.locator('.swal2-confirm').click();
      
      await expect(completionPopup).toBeHidden();
    });

    // Step 11: Verify duration / Étape 11 : Vérifier la durée
    await test.step('Verify duration / Vérifier la durée', async () => {
      const participationList = page.locator('#participations_list');
      await expect(participationList).toContainText(/1 j|1 d/i);
      console.log('✓ Duration verified / Durée vérifiée');
    });
  });
});
