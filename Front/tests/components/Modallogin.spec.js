const {test, expect} = require('@playwright/test')

// configuration
test.use({
  headless: false,
  viewport: {width: 1280, height: 720},
  ignoreHTTPSErrors: true,
})


/*
// Click [placeholder="Email"]
  await page.locator('[placeholder="Email"]').click();
  // Fill [placeholder="Email"]
  await page.locator('[placeholder="Email"]').fill('t');
  // Double click [placeholder="Email"]
  await page.locator('[placeholder="Email"]').dblclick();
  // Click [placeholder="Email"]
  await page.locator('[placeholder="Email"]').click();
  // Fill [placeholder="Email"]
  await page.locator('[placeholder="Email"]').fill('');
  // Double click [placeholder="Email"]
  await page.locator('[placeholder="Email"]').dblclick();
  // Fill [placeholder="Email"]
  await page.locator('[placeholder="Email"]').fill('dijouxnicolas@sfr.fr');
  // Click text=Valider
  await page.locator('text=Valider').click();
  // Click text=Validation×
  await page.locator('text=Validation×').click();
  // Click div:has-text("Pour acceder à votre espace et réservations, merci de valider votre adresse emai") >> nth=4
  await page.locator('div:has-text("Pour acceder à votre espace et réservations, merci de valider votre adresse emai")').nth(4).click();
  // Click #conteneur-message-modal-body div:has-text("Close") >> nth=1
  await page.locator('#conteneur-message-modal-body div:has-text("Close")').nth(1).click();
  // Click #conteneur-message-modal-body >> text=Close
  await page.locator('#conteneur-message-modal-body >> text=Close').click();
 */
test.describe('Modallogin.vue', () => {
  test.beforeEach(async ({page}) => {
    // Go to the starting url before each test.
    await page.goto('https://raffinerie.django-local.org/')

    // clique sur bouton "Se connecter"
    await page.locator('h6[data-test-id="seConnecter"]').click()

    // attente modal
    const modalLogin = await page.locator('#modal-form-login')

    // modal doit être visible
    await expect(modalLogin).toBeVisible()
  })

  test('Email sans @ et sans .', async ({page, browser, browserName}) => {
    // peuple le input email
    await page.locator('[placeholder="Email"]').click()
    await page.locator('[placeholder="Email"]').fill('testEmail')

    // Click text=Valider
    await page.locator('text=Valider').click()

    // copie d'écran
    await page.screenshot({path: `tests/components/modalLoginEmailSansArobaseEtSansPoint-${browserName}.png`})
    await page.pause()
  })

})