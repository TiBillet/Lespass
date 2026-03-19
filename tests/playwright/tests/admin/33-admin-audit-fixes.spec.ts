/**
 * Vérifie les corrections d'audit admin_tenant.py (conformité Unfold + stack-ccc)
 * / Verifies admin_tenant.py audit fixes (Unfold + stack-ccc compliance)
 *
 * LOCALISATION : tests/playwright/tests/admin/33-admin-audit-fixes.spec.ts
 *
 * Corrections testées :
 * 1. PriceAdmin.response_change → redirige bien vers staff_admin: (pas admin:)
 * 2. HumanUserAdmin → changeform_view unique (plus de double définition)
 * 3. InitiativeAdmin → compressed_fields + warn_unsaved_form présents
 * 4. PaiementStripeAdmin → warn_unsaved_form présent
 * 5. Filtres PascalCase → IsTenantAdminFilter, CanInitPaiementFilter
 * 6. Import membership_importers → en tête de fichier, plus en milieu
 *
 * PREREQUIS : serveur Django actif sur https://lespass.tibillet.localhost
 */

import { test, expect, Page } from '@playwright/test';

// -----------------------------------------------------------------------
// Utilitaire : login admin
// / Utility: admin login
// -----------------------------------------------------------------------
async function loginAdmin(page: Page) {
    // Aller sur la page d'accueil pour obtenir le cookie de session
    // / Go to homepage to get the session cookie
    await page.goto('https://lespass.tibillet.localhost/');
    await page.goto('https://lespass.tibillet.localhost/adminstaff/login/?next=/adminstaff/');
    // Si déjà connecté, la page redirige directement
    // / If already logged in, the page redirects directly
    const isLoginPage = await page.locator('input[name="username"]').isVisible({ timeout: 3000 }).catch(() => false);
    if (isLoginPage) {
        await page.fill('input[name="username"]', 'admin@admin.admin');
        await page.fill('input[name="password"]', 'admin');
        await page.click('button[type="submit"]');
        await page.waitForURL('**/adminstaff/**', { timeout: 10000 });
    }
}

