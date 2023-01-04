import {expect, test} from '@playwright/test'
import {getRootJWT, randomDate, initData, getData, updateData} from '../mesModules/commun.js'
// commun.js avant dataPeuplementInit.json, pour les variables d'environnement

const email = process.env.TEST_MAIL
let tokenBilletterie


test.describe('Peuplement initial de la db "billetterie".', () => {
  test('Get root token', async ({request}) => {
    tokenBilletterie = await getRootJWT()
    console.log('tokenBilletterie =', tokenBilletterie)

  })

  test('initData', async ({request}) => {
    // ne faire qu'une fois si l'on veut garder en état le cheminement des tests
    await initData()
  })

  test('Create places', async ({request}) => {
    const dataDb = getData()
    let response
    const places = dataDb.filter(obj => obj.typeData === 'place')
    for (const placeR of places) {
      // ajout, donc modification
      placeR.value['stripe_connect_account'] = process.env.ID_STRIPE
      console.log('Création du lieu ', placeR.value.organisation)
      response = await request.post(process.env.URL_META + '/api/place/', {
        headers: {
          "Content-Type": "application/json"
        },
        data: placeR.value
      })
      expect(response.ok()).toBeTruthy()
    }
    // maj pour garder le state db dans les prochains tests
    updateData(dataDb)
  })

  test('Create artist', async ({request}) => {
    const dataDb = getData()
    let response
    const artists = dataDb.filter(obj => obj.typeData === 'artist')
    for (const artistR of artists) {
      artistR.value['stripe_connect_account'] = process.env.ID_STRIPE
      console.log('Création artiste', artistR.value.organisation)
      response = await request.post(process.env.URL_META + '/api/artist/', {
        headers: {
          "Content-Type": "application/json"
        },
        data: artistR.value
      })
      expect(response.ok()).toBeTruthy()
      const retour = await response.json()
      // console.log('retour artist =', retour)
      // mémorise le uuid de l'artiste 'Ziskakan'
      artistR.value['uuid'] = retour.uuid
    }
    updateData(dataDb)
  })

  test('Create product', async ({request}) => {
    const dataDb = getData()
    let response
    const products = dataDb.filter(obj => obj.typeData === 'product')
    for (const productR of products) {
      console.log('Création produit', productR.value.name)
      const url = `https://${productR.place}.${process.env.DOMAIN}/api/products/`
      response = await request.post(url, {
        headers: {
          "Content-Type": "application/json",
          Authorization: 'Bearer ' + tokenBilletterie
        },
        data: productR.value
      })
      expect(response.ok()).toBeTruthy()
      const retour = await response.json()
      // mémorise le uuid du produit
      productR.value['uuid'] = retour.uuid
    }
    updateData(dataDb)
  })

  test('Create price', async ({request}) => {
    const dataDb = getData()
    let response
    const products = dataDb.filter(obj => obj.typeData === 'product')
    const prices = dataDb.filter(obj => obj.typeData === 'price')
    for (const priceR of prices) {
      console.log('Création du prix', priceR.value.name)
      const url = `https://${priceR.place}.${process.env.DOMAIN}/api/prices/`
      const uuidProduct = products.find(obj => obj.value.name === priceR.productName).value.uuid
      priceR.value['product'] = uuidProduct
      // console.log('url =', url)
      // console.log('priceR =', priceR)
      response = await request.post(url, {
        headers: {
          "Content-Type": "application/json",
          Authorization: 'Bearer ' + tokenBilletterie
        },
        data: priceR.value
      })
      expect(response.ok()).toBeTruthy()
    }
    updateData(dataDb)
    // TODO: + adhesion_obligatoire
  })


  test('Events Create with OPT ART - Ziskakan', async ({request}) => {
    const dataDb = getData()
    let response
    const artists = dataDb.filter(obj => obj.typeData === 'artist')
    const products = dataDb.filter(obj => obj.typeData === 'product')
    const events = dataDb.filter(obj => obj.typeData === 'event')
    for (const eventR of events) {
      console.log("Création d'un évènement.")
      const url = `https://${eventR.place}.${process.env.DOMAIN}/api/events/`
      console.log('url =', url)
      // init
      let dataEvent = {
        datetime: randomDate(),
        short_description: eventR.short_description,
        long_description: eventR.long_description,
      }

      // les artistes
      dataEvent['artists'] = []
      for (const artist of eventR.artists) {
        // console.log('artist =', artist)
        const uuidArtist = artists.find(obj => obj.value.organisation === artist).value.uuid
        const datetime = randomDate()
        dataEvent.artists.push({
          uuid: uuidArtist,
          datetime
        })
      }

      // les produits
      dataEvent['products'] = []
      for (const product of eventR.products) {
        // console.log('product =', product)
        const uuidProduct = products.find(obj => obj.value.name === product).value.uuid
        dataEvent.products.push(uuidProduct)
      }

      // TODO: options_checkbox
      dataEvent['options_checkbox'] = []
      // TODO: options_radio
      dataEvent['options_radio'] = []

      dataEvent['stripe_connect_account'] = process.env.ID_STRIPE

      // console.log('dataEvent =', dataEvent)

      response = await request.post(url, {
        headers: {
          "Content-Type": "application/json",
          Authorization: 'Bearer ' + tokenBilletterie
        },
        data: dataEvent
      })
      expect(response.ok()).toBeTruthy()
    }
  })

})
