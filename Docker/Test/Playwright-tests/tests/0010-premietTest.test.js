import {test} from '@playwright/test'

test.use({viewport: {width: 1400, height: 1300}})

let page
const urlTester = 'https://raffinerie.django-local.org/iframeevent/ziskakan-072625-1830/'

test.describe('Acceuil.', () => {
  test('Retour stripe.', async ({browser}) => {
    // 1 - connexion appareil client
    page = await browser.newPage()

    // ignore certificat https privé
    const context = await browser.newContext({ignoreHTTPSErrors: true})

    // première connexion
    await page.goto(urlTester)

    await page.pause()

     const reservation = 'demi tarif : 5 €'

    // ajouter une réservation à l'article "gratuite"
    await page.locator('.test-card-billet div section', {hasText: reservation}).locator('div button').click()

    // input nom = 'Durand'
    await page.locator('.test-card-billet div section', {hasText: reservation}).locator('.test-card-billet-input-group .test-card-billet-input-group-nom').fill('Durand')

    // input prénom = 'Jean'
    await page.locator('.test-card-billet div section', {hasText: reservation}).locator('.test-card-billet-input-group .test-card-billet-input-group-prenom').fill('Jean')

    // profil-email
    await page.locator('#profil-email').fill('filaos974@hotmail.com')

    // profil-confirme-email
    await page.locator('#profil-confirme-email').fill('filaos974@hotmail.com')

    // vérifier data du post

    // valider formulaire
    await page.locator('button[type="submit"]', {hasText: 'Valider la réservation'}).click()

  })

  test('Fin.', async ({browser}) => {
    await page.pause()
    await page.close()
  })
})
