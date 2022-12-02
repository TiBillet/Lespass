import {expect, test} from '@playwright/test'
import * as dotenv from 'dotenv'
import moment from 'moment'

function randomDate() {
  const dateR = moment()
  const randomNbDays = (Math.random() * 365) + 1
  dateR.add(randomNbDays, 'days')
  dateR.format("YYYY-MM-DD")
  return dateR
}

dotenv.config('../.env')

const email = process.env.TEST_MAIL
let tokenBilletterie, uuidS = []

test.describe.skip('Api pop db.', () => {
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
        "Content-Type": "application/json"
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
  })

  test('Artist Ziskakan create', async ({request}) => {
    const response = await request.post(process.env.URL_META + '/api/artist/', {
      headers: {
        "Content-Type": "application/json"
      },
      data: {
        organisation: "Ziskakan",
        short_description: "40 ans de Maloya Rock !",
        long_description: "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.",
        phone: "0692929292",
        email: "jturbeaux+ziz@pm.me",
        site_web: "https://www.ziskakan.re",
        postal_code: "97410",
        img_url: "https://lespas.re/wp-content/uploads/2021/06/Ziskakan-%C2%A9Pierre-Yves-Babelon-lespas-1-1200x1200.jpg",
        logo_url: "https://lespas.re/wp-content/uploads/2021/06/Ziskakan-%C2%A9Pierre-Yves-Babelon-lespas-1-1200x1200.jpg",
        categorie: "A",
        stripe_connect_account: process.env.ID_STRIPE
      }
    })
    expect(response.ok()).toBeTruthy()
    const retour = await response.json()
    // console.log('retour artist =', retour)
    // mémorise le uuid de l'artiste 'Ziskakan'
    uuidS.push({name: 'Ziskakan', uuid: retour.uuid})
  })

  test('Artist Balaphonik create', async ({request}) => {
    const response = await request.post(process.env.URL_META + '/api/artist/', {
      headers: {
        "Content-Type": "application/json"
      },
      data: {
        organisation: "Balaphonik Sound System",
        short_description: "Balaphonik Sound System fait danser les corps, ressource et rafraîchit les esprits.",
        long_description: "Multi-instrumentiste, Alex a participé à des projets musicaux variés. Usant tous les genres, du métal au gnawa et du reggae au hiphop, il étudie le rythme sous toutes ses formes, à travers ses rencontres et ses voyages.",
        phone: "0692929292",
        email: "jturbeaux+ziz@pm.me",
        site_web: "https://balaphonik.wixsite.com/balaphonik",
        postal_code: "97410",
        img_url: "https://www.festival-arbre-creux.fr/wp-content/uploads/2019/05/balaphonik-3.jpg",
        logo_url: "https://i.ytimg.com/vi/HkRYJg7dnNM/hqdefault.jpg",
        categorie: "A",
        stripe_connect_account: process.env.ID_STRIPE
      }
    })
    expect(response.ok()).toBeTruthy()
    const retour = await response.json()
    uuidS.push({name: 'Balaphonik', uuid: retour.uuid})
  })

  test('Product Billet Create', async ({request}) => {
    const url = 'https://' + process.env.SLUG_PLACE_RAFFINERIE + '.' + process.env.DOMAIN + '/api/products/'
    // console.log('url =', url)
    const response = await request.post(url, {
      headers: {
        "Content-Type": "application/json",
        Authorization: 'Bearer ' + tokenBilletterie
      },
      data: {
        name: "Billet",
        publish: true,
        img_url: "https://picsum.photos/600/400.jpg",
        categorie_article: "B",
        stripe_connect_account: process.env.ID_STRIPE
      }
    })
    expect(response.ok()).toBeTruthy()
    const retour = await response.json()
    // mémorise le uuid du produit 'Billet'
    uuidS.push({name: 'Billet', uuid: retour.uuid})
    // console.log('uuidS =', uuidS)
  })

  test('Prices Billet demi tarif Create', async ({request}) => {
    const url = 'https://' + process.env.SLUG_PLACE_RAFFINERIE + '.' + process.env.DOMAIN + '/api/prices/'
    const uuid = uuidS.find(product => product.name === 'Billet').uuid
    const response = await request.post(url, {
      headers: {
        "Content-Type": "application/json",
        Authorization: 'Bearer ' + tokenBilletterie
      },
      data: {
        name: "Demi Tarif",
        prix: "5",
        vat: "NA",
        max_per_user: "10",
        stock: "10",
        product: uuid,
        stripe_connect_account: process.env.ID_STRIPE
      }
    })
    expect(response.ok()).toBeTruthy()
  })

  test('Prices Billet plein tarif Create', async ({request}) => {
    const url = 'https://' + process.env.SLUG_PLACE_RAFFINERIE + '.' + process.env.DOMAIN + '/api/prices/'
    const uuid = uuidS.find(product => product.name === 'Billet').uuid
    const response = await request.post(url, {
      headers: {
        "Content-Type": "application/json",
        Authorization: 'Bearer ' + tokenBilletterie
      },
      data: {
        name: "Plein Tarif",
        prix: "10",
        vat: "NA",
        max_per_user: "10",
        stock: "10",
        product: uuid,
        stripe_connect_account: process.env.ID_STRIPE
      }
    })
    expect(response.ok()).toBeTruthy()
  })


  // Ziskakan
  test('Events Create with OPT ART - Ziskakan', async ({request}) => {
    const url = 'https://' + process.env.SLUG_PLACE_RAFFINERIE + '.' + process.env.DOMAIN + '/api/events/'
    const uuidArtist = uuidS.find(product => product.name === 'Ziskakan').uuid
    const uuidBillet = uuidS.find(product => product.name === 'Billet').uuid
    const response = await request.post(url, {
      headers: {
        "Content-Type": "application/json",
        Authorization: 'Bearer ' + tokenBilletterie
      },
      data: {
        datetime: randomDate(),
        short_description: "description courte",
        long_description: "Ceci est une longue description",
        artists: [
          {
            uuid: uuidArtist,
            datetime: randomDate()
          }
        ],
        products: [
          uuidBillet
        ],
        options_checkbox: [],
        options_radio: [],
        stripe_connect_account: process.env.ID_STRIPE
      }
    })
    expect(response.ok()).toBeTruthy()
    // console.log('response =', response)
  })

  // Balaphonik
  test('Events Create with OPT ART - Balaphonik', async ({request}) => {
    const url = 'https://' + process.env.SLUG_PLACE_RAFFINERIE + '.' + process.env.DOMAIN + '/api/events/'
    const uuidArtist = uuidS.find(product => product.name === 'Balaphonik').uuid
    const uuidBillet = uuidS.find(product => product.name === 'Billet').uuid
    const response = await request.post(url, {
      headers: {
        "Content-Type": "application/json",
        Authorization: 'Bearer ' + tokenBilletterie
      },
      data: {
        datetime: randomDate(),
        short_description: "description courte de Balaphonik",
        long_description: "Ceci est une longue description e Balaphonik",
        artists: [
          {
            uuid: uuidArtist,
            datetime: randomDate()
          }
        ],
        products: [
          uuidBillet
        ],
        options_checkbox: [],
        options_radio: [],
        stripe_connect_account: process.env.ID_STRIPE
      }
    })
    expect(response.ok()).toBeTruthy()
    // console.log('response =', response)
  })

})
