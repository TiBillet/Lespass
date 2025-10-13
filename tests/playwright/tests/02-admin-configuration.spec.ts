import { test, expect } from '@playwright/test';
import { env } from './utils/env';

/**
 * Test: Admin Configuration
 * 
 * This test reproduces Section 2 of demo_data_operations.md:
 * "Configuration générale (pour chaque tenant)"
 * 
 * Steps:
 * - Navigate to /admin/ (admin panel)
 * - Click on Settings/Configuration in the sidebar
 * - Fill in all required configuration fields
 * - Save the configuration
 * - Navigate to homepage (/) and verify the configured text is visible
 */

test.describe('Admin Configuration', () => {
  test('should fill configuration fields and verify on homepage', async ({ page }) => {
    // Step 1: Login as admin (reuse login flow)
    await test.step('Login as admin', async () => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      
      // Open login panel
      const loginButton = page.locator('.navbar button:has-text("Log in"), .navbar button:has-text("Connexion")').first();
      await loginButton.click();
      
      // Fill email and submit
      const emailInput = page.locator('#loginEmail');
      await emailInput.fill(env.ADMIN_EMAIL);
      
      const submitButton = page.locator('#loginForm button[type="submit"]');
      await submitButton.click();
      
      // Click TEST MODE link
      if (env.TEST) {
        const testModeLink = page.locator('a:has-text("TEST MODE")');
        await expect(testModeLink).toBeVisible({ timeout: 5000 });
        await testModeLink.click();
        await page.waitForLoadState('networkidle');
      }
      
      console.log('✓ Logged in as admin');
    });

    // Step 2: Navigate to admin panel
    await test.step('Navigate to admin panel', async () => {
      // The admin panel link has target="_blank", so we navigate directly
      await page.goto('/admin/');
      await page.waitForLoadState('networkidle');
      await expect(page).toHaveURL(/\/admin\//);
      
      console.log('✓ Navigated to admin panel');
    });

    // Step 3: Navigate to Configuration page
    await test.step('Open Configuration settings', async () => {
      // Navigate directly to the Configuration page
      // The URL pattern for singleton admin in Unfold/Django admin
      await page.goto('/admin/BaseBillet/configuration/');
      await page.waitForLoadState('networkidle');
      
      // Verify we're on the configuration page
      await expect(page.url()).toContain('configuration');
      
      console.log('✓ Opened Configuration page');
    });

    // Step 4: Check and fill configuration fields
    await test.step('Fill configuration fields', async () => {
      // The Configuration is a singleton, so we're already on the form page
      // Based on demo_data.py lines 74-111, we need to fill:
      
      // 1. Organisation name
      const organisationInput = page.locator('input[name="organisation"]');
      if (await organisationInput.count() > 0) {
        const currentValue = await organisationInput.inputValue();
        if (!currentValue || currentValue === 'lespass') {
          await organisationInput.fill('Le Tiers-Lustre');
          console.log('✓ Filled organisation name');
        } else {
          console.log('✓ Organisation already set:', currentValue);
        }
      }
      
      // 2. Short description
      const shortDescInput = page.locator('input[name="short_description"], textarea[name="short_description"]');
      if (await shortDescInput.count() > 0) {
        const currentValue = await shortDescInput.inputValue();
        if (!currentValue) {
          await shortDescInput.fill('Instance de démonstration du collectif imaginaire « Le Tiers-Lustre ».');
          console.log('✓ Filled short description');
        } else {
          console.log('✓ Short description already set');
        }
      }
      
      // 3. Long description (WYSIWYG editor - might be in iframe or contenteditable)
      const longDescTextarea = page.locator('textarea[name="long_description"]');
      if (await longDescTextarea.count() > 0) {
        const currentValue = await longDescTextarea.inputValue();
        if (!currentValue) {
          const longDesc = "Bienvenue sur Lespass, la plateforme en ligne de TiBillet.\nVous trouverez ici des exemples d'évènements à réserver et d'adhésions à prendre. Vous pouvez choisir entre tarifs gratuits, payants, en prix libre ou soumis à adhésion. Les adhésions peuvent être mensuelles ou annuelles, ponctuelles ou réccurentes.\nEnfin, vous avez en démonstration une badgeuse pour la gestion d'accès d'un espace de co-working.";
          await longDescTextarea.fill(longDesc);
          console.log('✓ Filled long description');
        } else {
          console.log('✓ Long description already set');
        }
      }
      
      // 4. Phone
      const phoneInput = page.locator('input[name="phone"]');
      if (await phoneInput.count() > 0) {
        const currentValue = await phoneInput.inputValue();
        if (!currentValue) {
          await phoneInput.fill('+33 1 23 45 67 89');
          console.log('✓ Filled phone');
        } else {
          console.log('✓ Phone already set');
        }
      }
      
      // 5. Email (should already be set to admin email, but verify)
      const emailInput = page.locator('input[name="email"]');
      if (await emailInput.count() > 0) {
        const currentValue = await emailInput.inputValue();
        if (!currentValue || currentValue !== env.ADMIN_EMAIL) {
          await emailInput.fill(env.ADMIN_EMAIL);
          console.log('✓ Set email to admin email');
        } else {
          console.log('✓ Email already set correctly');
        }
      }
      
      // 6. Site web
      const siteWebInput = page.locator('input[name="site_web"]');
      if (await siteWebInput.count() > 0) {
        const currentValue = await siteWebInput.inputValue();
        if (!currentValue) {
          await siteWebInput.fill('https://tibillet.org');
          console.log('✓ Filled site web');
        } else {
          console.log('✓ Site web already set');
        }
      }
      
      console.log('✓ All visible configuration fields checked and filled if needed');
    });

    // Step 4b: Upload images
    await test.step('Upload images', async () => {
      // Upload logo (vignette.webp)
      const logoInput = page.locator('input[name="logo"]');
      if (await logoInput.count() > 0) {
        // Check if there's already an image
        const clearCheckbox = page.locator('input[name="logo-clear"]');
        const hasClearCheckbox = await clearCheckbox.count() > 0;
        
        if (!hasClearCheckbox) {
          // No image yet, upload one
          await logoInput.setInputFiles('/home/jonas/TiBillet/dev/Lespass/tests/playwright/demo_data/vignette.webp');
          console.log('✓ Uploaded logo (vignette.webp)');
        } else {
          console.log('✓ Logo already set');
        }
      }
      
      // Upload background image (banner.jpg)
      const imgInput = page.locator('input[name="img"]');
      if (await imgInput.count() > 0) {
        // Check if there's already an image
        const clearCheckbox = page.locator('input[name="img-clear"]');
        const hasClearCheckbox = await clearCheckbox.count() > 0;
        
        if (!hasClearCheckbox) {
          // No image yet, upload one
          await imgInput.setInputFiles('/home/jonas/TiBillet/dev/Lespass/tests/playwright/demo_data/banner.jpg');
          console.log('✓ Uploaded background image (banner.jpg)');
        } else {
          console.log('✓ Background image already set');
        }
      }
      
      console.log('✓ Image uploads completed');
    });

    // Step 5: Save the configuration
    await test.step('Save configuration', async () => {
      // Look for save button (usually at the bottom of the form)
      const saveButton = page.locator('button[type="submit"]:has-text("Save"), button[type="submit"]:has-text("Enregistrer"), input[type="submit"][value="Save"], input[type="submit"][value="Enregistrer"]');
      
      if (await saveButton.count() > 0) {
        await saveButton.first().click();
        
        // Wait for save to complete
        await page.waitForLoadState('networkidle');
        
        // Check for success message
        const successMessage = page.locator('text="successfully", text="succès", text="enregistré"').first();
        if (await successMessage.count() > 0) {
          console.log('✓ Configuration saved successfully');
        } else {
          console.log('✓ Save button clicked (no explicit success message found)');
        }
      } else {
        console.log('⚠ No save button found - configuration might auto-save');
      }
    });

    // Step 6: Navigate to homepage and verify configured text and images are visible
    await test.step('Verify configuration on homepage', async () => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      
      // Wait a bit for any dynamic content to load
      await page.waitForTimeout(1000);
      
      // Check if the short description or long description is visible on the homepage
      // The text should be somewhere in the page body
      const pageContent = await page.content();
      
      // Look for the organisation name in navbar
      const orgName = page.locator('.navbar-brand').first();
      const orgNameText = await orgName.textContent();
      
      if (orgNameText?.includes('Le Tiers-Lustre') || orgNameText?.includes('Tiers-Lustre')) {
        console.log('✓ Organisation name visible in navbar');
      }
      
      // Check for logo image in navbar
      const logoImg = page.locator('.navbar-brand img');
      if (await logoImg.count() > 0) {
        const logoSrc = await logoImg.first().getAttribute('src');
        if (logoSrc && logoSrc.includes('vignette')) {
          console.log('✓ Logo image visible in navbar');
        } else if (logoSrc) {
          console.log('✓ Logo image visible in navbar (different source)');
        }
      }
      
      // Check for background/banner image
      const bannerImg = page.locator('img[src*="banner"], img[src*="media/images"]').first();
      if (await bannerImg.count() > 0) {
        console.log('✓ Background/banner image visible on homepage');
      }
      
      // Look for short or long description text
      const hasShortDesc = pageContent.includes('Instance de démonstration') || 
                          pageContent.includes('collectif imaginaire');
      const hasLongDesc = pageContent.includes('Bienvenue sur Lespass') || 
                         pageContent.includes('plateforme en ligne de TiBillet');
      
      if (hasShortDesc) {
        console.log('✓ Short description visible on homepage');
      }
      
      if (hasLongDesc) {
        console.log('✓ Long description visible on homepage');
      }
      
      // At least one should be visible
      expect(hasShortDesc || hasLongDesc || orgNameText?.includes('Tiers-Lustre')).toBeTruthy();
      
      console.log('✓ Configuration is visible on the homepage');
    });
  });
});
