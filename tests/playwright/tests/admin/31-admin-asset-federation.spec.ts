import { test, expect } from '@playwright/test';
import { loginAs, loginAsAdmin } from '../utils/auth';
import { env } from '../utils/env';

/**
 * Test du flow complet d'invitation per-asset entre deux tenants.
 * Full per-asset invitation flow test between two tenants.
 *
 * Scenario :
 * 1. Lespass cree un asset et invite Chantefrein
 * 2. Chantefrein voit l'invitation et l'accepte
 * 3. L'asset est visible par les deux tenants
 *
 * Scenario:
 * 1. Lespass creates an asset and invites Chantefrein
 * 2. Chantefrein sees the invitation and accepts it
 * 3. The asset is visible by both tenants
 *
 * Prerequis / Prerequisites:
 * - Tenants Lespass et Chantefrein existent
 * - Admin superuser (jturbeaux@pm.me) a acces aux deux
 * - module_monnaie_locale active sur les deux tenants
 */

// Suffixe unique par run pour eviter les conflits avec les runs precedents.
// Unique suffix per run to avoid conflicts with previous runs.
const RUN_ID = Date.now().toString(36).slice(-5);
const ASSET_NAME = `PW Test Fed ${RUN_ID}`;
const CHANTEFREIN_DOMAIN = `chantefrein.${env.DOMAIN}`;
const CHANTEFREIN_BASE_URL = `https://${CHANTEFREIN_DOMAIN}`;

