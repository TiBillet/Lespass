import {expect, test} from '@playwright/test'
import {getRootJWT} from '../mesModules/commun.js'

const email = process.env.TEST_MAIL
let tokenBilletterie

test.describe.skip('Peuplement initial de la db "billetterie".', () => {
  test('Ajouter "don".', async () => {
    tokenBilletterie = await getRootJWT()
    console.log('tokenBilletterie =', tokenBilletterie)

    // réservation gratuite, type d'article = "F"

  })
})