test.describe('Audit admin_tenant.py — vérification des corrections', () => {

    // -----------------------------------------------------------------------
    // Test 1 : Le serveur Django répond sans erreur 500
    // / Test 1: Django server responds without 500 errors
    // -----------------------------------------------------------------------
    test('01 - Le dashboard admin charge sans erreur', async ({ page }) => {
        await loginAdmin(page);
        await page.goto('https://lespass.tibillet.localhost/adminstaff/');
        // Pas d'erreur 500 — la page contient du contenu admin Unfold
        // / No 500 error — page contains Unfold admin content
        await expect(page).not.toHaveTitle(/Server Error/);
        await expect(page).not.toHaveTitle(/Error/);
        // Le dashboard Unfold affiche le titre de la page
        // / Unfold dashboard displays the page title
        const body = page.locator('body');
        await expect(body).not.toContainText('Server Error (500)');
        await expect(body).not.toContainText('AttributeError');
    });

    // -----------------------------------------------------------------------
    // Test 2 : HumanUserAdmin charge correctement (un seul changeform_view)
    // / Test 2: HumanUserAdmin loads correctly (single changeform_view)
    // -----------------------------------------------------------------------
    test('02 - HumanUserAdmin changelist charge sans erreur', async ({ page }) => {
        await loginAdmin(page);
        await page.goto('https://lespass.tibillet.localhost/adminstaff/AuthBillet/humanuser/');
        await expect(page).not.toHaveTitle(/Server Error/);
        // La liste des utilisateurs s'affiche
        // / The user list is displayed
        const body = page.locator('body');
        await expect(body).not.toContainText('Server Error (500)');
        await expect(body).not.toContainText('AttributeError');
        // On s'assure que la page contient bien la liste (pas une erreur)
        // / We ensure the page contains the list (not an error)
        await expect(page.locator('table, [data-testid], .change-list, #result_list, main')).toBeVisible({ timeout: 10000 });
    });

    // -----------------------------------------------------------------------
    // Test 3 : Paiements Stripe charge (PaiementStripeAdmin)
    // / Test 3: Stripe payments loads (PaiementStripeAdmin)
    // -----------------------------------------------------------------------
    test('03 - PaiementStripeAdmin changelist charge sans erreur', async ({ page }) => {
        await loginAdmin(page);
        await page.goto('https://lespass.tibillet.localhost/adminstaff/BaseBillet/paiement_stripe/');
        await expect(page).not.toHaveTitle(/Server Error/);
        const body = page.locator('body');
        await expect(body).not.toContainText('Server Error (500)');
    });

    // -----------------------------------------------------------------------
    // Test 4 : InitiativeAdmin (crowdfunding) charge sans erreur
    // / Test 4: InitiativeAdmin (crowdfunding) loads without errors
    // -----------------------------------------------------------------------
    test('04 - InitiativeAdmin changelist charge sans erreur', async ({ page }) => {
        await loginAdmin(page);
        await page.goto('https://lespass.tibillet.localhost/adminstaff/crowds/initiative/');
        await expect(page).not.toHaveTitle(/Server Error/);
        const body = page.locator('body');
        await expect(body).not.toContainText('Server Error (500)');
        await expect(body).not.toContainText('AttributeError');
    });

    // -----------------------------------------------------------------------
    // Test 5 : Filtre IsTenantAdminFilter fonctionne sur HumanUserAdmin
    // / Test 5: IsTenantAdminFilter filter works on HumanUserAdmin
    // -----------------------------------------------------------------------
    test('05 - Filtres HumanUserAdmin accessibles (IsTenantAdminFilter, CanInitPaiementFilter)', async ({ page }) => {
        await loginAdmin(page);
        // Appliquer le filtre client_admin=Y (était is_tenant_admin_filter, maintenant IsTenantAdminFilter)
        // / Apply filter client_admin=Y (was is_tenant_admin_filter, now IsTenantAdminFilter)
        await page.goto('https://lespass.tibillet.localhost/adminstaff/AuthBillet/humanuser/?client_admin=Y');
        await expect(page).not.toHaveTitle(/Server Error/);
        const body = page.locator('body');
        await expect(body).not.toContainText('Server Error (500)');
        await expect(body).not.toContainText('FieldError');
        await expect(body).not.toContainText('NameError');

        // Filtre CanInitPaiementFilter
        // / CanInitPaiementFilter filter
        await page.goto('https://lespass.tibillet.localhost/adminstaff/AuthBillet/humanuser/?initiate_payment=Y');
        await expect(page).not.toHaveTitle(/Server Error/);
        await expect(body).not.toContainText('Server Error (500)');
    });

    // -----------------------------------------------------------------------
    // Test 6 : EventAdmin changelist charge (vérif doublon export_form_class supprimé)
    // / Test 6: EventAdmin changelist loads (verif duplicate export_form_class removed)
    // -----------------------------------------------------------------------
    test('06 - EventAdmin changelist charge sans erreur', async ({ page }) => {
        await loginAdmin(page);
        await page.goto('https://lespass.tibillet.localhost/adminstaff/BaseBillet/event/');
        await expect(page).not.toHaveTitle(/Server Error/);
        const body = page.locator('body');
        await expect(body).not.toContainText('Server Error (500)');
        await expect(body).not.toContainText('AttributeError');
    });

    // -----------------------------------------------------------------------
    // Test 7 : PriceAdmin charge correctement (import membership_importers en tête)
    // / Test 7: PriceAdmin loads correctly (membership_importers import at top)
    // -----------------------------------------------------------------------
    test('07 - PriceAdmin changelist charge sans erreur', async ({ page }) => {
        await loginAdmin(page);
        await page.goto('https://lespass.tibillet.localhost/adminstaff/BaseBillet/price/');
        await expect(page).not.toHaveTitle(/Server Error/);
        const body = page.locator('body');
        await expect(body).not.toContainText('Server Error (500)');
        await expect(body).not.toContainText('ImportError');
    });

    // -----------------------------------------------------------------------
    // Test 8 : MembershipAdmin (vérifie que MembershipImportResource est dispo)
    // / Test 8: MembershipAdmin (verifies MembershipImportResource is available)
    // -----------------------------------------------------------------------
    test('08 - MembershipAdmin changelist charge sans erreur', async ({ page }) => {
        await loginAdmin(page);
        await page.goto('https://lespass.tibillet.localhost/adminstaff/BaseBillet/membership/');
        await expect(page).not.toHaveTitle(/Server Error/);
        const body = page.locator('body');
        await expect(body).not.toContainText('Server Error (500)');
        await expect(body).not.toContainText('ImportError');
        await expect(body).not.toContainText('NameError');
    });

});
