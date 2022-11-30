import {expect, test} from '@playwright/test'
import * as dotenv from 'dotenv'

dotenv.config('../.env')

const email = process.env.TEST_MAIL
let tokenBilletterie

test.describe('Api pop db.', () => {


  test('GeT Root JWT Token', async ({request}) => {
    const response = await request.post(process.env.URL_ROOT + '/api/user/token/', {
      headers: {
        "Content-Type": "application/json"
      },
      data: {
        username: process.env.EMAIL_ROOT,
        password: process.env.PASSWORD_ROOT
      }
    })

    const retour = await response.json()
    tokenBilletterie = retour.access
    expect(response.ok()).toBeTruthy()
  })

  test('Place rafftou create', async ({request}) => {
    const response = await request.post(process.env.URL_META + '/api/place/', {
      headers: {
        "Content-Type": "application/json",
        Authorization: 'Bearer ' + tokenBilletterie
      },
      data: {
        organisation: "Raffinerie",
        short_description: "Tiers-lieux eco-culturel du Billetistan",
        long_description: "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
        phone: "0692929292",
        email: process.env.EMAIL,
        site_web: "https://laraffinerie.re/",
        postal_code: "97410",
        img_url: "https://picsum.photos/1920/1080.jpg",
        logo_url: "https://picsum.photos/300/300.jpg",
        categorie: "S",
        stripe_connect_account: process.env.ID_STRIPE
      }
    })
    expect(response.ok()).toBeTruthy()
    console.log('response =', response)
  })

  // créer un artist (POST Artist .... Create)
  // créer un produit (POST Product .... Create)
  // créer 2 prix pour le produit (POST Prices .... Create)
  // créer un évènement (POST Events Create with OPT ART)

})
