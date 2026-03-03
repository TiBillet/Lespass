import { test, expect } from '@playwright/test';
import { createEvent, createProduct } from './utils/api';

/**
 * TEST: Numeric overflow validation on free price fields
 * TEST : Validation du dépassement numérique sur les champs prix libre
 *
 * Reproduces Sentry issue #7271957907: a user entered 145000 as custom amount,
 * causing a PostgreSQL numeric overflow (max_digits=8, scale=2 → max 999999.99).
 *
 * Reproduit le bug Sentry #7271957907 : un utilisateur a saisi 145000 comme montant,
 * provoquant un overflow numérique PostgreSQL.
 *
 * We verify that:
 * On vérifie que :
 * 1. The HTML input has a max attribute / L'input HTML a un attribut max
 * 2. An oversized amount is rejected client-side / Un montant trop grand est rejeté côté client
 * 3. Same checks on booking form / Mêmes vérifications sur le formulaire de réservation
 */

function generateRandomId() {
  return Math.random().toString(36).substring(2, 10);
}

function slugifyName(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

test.describe('Numeric overflow validation / Validation dépassement numérique', () => {

  test('membership: should reject oversized custom amount / adhésion : doit rejeter un montant trop élevé', async ({ page }) => {
    const userEmail = `jturbeaux+overflow${generateRandomId()}@pm.me`;

    // Étape 1 : Aller sur la page des adhésions
    // Step 1: Navigate to the memberships page
    await test.step('Navigate to memberships / Aller sur les adhésions', async () => {
      await page.goto('/memberships/');
      await page.waitForLoadState('domcontentloaded');
    });

    // Étape 2 : Ouvrir le premier panneau d'adhésion disponible
    // Step 2: Open the first available membership panel
    await test.step('Open membership panel / Ouvrir le panneau adhésion', async () => {
      // Cliquer sur le premier bouton "Adhérer" / Click the first "Subscribe" button
      const openButton = page.locator('[data-testid^="membership-open-"]').first();
      await openButton.click();
      // Attendre que le formulaire soit visible / Wait for form to be visible
      const membershipForm = page.locator('[data-testid="membership-form"], #membership-form').first();
      await expect(membershipForm).toBeVisible({ timeout: 5000 });

      // Si plusieurs prix : sélectionner le radio prix libre pour afficher le container
      // If multiple prices: select the free price radio to show the container
      const freePriceRadio = page.locator('input.free-price-radio').first();
      if (await freePriceRadio.isVisible()) {
        await freePriceRadio.click();
        await page.waitForTimeout(300);
      }
    });

    // Étape 3 : Vérifier que l'input prix libre a un attribut max
    // Step 3: Check that the free price input has a max attribute
    await test.step('Check max attribute / Vérifier attribut max', async () => {
      // L'input peut être dans un container visible (un seul prix) ou rendu visible par le radio
      // The input may be in a visible container (single price) or made visible by the radio
      const customAmountInput = page.locator('input[name^="custom_amount_"]:visible').first();
      await expect(customAmountInput).toBeVisible({ timeout: 5000 });
      const maxValue = await customAmountInput.getAttribute('max');
      expect(maxValue).toBeTruthy();
      expect(parseFloat(maxValue!)).toBeLessThanOrEqual(999999.99);
      console.log(`✓ Input has max="${maxValue}"`);
    });

    // Étape 4 : Saisir un montant excessif et vérifier le rejet
    // Step 4: Enter an oversized amount and verify rejection
    await test.step('Submit oversized amount / Soumettre montant trop élevé', async () => {
      const customAmountInput = page.locator('input[name^="custom_amount_"]:visible').first();
      // Saisir un montant absurde comme dans le bug original (145000)
      // Enter an absurd amount like in the original bug (145000)
      await customAmountInput.click();
      await customAmountInput.fill('999999999999999');

      // Remplir les champs obligatoires / Fill required fields
      await page.getByTestId('membership-email').fill(userEmail);
      await page.getByTestId('membership-email').press('Tab');
      await page.getByTestId('membership-email-confirm').fill(userEmail);
      await page.getByTestId('membership-email-confirm').press('Tab');
      await page.getByTestId('membership-firstname').fill('Overflow');
      await page.getByTestId('membership-firstname').press('Tab');
      await page.getByTestId('membership-lastname').fill('Test');

      // Cocher acknowledge si visible / Check acknowledge if visible
      const acknowledgeInput = page.locator('[data-testid="membership-acknowledge"], #acknowledge').first();
      if (await acknowledgeInput.isVisible()) {
        await acknowledgeInput.check();
      }

      // Soumettre / Submit
      await page.getByTestId('membership-submit').click();

      // Le navigateur doit bloquer via la validation HTML (attribut max)
      // ou la validation JS doit ajouter is-invalid
      // Browser should block via HTML validation (max attribute)
      // or JS validation should add is-invalid
      const isHtmlValid = await customAmountInput.evaluate(
        (el) => (el as HTMLInputElement).validity.valid
      );
      const hasInvalidClass = await customAmountInput.evaluate(
        (el) => el.classList.contains('is-invalid')
      );

      // Au moins une des deux validations doit rejeter le montant
      // At least one validation must reject the amount
      const isRejected = !isHtmlValid || hasInvalidClass;
      expect(isRejected).toBeTruthy();
      console.log(`✓ Oversized amount rejected (htmlValid=${isHtmlValid}, hasInvalidClass=${hasInvalidClass})`);

      // Vérifier qu'on n'a PAS été redirigé vers Stripe
      // Verify we were NOT redirected to Stripe
      expect(page.url()).not.toContain('stripe.com');
      console.log('✓ No Stripe redirect / Pas de redirection Stripe');
    });

    // Étape 5 : Vérifier qu'un montant valide passe la validation HTML
    // Step 5: Verify a valid amount passes HTML validation
    await test.step('Valid amount is accepted / Montant valide accepté', async () => {
      const customAmountInput = page.locator('input[name^="custom_amount_"]:visible').first();
      await customAmountInput.fill('15');

      const isHtmlValid = await customAmountInput.evaluate(
        (el) => (el as HTMLInputElement).validity.valid
      );
      expect(isHtmlValid).toBeTruthy();
      console.log('✓ Valid amount (15€) passes HTML validation');
    });
  });

  test('booking: should reject oversized custom amount / réservation : doit rejeter un montant trop élevé', async ({ page }) => {
    const randomId = generateRandomId();
    const eventName = `Event Overflow ${randomId}`;
    const productName = `Billet Overflow ${randomId}`;
    const priceName = 'Entrée Libre Overflow';

    let eventSlug = slugifyName(eventName);

    // Étape 1 : Créer un événement avec un prix libre
    // Step 1: Create an event with a free price
    await test.step('Create event with free price / Créer événement prix libre', async () => {
      const startDate = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();

      const eventResponse = await createEvent({
        request: page.request,
        name: eventName,
        startDate,
      });
      expect(eventResponse.ok).toBeTruthy();
      eventSlug = eventResponse.slug || eventSlug;

      const productResponse = await createProduct({
        request: page.request,
        name: productName,
        description: 'Produit pour tester overflow réservation.',
        category: 'Ticket booking',
        eventUuid: eventResponse.uuid,
        offers: [
          {
            name: priceName,
            price: '1.00',
            freePrice: true,
          },
        ],
      });
      expect(productResponse.ok).toBeTruthy();
    });

    // Étape 2 : Aller sur la page de l'événement et ouvrir le panneau de réservation
    // Step 2: Go to event page and open booking panel
    await test.step('Open booking form / Ouvrir le formulaire', async () => {
      await page.goto(`/event/${eventSlug}/`);
      await page.waitForLoadState('domcontentloaded');
      await page.getByTestId('booking-open-panel').click();
      await page.waitForTimeout(500);
    });

    // Étape 3 : Incrémenter la quantité pour afficher le champ prix libre
    // Step 3: Increment quantity to reveal the free price field
    await test.step('Increment quantity and check max / Incrémenter quantité et vérifier max', async () => {
      // Cliquer sur le bouton "+" du bs-counter comme dans le script enregistré
      // Click the "+" button of bs-counter as in the recorded script
      const counter = page.locator('bs-counter.js-order-amount').first();
      await expect(counter).toBeVisible();
      // Le bouton + est le dernier bouton dans le bs-counter
      // The + button is the last button in the bs-counter
      const incrementButton = counter.getByRole('button').last();
      await incrementButton.click();
      await page.waitForTimeout(300);

      // Le container prix libre doit maintenant être visible
      // The free price container should now be visible
      const customAmountInput = page.locator('.js-order-custom-price').first();
      await expect(customAmountInput).toBeVisible({ timeout: 5000 });

      // Vérifier l'attribut max / Check max attribute
      const maxValue = await customAmountInput.getAttribute('max');
      expect(maxValue).toBeTruthy();
      expect(parseFloat(maxValue!)).toBeLessThanOrEqual(999999.99);
      console.log(`✓ Booking input has max="${maxValue}"`);
    });

    // Étape 4 : Saisir un montant excessif et vérifier le rejet
    // Step 4: Enter an oversized amount and verify rejection
    await test.step('Submit oversized booking amount / Soumettre montant réservation trop élevé', async () => {
      const customAmountInput = page.locator('.js-order-custom-price').first();
      await customAmountInput.click();
      await customAmountInput.fill('9999999999');

      // Le navigateur doit invalider via l'attribut max
      // Browser should invalidate via max attribute
      const isHtmlValid = await customAmountInput.evaluate(
        (el) => (el as HTMLInputElement).validity.valid
      );
      expect(isHtmlValid).toBeFalsy();
      console.log(`✓ Booking oversized amount rejected by HTML validation (valid=${isHtmlValid})`);
    });
  });

});
