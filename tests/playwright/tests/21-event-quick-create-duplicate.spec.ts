import { test, expect } from '@playwright/test';
import { loginAsAdmin } from './utils/auth';

function isoLocalFuture(offsetDays = 10, hour = 10, minute = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  d.setHours(hour, minute, 0, 0);
  // YYYY-MM-DDTHH:mm (without seconds)
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/**
 * TEST: Quick create event via offcanvas + duplicate handling
 * - Create an event from the simple form and verify it appears on agenda
 * - Try to create the same event (same name + same datetime) and verify:
 *   - an error is shown on the form
 *   - previously entered values are still present (not cleared)
 */

test.describe('Event quick create - duplicate prevention and form persistence', () => {
  test('create once then duplicate should show error and keep data', async ({ page }) => {
    // 1) Auth as admin (required to see the quick-create button)
    await loginAsAdmin(page);

    const eventName = `Playwright QuickCreate EVT ${Date.now()}`;
    const startLocal = isoLocalFuture(5, 10, 0);
    const endLocal = isoLocalFuture(5, 12, 0);

    // 2) Open agenda and the quick-create offcanvas
    await page.goto('/event/');
    await page.waitForLoadState('networkidle');

    const openBtn = page.locator('[hx-get="/event/simple_add_event/"]').first();
    await expect(openBtn).toBeVisible();
    await openBtn.click();

    // Wait for the form to load into offcanvas target
    const form = page.locator('form[hx-post="/event/simple_create_event/"]');
    await expect(form).toBeVisible();

    // 3) Fill the form and submit (first creation)
    await page.locator('input[name="name"]').fill(eventName);
    await page.locator('input[name="datetime_start"]').fill(startLocal);
    await page.locator('input[name="datetime_end"]').fill(endLocal);
    await page.locator('input[name="short_description"]').fill('Quick create from Playwright');
    await page.locator('textarea[name="long_description"]').fill('Detailed description for E2E test.');

    await form.locator('button[type="submit"]').click();

    // On success, the server responds with an HTMX client redirect to /event/
    await page.waitForURL('**/event/**');
    await page.waitForLoadState('networkidle');

    // Verify the event name is visible on the agenda list
    const eventList = page.locator('#event_list');
    await expect(eventList).toContainText(eventName);

    // 4) Try to create the same event again (duplicate)
    await openBtn.click();
    await expect(form).toBeVisible();

    await page.locator('input[name="name"]').fill(eventName);
    await page.locator('input[name="datetime_start"]').fill(startLocal);
    await page.locator('input[name="datetime_end"]').fill(endLocal);
    await page.locator('input[name="short_description"]').fill('Quick create from Playwright');
    await page.locator('textarea[name="long_description"]').fill('Detailed description for E2E test.');

    await form.locator('button[type="submit"]').click();

    // EXPECTATION after implementation fix:
    // - the same form is re-rendered with an error message (bootstrap alert)
    // - inputs preserve the values that were submitted
    const errorAlert = page.locator('.alert.alert-danger');
    await expect(errorAlert, 'Form should display an error alert on duplicate').toBeVisible();

    // Check persisted values
    await expect(page.locator('input[name="name"]')).toHaveValue(eventName);
    await expect(page.locator('input[name="datetime_start"]')).toHaveValue(startLocal);
    // end is optional but should be kept when provided
    await expect(page.locator('input[name="datetime_end"]')).toHaveValue(endLocal);
    await expect(page.locator('input[name="short_description"]')).toHaveValue('Quick create from Playwright');
    await expect(page.locator('textarea[name="long_description"]')).toHaveValue('Detailed description for E2E test.');
  });
});
