import { test, expect } from '@playwright/test';
import { env } from './utils/env';
import { loginAsAdmin } from './utils/auth';

/**
 * TEST: Discovery PIN pairing flow
 * TEST : Flux d'appairage par code PIN (Discovery)
 *
 * This test verifies the full device pairing flow:
 * Ce test vérifie le flux complet d'appairage d'un terminal :
 * 1. Login as admin / Connexion admin
 * 2. Navigate to PairingDevice admin / Naviguer vers l'admin PairingDevice
 * 3. Create a new PairingDevice / Créer un nouveau PairingDevice
 * 4. Read the generated PIN / Lire le PIN généré
 * 5. Call the public claim API with the PIN / Appeler l'API publique claim avec le PIN
 * 6. Verify the response (server_url, api_key, device_name) / Vérifier la réponse
 * 7. Verify re-claim fails (PIN already used) / Vérifier que le re-claim échoue
 */

test.describe('Discovery PIN Pairing / Appairage PIN Discovery', () => {

  test('should create device, claim PIN, and reject re-claim / doit créer un device, réclamer le PIN, et rejeter le re-claim', async ({ page, request }) => {

    // Étape 1 : Connexion admin / Step 1: Login as admin
    await test.step('Login as admin / Connexion admin', async () => {
      await loginAsAdmin(page);
    });

    // Étape 2 : Naviguer vers l'admin PairingDevice / Step 2: Navigate to PairingDevice admin
    await test.step('Navigate to PairingDevice admin / Naviguer vers l\'admin PairingDevice', async () => {
      await page.goto('/admin/discovery/pairingdevice/');
      await page.waitForLoadState('networkidle');
      await expect(page).toHaveURL(/\/admin\/discovery\/pairingdevice\//);
      console.log('✓ On PairingDevice list page / Sur la page liste PairingDevice');
    });

    // Étape 3 : Créer un nouveau PairingDevice / Step 3: Create a new PairingDevice
    await test.step('Create a new PairingDevice / Créer un nouveau PairingDevice', async () => {
      // Cliquer sur le bouton "+" (Unfold admin) pour ajouter un device
      // Click the "+" button (Unfold admin) to add a device
      const addButton = page.locator('a[href*="/admin/discovery/pairingdevice/add/"]').first();
      await expect(addButton).toBeVisible({ timeout: 10000 });
      await addButton.click();
      await page.waitForLoadState('networkidle');
      console.log('✓ On add PairingDevice form / Sur le formulaire ajout PairingDevice');

      // Remplir le nom du device / Fill the device name
      const nameInput = page.locator('input[name="name"]');
      await expect(nameInput).toBeVisible({ timeout: 5000 });
      await nameInput.fill('Terminal Test Playwright');

      // Cliquer sur "Save and continue editing" pour voir le PIN généré
      // Click "Save and continue editing" to see the generated PIN
      const saveContinueButton = page.locator('button[name="_continue"], input[name="_continue"]').first();
      await saveContinueButton.click();
      await page.waitForLoadState('networkidle');
      console.log('✓ PairingDevice saved / PairingDevice enregistré');
    });

    // Étape 4 : Lire le PIN généré / Step 4: Read the generated PIN
    let pinCode = '';
    await test.step('Read the generated PIN / Lire le PIN généré', async () => {
      // Le PIN est affiché en gros dans un <span> stylé
      // The PIN is displayed large in a styled <span>
      const pinDisplay = page.locator('span').filter({ hasText: /^\d{3}\s\d{3}$/ }).first();
      await expect(pinDisplay).toBeVisible({ timeout: 5000 });
      const pinText = await pinDisplay.innerText();

      // Retirer l'espace du format "123 456" → "123456"
      // Remove space from format "123 456" → "123456"
      pinCode = pinText.replace(/\s/g, '');
      expect(pinCode).toMatch(/^\d{6}$/);
      console.log(`✓ PIN generated: ${pinCode} / PIN généré : ${pinCode}`);
    });

    // Étape 5 : Appeler l'API publique claim / Step 5: Call the public claim API
    let claimResponseBody: any;
    await test.step('Claim PIN via public API / Réclamer le PIN via l\'API publique', async () => {
      // L'API discovery est sur le domaine racine (public), pas sur le tenant
      // The discovery API is on the root domain (public), not on the tenant
      const publicBaseUrl = `https://${env.DOMAIN}`;
      const claimUrl = `${publicBaseUrl}/api/discovery/claim/`;

      const claimResponse = await request.post(claimUrl, {
        data: { pin_code: pinCode },
        headers: { 'Content-Type': 'application/json' },
        ignoreHTTPSErrors: true,
      });

      expect(claimResponse.status()).toBe(200);
      claimResponseBody = await claimResponse.json();

      // Vérifier que la réponse contient les champs attendus
      // Verify the response contains the expected fields
      expect(claimResponseBody).toHaveProperty('server_url');
      expect(claimResponseBody).toHaveProperty('api_key');
      expect(claimResponseBody).toHaveProperty('device_name');

      // Vérifier les valeurs / Verify values
      expect(claimResponseBody.server_url).toContain(env.DOMAIN);
      expect(claimResponseBody.api_key).toBeTruthy();
      expect(claimResponseBody.device_name).toBe('Terminal Test Playwright');

      console.log(`✓ Claim successful / Claim réussi`);
      console.log(`  server_url: ${claimResponseBody.server_url}`);
      console.log(`  device_name: ${claimResponseBody.device_name}`);
      console.log(`  api_key length: ${claimResponseBody.api_key.length}`);
    });

    // Étape 6 : Vérifier que le re-claim échoue / Step 6: Verify re-claim fails
    await test.step('Verify re-claim is rejected / Vérifier que le re-claim est rejeté', async () => {
      const publicBaseUrl = `https://${env.DOMAIN}`;
      const claimUrl = `${publicBaseUrl}/api/discovery/claim/`;

      const reClaimResponse = await request.post(claimUrl, {
        data: { pin_code: pinCode },
        headers: { 'Content-Type': 'application/json' },
        ignoreHTTPSErrors: true,
      });

      // Le re-claim doit échouer (400 Bad Request — validation error)
      // Re-claim must fail (400 Bad Request — validation error)
      expect(reClaimResponse.status()).toBe(400);
      const reClaimBody = await reClaimResponse.json();
      console.log(`✓ Re-claim rejected as expected / Re-claim rejeté comme prévu`);
      console.log(`  Response: ${JSON.stringify(reClaimBody)}`);
    });

    // Étape 7 : Vérifier qu'un PIN invalide échoue aussi / Step 7: Verify invalid PIN also fails
    await test.step('Verify invalid PIN is rejected / Vérifier qu\'un PIN invalide est rejeté', async () => {
      const publicBaseUrl = `https://${env.DOMAIN}`;
      const claimUrl = `${publicBaseUrl}/api/discovery/claim/`;

      const invalidResponse = await request.post(claimUrl, {
        data: { pin_code: '000000' },
        headers: { 'Content-Type': 'application/json' },
        ignoreHTTPSErrors: true,
      });

      // Un PIN inconnu doit échouer (400 Bad Request)
      // An unknown PIN must fail (400 Bad Request)
      expect(invalidResponse.status()).toBe(400);
      console.log('✓ Invalid PIN rejected / PIN invalide rejeté');
    });
  });
});
