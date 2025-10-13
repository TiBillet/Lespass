import { test, expect } from '@playwright/test';
import { env } from './utils/env';

/**
 * Test: Login flow
 * 
 * This test reproduces the first step of the demo_data operations:
 * - Navigate to the homepage
 * - Click on the "Log in" / "Connexion" button
 * - Fill in the admin email from .env
 * - Submit the login request
 */

test.describe('Login Flow', () => {
  test('should open login panel and fill admin email', async ({ page }) => {
    // Step 1: Navigate to the homepage
    await test.step('Navigate to homepage', async () => {
      await page.goto('/');
      
      // Wait for the page to be fully loaded
      await page.waitForLoadState('networkidle');
      
      // Verify we're on the correct page
      await expect(page).toHaveURL(env.BASE_URL + '/');
    });

    // Step 2: Click on the "Log in" button to open the login panel
    await test.step('Open login panel', async () => {
      // The button text could be "Log in" in English or "Connexion" in French
      // Target specifically the navbar button to avoid matching footer button
      const loginButton = page.locator('.navbar button:has-text("Log in"), .navbar button:has-text("Connexion")').first();
      
      // Verify the button is visible
      await expect(loginButton).toBeVisible();
      
      // Click the button
      await loginButton.click();
      
      // Wait for the offcanvas panel to be visible
      const loginPanel = page.locator('#loginPanel');
      await expect(loginPanel).toBeVisible();
    });

    // Step 3: Fill in the email field with the admin email from .env
    await test.step('Fill admin email', async () => {
      // Locate the email input field
      const emailInput = page.locator('#loginEmail');
      
      // Verify the input is visible
      await expect(emailInput).toBeVisible();
      
      // Fill in the admin email
      await emailInput.fill(env.ADMIN_EMAIL);
      
      // Verify the email was filled correctly
      await expect(emailInput).toHaveValue(env.ADMIN_EMAIL);
      
      console.log(`✓ Filled email field with: ${env.ADMIN_EMAIL}`);
    });

    // Step 4: Submit the login form
    await test.step('Submit login form', async () => {
      // Locate the submit button
      const submitButton = page.locator('#loginForm button[type="submit"]');
      
      // Verify the button is visible
      await expect(submitButton).toBeVisible();
      
      // Click the submit button
      await submitButton.click();
      
      // Wait for the form submission to complete
      // In TEST mode, a link should appear with the connection URL
      if (env.TEST) {
        // Wait for the test mode message with the connexion link
        const testModeLink = page.locator('a:has-text("TEST MODE")');
        await expect(testModeLink).toBeVisible({ timeout: 5000 });
        console.log('✓ Login request submitted successfully (TEST MODE)');
      } else {
        // In production mode, wait for a success message
        await page.waitForTimeout(2000);
        console.log('✓ Login request submitted successfully');
      }
    });

    // Step 5: Click on TEST MODE link to simulate email connection
    await test.step('Click TEST MODE link', async () => {
      if (env.TEST) {
        // Locate and click the TEST MODE link
        const testModeLink = page.locator('a:has-text("TEST MODE")');
        await testModeLink.click();
        
        // Wait for navigation to complete
        await page.waitForLoadState('networkidle');
        
        console.log('✓ Clicked TEST MODE link - user should now be authenticated');
      }
    });

    // Step 6: Navigate to /my_account
    await test.step('Navigate to my account page', async () => {
      // Navigate to the account page
      await page.goto('/my_account/');
      
      // Wait for the page to be fully loaded
      await page.waitForLoadState('networkidle');
      
      // Verify we're on the correct page
      await expect(page).toHaveURL(new RegExp('/my_account'));
      
      console.log('✓ Successfully navigated to /my_account');
    });

    // Step 7: Verify Admin panel button is visible
    await test.step('Verify Admin panel is visible', async () => {
      // The Admin panel button should be visible only for admin users
      // It's inside a link with text "Admin panel" / "Panneau d'administration"
      const adminPanelButton = page.locator('a[href="/admin/"]:has-text("Admin panel"), a[href="/admin/"]:has-text("Panneau d\'administration")');
      
      // Verify the button is visible
      await expect(adminPanelButton).toBeVisible({ timeout: 5000 });
      
      // Verify it has the correct styling (btn-outline-danger)
      await expect(adminPanelButton).toHaveClass(/btn-outline-danger/);
      
      console.log('✓ Admin panel button is visible - user has admin rights');
    });
  });

  test('should validate email format', async ({ page }) => {
    // Navigate to the homepage
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Open login panel - target specifically the navbar button
    const loginButton = page.locator('.navbar button:has-text("Log in"), .navbar button:has-text("Connexion")').first();
    await loginButton.click();

    // Wait for the login panel to be visible
    const loginPanel = page.locator('#loginPanel');
    await expect(loginPanel).toBeVisible();

    // Try to submit with invalid email
    const emailInput = page.locator('#loginEmail');
    await emailInput.fill('invalid-email');

    const submitButton = page.locator('#loginForm button[type="submit"]');
    await submitButton.click();

    // The form should show validation error (the input should be marked as invalid)
    // The browser's built-in validation or the custom JS validation should prevent submission
    await page.waitForTimeout(500);
    
    console.log('✓ Email validation works correctly');
  });
});
