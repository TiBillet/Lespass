import { test, expect, Page } from '@playwright/test';
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
 * TEST: Create event via the UNIFIED wizard + duplicate handling
 * TEST : Creation d'event via le wizard UNIFIE + gestion des doublons
 *
 * L'ancien flow "quick create" (offcanvas /event/simple_add_event/) a ete
 * remplace par le wizard unifie /event/wizard/ (CHANTIER-03) :
 *   - Etape 1 (place) : choix d'une adresse existante ou creation d'un lieu.
 *   - Etape 2 (event) : ajout de brouillons (HTMX) puis finalisation.
 * / The old offcanvas quick-create flow was replaced by the unified wizard.
 */

// Remplit le wizard de bout en bout (etape lieu + etape event) puis clique
// sur "Creer les evenements" et renvoie le statut HTTP du POST de finalisation.
// / Walk the wizard end to end (place + event steps), click finalize and
// return the HTTP status of the finalize POST.
async function walkWizardAndFinalize(page: Page, eventName: string, startLocal: string) {
  // Etape 1 : choisir la premiere adresse existante.
  // / Step 1: pick the first existing address.
  await page.goto('/event/wizard/place/');
  await page.waitForLoadState('domcontentloaded');
  const firstAddress = page.locator('[data-testid="wizard-place-radio"]').first();
  await expect(firstAddress).toBeAttached();
  await firstAddress.check();
  const continueBtn = page.locator('[data-testid="wizard-place-submit"]');
  await expect(continueBtn).toBeEnabled();
  await continueBtn.click();

  // Etape 2 : ajouter un brouillon (HTMX) puis finaliser.
  // / Step 2: add a draft (HTMX) then finalize.
  await page.waitForURL('**/event/wizard/event/**');
  await page.locator('[data-testid="wizard-event-name"]').fill(eventName);
  await page.locator('[data-testid="wizard-event-datetime"]').fill(startLocal);
  await page.locator('[data-testid="wizard-event-description"]').fill('Detailed description for E2E test.');
  await page.locator('[data-testid="wizard-event-add"]').click();
  // Le brouillon apparait dans la liste (swap HTMX).
  // / The draft shows up in the list (HTMX swap).
  await expect(page.locator('[data-testid="wizard-event-0"]')).toBeVisible();
  await expect(page.locator('[data-testid="wizard-event-0"]')).toContainText(eventName);

  // Finalisation : POST plein page. On capture le statut de la reponse pour
  // detecter un eventuel crash serveur (500) sur les doublons.
  // / Finalize: full-page POST. Capture the response status to detect a
  // potential server crash (500) on duplicates.
  const [finalizeResponse] = await Promise.all([
    page.waitForResponse(
      resp => resp.url().includes('/event/wizard/event/') && resp.request().method() === 'POST',
    ),
    page.locator('[data-testid="wizard-events-finalize"]').click(),
  ]);
  return finalizeResponse.status();
}

test.describe('Event wizard - create and duplicate handling', () => {
  test('create event via unified wizard / creer un event via le wizard unifie', async ({ page }) => {
    // 1) Auth en admin (droits de creation d'event).
    // / Auth as admin (event creation rights).
    await loginAsAdmin(page);

    const eventName = `Playwright Wizard EVT ${Date.now()}`;
    const startLocal = isoLocalFuture(5, 10, 0);

    await test.step('Wizard entry visible on agenda / Bouton wizard visible sur l agenda', async () => {
      await page.goto('/event/');
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator('[data-testid="btn-event-add"]')).toBeVisible();
    });

    await test.step('Create event via wizard / Creer l event via le wizard', async () => {
      const status = await walkWizardAndFinalize(page, eventName, startLocal);
      expect(status, 'Finalize should not crash').toBeLessThan(500);
      // Un seul event -> redirection vers sa page de detail.
      // / Single event -> redirect to its detail page.
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator('body')).toContainText(eventName);
    });

    await test.step('Event visible on agenda / Event visible sur l agenda', async () => {
      await page.goto('/event/');
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator('#event_list')).toContainText(eventName);
    });
  });

  // BUG CORRIGE (2026-06-11) : la finalisation du wizard gere desormais le
  // doublon (meme nom + meme datetime) : `EventWizard.step2_event` enveloppe
  // la creation dans transaction.atomic() et attrape l'IntegrityError de
  // unique_together('name','datetime') → message warning + retour a l'etape
  // des brouillons (conserves en session), rien n'est cree (tout ou rien).
  // / FIXED BUG (2026-06-11): the wizard finalize now handles duplicates
  // (same name + datetime): step2_event wraps creation in transaction.atomic()
  // and catches the IntegrityError → warning message + back to the drafts
  // step (kept in session), nothing created (all-or-nothing).
  test('duplicate event should show an error, not a 500 / un doublon doit afficher une erreur, pas une 500', async ({ page }) => {
    await loginAsAdmin(page);

    const eventName = `Playwright Wizard DUP ${Date.now()}`;
    const startLocal = isoLocalFuture(6, 10, 0);

    // Premiere creation : OK.
    // / First creation: OK.
    const firstStatus = await walkWizardAndFinalize(page, eventName, startLocal);
    expect(firstStatus).toBeLessThan(500);

    // Doublon : meme nom + meme datetime. Le serveur doit repondre sans
    // crasher (erreur de formulaire ou message), PAS une 500.
    // / Duplicate: same name + datetime. The server must answer without
    // crashing (form error or message), NOT a 500.
    const duplicateStatus = await walkWizardAndFinalize(page, eventName, startLocal);
    expect(duplicateStatus, 'Duplicate finalize must not return a server error').toBeLessThan(500);
  });
});