test.describe('Asset Federation / Federation d\'assets', () => {

    test('Full per-asset invitation flow / Flow complet invitation per-asset', async ({ page }) => {

        // -----------------------------------------------------------
        // Step 1 : Login sur Lespass admin
        // Step 1: Login on Lespass admin
        // -----------------------------------------------------------
        await test.step('Login on Lespass admin / Connexion admin Lespass', async () => {
            await loginAsAdmin(page);
            console.log('✓ Logged in on Lespass / Connecte sur Lespass');
        });

        // -----------------------------------------------------------
        // Step 2 : Naviguer vers la changelist Asset
        // Step 2: Navigate to Asset changelist
        // -----------------------------------------------------------
        await test.step('Navigate to Asset changelist / Naviguer vers la liste des assets', async () => {
            await page.goto('/admin/fedow_core/asset/');
            await page.waitForLoadState('networkidle');
            await expect(page).toHaveURL(/\/admin\/fedow_core\/asset\//);
            console.log('✓ Asset changelist loaded / Liste des assets chargee');
        });

        // -----------------------------------------------------------
        // Step 3 : Creer un nouvel asset
        // Step 3: Create a new asset
        // -----------------------------------------------------------
        await test.step('Create a new asset / Creer un nouvel asset', async () => {
            // Cliquer sur le bouton "Ajouter" / Click "Add" button
            const addButton = page.locator('a[href$="/admin/fedow_core/asset/add/"]').first();
            await addButton.click();
            await page.waitForLoadState('networkidle');
            await expect(page).toHaveURL(/\/admin\/fedow_core\/asset\/add\//);

            // Remplir le formulaire / Fill the form
            await page.locator('input[name="name"]').fill(ASSET_NAME);
            await page.locator('input[name="currency_code"]').fill('EUR');
            await page.locator('select[name="category"]').selectOption('TLF');

            // Sauvegarder / Save
            await page.locator('input[name="_save"], button[name="_save"]').click();
            await page.waitForLoadState('networkidle');

            console.log(`✓ Asset "${ASSET_NAME}" created / Asset "${ASSET_NAME}" cree`);
        });

        // -----------------------------------------------------------
        // Step 4 : Editer l'asset → inviter Chantefrein
        // Step 4: Edit the asset → invite Chantefrein
        // -----------------------------------------------------------
        let assetEditUrl: string;
        await test.step('Edit asset and invite Chantefrein / Editer et inviter Chantefrein', async () => {
            // On devrait etre redirige vers la changelist apres le save.
            // Cliquer sur l'asset qu'on vient de creer.
            // We should be redirected to changelist after save.
            // Click on the asset we just created.
            const assetLink = page.locator(`#result_list a:has-text("${ASSET_NAME}")`).first();
            await expect(assetLink).toBeVisible({ timeout: 10000 });
            await assetLink.click();
            await page.waitForLoadState('networkidle');

            // Sauvegarder l'URL d'edition pour plus tard.
            // Save the edit URL for later.
            assetEditUrl = page.url();

            // Le champ pending_invitations est un combobox Unfold (Tom Select).
            // Trouver le searchbox a l'interieur du combobox.
            // The pending_invitations field is an Unfold combobox (Tom Select).
            // Find the searchbox inside the combobox.
            const searchBox = page.getByRole('searchbox').last();
            await expect(searchBox).toBeVisible({ timeout: 5000 });
            await searchBox.click();
            await searchBox.fill('Chantefrein');

            // Attendre le resultat et cliquer dessus.
            // Wait for the result and click it.
            const chantefreinOption = page.getByRole('option', { name: /Chantefrein/i }).first();
            await expect(chantefreinOption).toBeVisible({ timeout: 10000 });
            await chantefreinOption.click();

            // Sauvegarder / Save
            await page.locator('input[name="_save"], button[name="_save"]').click();
            await page.waitForLoadState('networkidle');

            console.log('✓ Chantefrein invited / Chantefrein invite');
        });

        // -----------------------------------------------------------
        // Step 5 : Verifier la colonne "Lieux federes" sur Lespass
        // Step 5: Verify "Lieux federes" column on Lespass
        // -----------------------------------------------------------
        await test.step('Verify federated venues on Lespass / Verifier lieux federes sur Lespass', async () => {
            // On est sur la changelist apres le save.
            // We are on the changelist after save.
            await expect(page).toHaveURL(/\/admin\/fedow_core\/asset\//);

            // La colonne "Lieux federes" doit afficher "Lespass" (createur uniquement).
            // Chantefrein n'a pas encore accepte, donc il n'est PAS dans federated_with.
            // The "Lieux federes" column should show "Lespass" (creator only).
            // Chantefrein has not accepted yet, so it's NOT in federated_with.
            const assetRow = page.locator(`#result_list tr:has-text("${ASSET_NAME}")`).first();
            await expect(assetRow).toBeVisible();
            const rowText = await assetRow.textContent();
            expect(rowText).toContain('Lespass');
            expect(rowText).not.toContain('Chantefrein');

            console.log('✓ Federated venues show only Lespass / Lieux federes : Lespass seul');
        });

        // -----------------------------------------------------------
        // Step 6-7 : Login sur Chantefrein admin
        // Step 6-7: Login on Chantefrein admin
        //
        // loginAs() utilise page.goto('/') qui resout vers le baseURL (Lespass).
        // On doit reproduire le flow avec des URLs absolues vers Chantefrein.
        // loginAs() uses page.goto('/') which resolves to baseURL (Lespass).
        // We must reproduce the flow with absolute URLs to Chantefrein.
        // -----------------------------------------------------------
        await test.step('Login on Chantefrein admin / Connexion admin Chantefrein', async () => {
            await page.goto(`${CHANTEFREIN_BASE_URL}/`);
            await page.waitForLoadState('networkidle');

            // Cliquer sur le bouton de login / Click login button
            const loginButton = page.locator(
                '.navbar button:has-text("Log in"), .navbar button:has-text("Connexion")'
            ).first();
            await expect(loginButton).toBeVisible({ timeout: 10000 });
            await loginButton.click();

            // Remplir l'email / Fill email
            const emailInput = page.locator('#loginEmail');
            await expect(emailInput).toBeVisible({ timeout: 5000 });
            await emailInput.fill(env.ADMIN_EMAIL);

            // Soumettre / Submit
            const submitButton = page.locator('#loginForm button[type="submit"]');
            await submitButton.click();

            // Cliquer sur le lien TEST MODE / Click TEST MODE link
            const testModeLink = page.locator('a:has-text("TEST MODE")');
            await expect(testModeLink).toBeVisible({ timeout: 10000 });
            await testModeLink.click();
            await page.waitForLoadState('networkidle');

            console.log('✓ Logged in on Chantefrein / Connecte sur Chantefrein');
        });

        // -----------------------------------------------------------
        // Step 8 : Verifier que l'invitation est visible
        // Step 8: Verify invitation is visible
        // -----------------------------------------------------------
        await test.step('Verify invitation visible on Chantefrein / Verifier invitation visible', async () => {
            await page.goto(`${CHANTEFREIN_BASE_URL}/admin/fedow_core/asset/`);
            await page.waitForLoadState('networkidle');

            // Le panneau d'invitations doit etre visible.
            // The invitations panel must be visible.
            const invitationsPanel = page.locator('[data-testid="asset-invitations-panel"]');
            await expect(invitationsPanel).toBeVisible({ timeout: 10000 });

            // L'invitation pour notre asset doit etre presente (nom visible).
            // The invitation for our asset must be present (name visible).
            await expect(invitationsPanel.locator(`text=${ASSET_NAME}`)).toBeVisible();

            console.log('✓ Invitation visible on Chantefrein / Invitation visible sur Chantefrein');
        });

        // -----------------------------------------------------------
        // Step 9 : Accepter l'invitation
        // Step 9: Accept the invitation
        // -----------------------------------------------------------
        await test.step('Accept invitation / Accepter l\'invitation', async () => {
            // Cliquer sur "Accepter le partage" pour cet asset.
            // Click "Accepter le partage" for this asset.
            const acceptButton = page.locator(
                '[data-testid="asset-invitations-panel"] button:has-text("Accepter le partage")'
            ).first();
            await expect(acceptButton).toBeVisible();
            await acceptButton.click();
            await page.waitForLoadState('networkidle');

            // Verifier le message de succes.
            // Check the success message.
            const successMessage = page.locator('.messagelist .success, [class*="alert-success"], [class*="bg-green"]');
            await expect(successMessage.first()).toBeVisible({ timeout: 10000 });

            console.log('✓ Invitation accepted / Invitation acceptee');
        });

        // -----------------------------------------------------------
        // Step 10 : Verifier l'asset dans la changelist de Chantefrein
        // Step 10: Verify asset in Chantefrein changelist
        // -----------------------------------------------------------
        await test.step('Verify asset in Chantefrein changelist / Verifier asset dans la liste Chantefrein', async () => {
            // Apres acceptation, on est redirige vers la changelist.
            // After acceptance, we are redirected to changelist.
            await expect(page).toHaveURL(/\/admin\/fedow_core\/asset\//);

            // L'asset doit apparaitre dans la liste.
            // The asset must appear in the list.
            const assetRow = page.locator(`#result_list tr:has-text("${ASSET_NAME}")`).first();
            await expect(assetRow).toBeVisible({ timeout: 10000 });

            // La colonne "Lieux federes" doit afficher Lespass ET Chantefrein.
            // The "Lieux federes" column should show both Lespass AND Chantefrein.
            const rowText = await assetRow.textContent();
            expect(rowText).toContain('Lespass');
            expect(rowText).toContain('Chantefrein');

            console.log('✓ Asset visible with both venues / Asset visible avec les deux lieux');
        });

        // -----------------------------------------------------------
        // Step 11 : Verifier lecture seule pour Chantefrein
        // Step 11: Verify read-only for Chantefrein
        // -----------------------------------------------------------
        await test.step('Verify read-only on Chantefrein / Verifier lecture seule sur Chantefrein', async () => {
            // Cliquer sur l'asset pour ouvrir la vue d'edition.
            // Click on the asset to open the edit view.
            const assetLink = page.locator(`#result_list a:has-text("${ASSET_NAME}")`).first();
            await assetLink.click();
            await page.waitForLoadState('networkidle');

            // Un lieu federe (non-createur) ne doit pas voir le bouton "Enregistrer".
            // Ou les champs doivent etre en readonly.
            // A federated venue (non-creator) should not see the "Save" button.
            // Or fields should be readonly.
            const saveButton = page.locator(
                'input[name="_save"], button[name="_save"], input[name="_continue"], button[name="_continue"]'
            );
            const saveButtonCount = await saveButton.count();

            // Pas de bouton save OU tous les champs sont readonly.
            // No save button OR all fields are readonly.
            if (saveButtonCount > 0) {
                // Si le bouton existe quand meme (Unfold peut l'afficher),
                // verifier que les champs importants sont readonly.
                // If button exists anyway (Unfold might display it),
                // check that important fields are readonly.
                const nameField = page.locator('input[name="name"]');
                if (await nameField.count() > 0) {
                    const isDisabled = await nameField.isDisabled();
                    const isReadonly = await nameField.getAttribute('readonly');
                    const fieldIsProtected = isDisabled || isReadonly !== null;
                    expect(fieldIsProtected).toBeTruthy();
                }
            }

            console.log('✓ Asset is read-only for Chantefrein / Asset en lecture seule pour Chantefrein');
        });

        // -----------------------------------------------------------
        // Step 12 : Retour sur Lespass — verifier federated_with
        // Step 12: Back on Lespass — verify federated_with
        // -----------------------------------------------------------
        await test.step('Verify federation on Lespass / Verifier federation sur Lespass', async () => {
            // La session Lespass est toujours active (cookie du step 1).
            // Aller directement a l'admin sans re-login.
            // Lespass session is still active (cookie from step 1).
            // Go directly to admin without re-login.
            const lespassBaseUrl = `https://${env.SUB}.${env.DOMAIN}`;
            await page.goto(`${lespassBaseUrl}/admin/fedow_core/asset/`);
            await page.waitForLoadState('networkidle');

            // La colonne "Lieux federes" doit maintenant afficher
            // Lespass ET Chantefrein.
            // The "Lieux federes" column should now show
            // both Lespass AND Chantefrein.
            const assetRow = page.locator(`#result_list tr:has-text("${ASSET_NAME}")`).first();
            await expect(assetRow).toBeVisible({ timeout: 10000 });
            const rowText = await assetRow.textContent();
            expect(rowText).toContain('Lespass');
            expect(rowText).toContain('Chantefrein');

            console.log('✓ Lespass sees Chantefrein as federated / Lespass voit Chantefrein federe');
        });
    });
});
