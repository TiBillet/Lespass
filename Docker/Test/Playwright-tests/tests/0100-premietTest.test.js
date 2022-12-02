import {expect, test} from '@playwright/test'
import * as dotenv from 'dotenv'

dotenv.config('../.env')

test.use({viewport: {width: 1400, height: 1300}})

let page
const email = process.env.EMAIL
const urlTester = 'https://raffinerie.django-local.org'

test.describe('Route iframeevent.', () => {
  test('Formulaire réservation puis stripe.', async ({browser}) => {
    // 1 - connexion appareil client
    page = await browser.newPage()

    // ignore certificat https privé
    const context = await browser.newContext({ignoreHTTPSErrors: true})

    // première connexion
    await page.goto(urlTester)

    // tester iframeevent, récupérer le premier évènement et remplacer dans son href "event" par "iframeevent"
    await page.evaluate(() => {
      const ele = (document.querySelectorAll('.test-card-event-container')[0]).querySelector('.test-card-event .card-body a')
      let href = ele.href
      ele.href = href.replace('event', 'iframeevent')
    })

    // aller à l'évènement
    await Promise.all([
      page.waitForResponse('https://raffinerie.django-local.org/iframeevent/**'),
      page.locator('.test-card-event-container').first().locator('.test-card-event .card-body a').click()
    ])

    const firstReservation = page.locator('.test-card-billet section ').first()

    // ajouter une réservation au premier tarif
    await firstReservation.locator('.test-card-billet-bt-add').click()

    // input nom = 'Durand'
    await firstReservation.locator('.test-card-billet-input-group .test-card-billet-input-group-nom').fill('Durand')

    // input prénom = 'Jean'
    await firstReservation.locator('.test-card-billet-input-group .test-card-billet-input-group-prenom').fill('Jean')

    // profil-email
    await page.locator('#profil-email').fill(email)

    // profil-confirme-email
    await page.locator('#profil-confirme-email').fill(email)

    // valider formulaire
    await Promise.all([
      //   // It is important to call waitForNavigation before click to set up waiting.
      page.waitForNavigation(),
      // Triggers a navigation with a script redirect.
      page.locator('button[type="submit"]', {hasText: 'Valider la réservation'}).click()
    ])

    // attente stripe
    // await page.waitForLoadState('networkidle')
    await page.locator('#root', {hasText: 'Pay with card'})

    // remplissage 4242 du formulaire stripe
    await page.locator('form fieldset input[placeholder="1234 1234 1234 1234"]').fill('4242 4242 4242 4242')
    await page.locator('form fieldset input[placeholder="MM / YY"]').fill('42 / 42')
    await page.locator('form fieldset input[placeholder="CVC"]').fill('424')
    await page.locator('form #billingName').fill('4242')
    await page.locator('form div[class="SubmitButton-IconContainer"]').click()

  })

  test('Retour formulaire stripe', async ({browser}) => {
    await page.waitForNavigation()
    // attend l'affichage d'un modal
    await expect(page.locator('body[class="modal-open"]')).toBeVisible()

    // vérifier le succès
    await expect(page.locator('#exampleModalLabel')).toHaveText('Succès')
    await expect(page.locator('.modal-body', {hasText: 'Paiement validé.'})).toBeVisible()

    // sortir du modal
    await page.locator('.modal-footer-bt-fermer').click()

    await expect(page.locator('.page-header .container', {hasText: 'Raffinerie'})).toBeVisible()

    await page.close()
  })

})