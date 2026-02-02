import { test, expect } from '@playwright/test';

test.describe('Theme and Language Switch / Changement de Thème et Langue', () => {

  test.beforeEach(async ({ page }) => {
    // Navigate to the homepage before each test
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('should toggle theme / doit changer le thème', async ({ page }) => {
    // Check initial theme (should be light by default or as per localStorage)
    const html = page.locator('html');
    
    // Toggle theme using the navbar button
    const themeToggle = page.locator('#themeToggle');
    await expect(themeToggle).toBeVisible();

    // Get current theme
    const initialTheme = await html.getAttribute('data-bs-theme') || 'light';
    const targetTheme = initialTheme === 'dark' ? 'light' : 'dark';

    await test.step(`Switch to ${targetTheme} theme`, async () => {
      await themeToggle.click();
      await expect(html).toHaveAttribute('data-bs-theme', targetTheme);
    });

    await test.step(`Switch back to ${initialTheme} theme`, async () => {
      await themeToggle.click();
      await expect(html).toHaveAttribute('data-bs-theme', initialTheme);
    });
  });

  test('should switch language / doit changer la langue', async ({ page }) => {
    const html = page.locator('html');
    
    // Check initial language
    const initialLang = await html.getAttribute('lang');
    console.log(`Initial language: ${initialLang}`);

    const languageDropdown = page.locator('#languageDropdown');
    await expect(languageDropdown).toBeVisible();

    // Open dropdown
    await languageDropdown.click();

    // Select English if current is French, or vice versa
    const targetLang = initialLang === 'fr' ? 'en' : 'fr';
    const langSelector = `.language-select-btn[data-lang="${targetLang}"]`;
    const langBtn = page.locator(langSelector);

    await test.step(`Switch to ${targetLang} language`, async () => {
      await expect(langBtn).toBeVisible();
      await langBtn.click();
      
      // Page should reload
      await page.waitForLoadState('networkidle');
      
      // Check if lang attribute changed
      await expect(html).toHaveAttribute('lang', targetLang);
    });

    // Check if preferences page also reflects the change (optional but good)
    /*
    await test.step('Verify language in preferences page', async () => {
       // Note: This might require login if /my_account/preferences/ is protected
       // For now let's stick to navbar verification
    });
    */
  });

  test('should sync theme and language with preferences page / doit synchroniser le thème et la langue avec la page des préférences', async ({ page }) => {
    // This test might require login. Let's try to access preferences.
    // In many TiBillet setups, /my_account/ is accessible if TEST mode is on or after login.
    
    // Assuming we need to login
    const { loginAsAdmin } = require('./utils/auth');
    await loginAsAdmin(page);
    
    await page.goto('/my_account/profile/'); // Corrected path from /my_account/preferences/
    await page.waitForLoadState('networkidle');

    const html = page.locator('html');
    const themeCheck = page.locator('#darkThemeCheck');
    const langSelect = page.locator('#languageSelect');

    await test.step('Toggle theme from preferences', async () => {
      // Ensure the element is visible
      await expect(themeCheck).toBeVisible({ timeout: 10000 });
      const isChecked = await themeCheck.isChecked();
      await themeCheck.click();
      const expectedTheme = isChecked ? 'light' : 'dark';
      await expect(html).toHaveAttribute('data-bs-theme', expectedTheme);
    });

    await test.step('Change language from preferences', async () => {
      const currentLang = await langSelect.inputValue();
      const targetLang = currentLang === 'fr' ? 'en' : 'fr';
      await langSelect.selectOption(targetLang);
      
      await page.waitForLoadState('networkidle');
      await expect(html).toHaveAttribute('lang', targetLang);
    });
  });
});
