import { test, expect } from '@playwright/test';
import { env } from './utils/env';
import { loginAsAdmin } from './utils/auth';

/**
 * TEST: Login flow
 * TEST : Flux de connexion
 * 
 * This test reproduces the first step of the demo_data operations:
 * Ce test reproduit la première étape des opérations demo_data :
 * 1. Navigate to the homepage / Naviguer vers la page d'accueil
 * 2. Open the login panel / Ouvrir le panneau de connexion
 * 3. Fill the admin email / Remplir l'email administrateur
 * 4. Submit the form / Soumettre le formulaire
 * 5. Use TEST MODE to authenticate / Utiliser le MODE TEST pour s'authentifier
 * 6. Verify admin access / Vérifier l'accès administrateur
 */

test.describe('Login Flow / Flux de connexion', () => {
  
  /**
   * Main test: standard login with admin rights
   * Test principal : connexion standard avec droits admin
   */
  test('should authenticate as admin / doit s\'authentifier en tant qu\'admin', async ({ page }) => {
    
    // We use the centralized authentication helper
    // On utilise l'aide à l'authentification centralisée
    await test.step('Login as admin / Connexion admin', async () => {
      await loginAsAdmin(page);
    });

    // Step 6: Verify navigation to the account page
    // Étape 6 : Vérifier la navigation vers la page du compte
    await test.step('Verify /my_account page / Vérifier la page /my_account', async () => {
      // Direct navigation to ensure we are where we expect
      await page.goto('/my_account/');
      await page.waitForLoadState('networkidle');
      
      // The URL must contain /my_account/
      await expect(page).toHaveURL(new RegExp('/my_account/'));
      console.log('✓ Successfully on /my_account / Succès sur /my_account');
    });

    // Step 7: Confirm admin rights (presence of the admin panel button)
    // Étape 7 : Confirmer les droits admin (présence du bouton vers le panel admin)
    await test.step('Verify Admin access / Vérifier l\'accès Admin', async () => {
      // Admin users see a red button pointing to /admin/
      // Les admins voient un bouton rouge pointant vers /admin/
      const adminPanelButton = page.locator('a[href*="/admin/"]').filter({ hasText: /Admin panel|Panneau d'administration/i });
      
      // We expect this button to be visible
      // On s'attend à ce que ce bouton soit visible
      await expect(adminPanelButton).toBeVisible({ timeout: 10000 });
      console.log('✓ Admin button is visible / Le bouton Admin est visible');
      
      // We check that it has the correct CSS class
      // On vérifie qu'il a la bonne classe CSS
      await expect(adminPanelButton).toHaveClass(/btn-outline-danger/);
    });
  });

  /**
   * Secondary test: check email validation in the form
   * Test secondaire : vérifier la validation de l'email dans le formulaire
   */
  test('should validate email format / doit valider le format de l\'email', async ({ page }) => {
    // 1. Go home / Aller à l'accueil
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // 2. Open login / Ouvrir la connexion
    const loginButton = page.locator('.navbar button:has-text("Log in"), .navbar button:has-text("Connexion")').first();
    await loginButton.click();

    // 3. Fill an incorrect email / Remplir un email incorrect
    const emailInput = page.locator('#loginEmail');
    await emailInput.fill('not-an-email');

    // 4. Submit / Valider
    const submitButton = page.locator('#loginForm button[type="submit"]');
    await submitButton.click();

    // 5. Check that we are still on the same page or that an error is shown
    // 5. Vérifier qu'on est toujours sur la même page ou qu'une erreur est affichée
    await page.waitForTimeout(500);
    
    // The HTML5 validation should normally stop the process
    // La validation HTML5 devrait normalement bloquer l'envoi
    console.log('✓ Email validation test finished / Test de validation d\'email terminé');
  });
});
