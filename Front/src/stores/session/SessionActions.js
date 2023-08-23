import { log } from '../../communs/LogError'
import * as CryptoJS from 'crypto-js'
import { setLocalStateKey, getLocalStateKey, resetLocalState } from '../../communs/storeLocal'

const domain = `${window.location.protocol}//${window.location.host}`

export const sessionActions = {
  disconnect () {
    // console.log('-> disconnect')
    this.me = {
      cashless: {},
      reservations: [],
      membership: [],
      email: ''
    }
    this.accessToken = ''
    this.forms = []
    resetLocalState('refreshToken', '')
    this.router.push('/')
  },
  async getMe () {
    // console.log('-> getMe, accessToken = ', this.accessToken)
    try {
      const apiMe = `/api/user/me/`
      const options = {
        method: 'GET',
        cache: 'no-cache',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.accessToken} `
        }
      }
      this.loading = true
      const response = await fetch(domain + apiMe, options)
      if (response.status === 200) {
        const retour = await response.json()
        // console.log('-> getMe, retour =', retour)
        this.loading = false
        this.me = await retour
      } else {
        throw new Error(`Erreur ${apiMe} !`)
      }
    } catch (error) {
      this.loading = false
      log({ message: 'getMe, /api/user/me/, error:', error })
      emitter.emit('modalMessage', {
        titre: 'Erreur',
        typeMsg: 'danger',
        contenu: `Obtention infos utilisateur, /api/user/me/ : ${error.message}`
      })
      this.me = {
        cashless: {},
        reservations: [],
        membership: [],
        email: ''
      }
    }
  },
  async emailActivation (id, token) {
    // console.log('emailActivation')
    // attention pas de "/" à la fin de "api"
    const api = `/api/user/activate/${id}/${token}`
    try {
      this.loading = true
      const response = await fetch(domain + api, {
        method: 'GET',
        cache: 'no-cache', // *default, no-cache, reload, force-cache, only-if-cached
        headers: {
          'Content-Type': 'application/json'
        }
      })
      if (response.status === 200) {
        const retour = await response.json()
        // console.log('retour =', retour)
        log({ message: 'sessionStore -> emailActivation /api/user/activate/, status = 200', object: retour })
        // message confirmation email
        emitter.emit('modalMessage', {
          titre: 'Succès',
          typeMsg: 'success',
          dynamic: true,
          contenu: '<h3>Utilisateur activé / connecté !</h3>'
        })
        // maj token d'accès
        this.accessToken = retour.access
        // enregistrement en local(long durée) du "refreshToken"
        setLocalStateKey('refreshToken', retour.refresh)
        // actu du profile
        await this.getMe()
        // this.me.email = getLocalStateKey('email')
      } else {
        throw new Error(`Erreur conrfirmation mail !`)
      }
    } catch (error) {
      log({ message: 'emailActivation, /api/user/activate/, error:', error })
      emitter.emit('modalMessage', {
        titre: 'Erreur',
        typeMsg: 'danger',
        contenu: `Activation email : ${error.message}`
      })
      this.accessToken = ''
      this.me = {
        cashless: {},
        reservations: [],
        membership: [],
        email: ''
      }
      localStorage.setItem('TiBillet-refreshToken', '')
    }
    this.loading = false
  },
  async automaticConnection () {
    const refreshToken = getLocalStateKey('refreshToken')
    if (this.accessToken === '' && refreshToken !== undefined && refreshToken !== '') {
      log({ message: '-> automaticConnection' })
      const api = `/api/user/token/refresh/`
      this.loading = true
      try {
        const response = await fetch(domain + api, {
          method: 'POST',
          cache: 'no-cache',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ refresh: refreshToken })
        })
        const retour = await response.json()
        // console.log('retour =', retour)
        if (response.status === 200) {
          this.accessToken = retour.access
          this.getMe()
        }
      } catch (error) {
        log({ message: 'automaticConnection, /api/user/token/refresh/, error:', error })
        emitter.emit('modalMessage', {
          titre: 'Erreur, maj accessToken !',
          contenu: `${domain + api} : ${error.message}`
        })
      }
      this.loading = false
    }
  },
  setIdentitySite (value) {
    this.identitySite = value
  },
  updateEmail (value) {
    this.email = value
  },
  generateUUIDUsingMathRandom () {
    let d = new Date().getTime()//Timestamp
    let d2 = (performance && performance.now && (performance.now() * 1000)) || 0//Time in microseconds since page-load or 0 if unsupported
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      let r = Math.random() * 16//random number between 0 and 16
      if (d > 0) {//Use timestamp until depleted
        r = (d + r) % 16 | 0
        d = Math.floor(d / 16)
      } else {//Use microseconds since page-load if supported
        r = (d2 + r) % 16 | 0
        d2 = Math.floor(d2 / 16)
      }
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16)
    })
  },
  resetEventOptions () {
    let form = this.forms.find(formRec => formRec.uuid === this.currentUuidEventForm)
    form.options_checkbox.forEach((option) => {
      option.checked = false
    })
    document.querySelectorAll('input[name="event-option-radio"]').forEach((ele) => {
      ele.checked = false
    })
    form.optionRadioSelected = ''
  },
  /**
   * Formate les données d'un évènement pour un formulaire
   * @param postEvent
   */
  initFormEvent (postEvent) {
    // console.log('-> initFormEvent')
    this.currentUuidEventForm = postEvent.uuid
    // hash retour + adhésions et sauvegarde dans event (le post et les adhésions ont changés ?)
    const returnString = JSON.stringify(postEvent) + JSON.stringify(this.membershipProducts)
    const hash = CryptoJS.HmacMD5(returnString, 'NODE_18_lts').toString()

    // convert proxy to array
    let forms = JSON.parse(JSON.stringify(this.forms))

    // lévènement actuel existe il dans forms
    let form = forms?.find(formItem => formItem.uuid === postEvent.uuid)

    // console.log('          hash =', hash)
    // console.log('form.eventHash =', form?.eventHash)

    // création ou reset de l'objet form si non existant ou données "postEvent" différentes
    if (form === undefined || form.eventHash !== hash) {
      // enregistrer le hash post
      postEvent.eventHash = hash

      // ajout de la propriété "selected" aux options checkbox
      postEvent.options_checkbox.forEach(option => option['checked'] = false)

      // ajout de la propriété "optionsRadioSelected" à l'évènement
      postEvent.optionRadioSelected = ''

      // ajout de l'adhésion obligatoire d'un prix de produits dans la liste des produits
      let newProducts = []
      postEvent.products.forEach((product) => {
        // ajout de la propriété "activatedGift" à "false" pour le don
        if (product.categorie_article === 'D') {
          product['activatedGift'] = false
        }
        // désactive la recharge carte par défaut et init nombre crédits à 0
        if (product.categorie_article === 'S') {
          product['activated'] = false
          product['qty'] = 1
        }
        newProducts.push(product)
        product.prices.forEach((price) => {
          // ajout de l'adhésion dans la liste de produits de l'évènement
          if (price.adhesion_obligatoire !== null) {

            let newProduct = this.membershipProducts.find(membership => membership.uuid === price.adhesion_obligatoire)
            newProduct['customers'] = [{
              first_name: '',
              last_name: '',
              phone: '',
              postal_code: '',
              uuid: ''
            }]
            // tarif lié à l'adhésion
            newProduct['priceLinkWithMembership'] = { productUuid: product.uuid, priceUuid: price.uuid }
            // adhésion non activée/visible
            newProduct['activated'] = false
            // conditions de l'adhésion
            newProduct['conditionsRead'] = false
            newProduct['optionRadio'] = ''
            // ajout de la propriété "checked" dans "option_generale_checkbox"
            newProduct.option_generale_checkbox.forEach((option) => {
              option['checked'] = false
            })

            newProducts.push(JSON.parse(JSON.stringify(newProduct)))
          }
          if (product.categorie_article !== 'D' && product.categorie_article !== 'S') {
            console.log('ajout du champ first_name / last_name')
            if (product.nominative === true) {
              //price['customers'] = [{ first_name: '', last_name: '', uuid: this.generateUUIDUsingMathRandom() }]
              price['customers'] = []
            } else {
              price['qty'] = 1
            }
          }
        })
      })
      postEvent.products = newProducts
      postEvent['email'] = this.me.email
      postEvent['typeForm'] = 'reservation'

      // le formulaire n'existe pas
      if (form === undefined) {
        forms.push(postEvent)
        this.forms = forms
      } else {
        // le contenu du formulaire est différent
        let newforms = forms.filter((obj) => obj.uuid !== postEvent.uuid)
        newforms.push(postEvent)
        this.forms = newforms
      }
    }
  },
  /**
   * Initialise/charge les données du tenant/lieu (place, membershipProducts)
   * @returns {Promise<void>}
   */
  async loadPlace () {
    // log({ message: '-> loadPlace' })
    let urlImage, urlLogo
    this.loading = true
    this.error = ''
    try {
      const apiLieu = `/api/here/`
      const response = await fetch(domain + apiLieu)
      if (response.status !== 200) {
        throw new Error(`${response.status} - ${response.statusText}`)
      }
      const retour = await response.json()
      // init state.place
      if (retour.membership_products) {
        this.membershipProducts = retour.membership_products
        // log({object : retour.membership_products})
      }

      try {
        urlImage = retour.img_variations.fhd
      } catch (e) {
        urlImage = '/medias/images/default_header_1080x300.jpg'
      }

      try {
        urlLogo = retour.logo_variations.med
      } catch (e) {
        urlLogo = '/medias/images/default_header_1080x300.jpg'
      }

      this.header = {
        urlImage: urlImage,
        logo: urlLogo,
        shortDescription: retour.short_description,
        longDescription: retour.long_description,
        titre: retour.organisation,
        domain: domain,
        categorie: retour.categorie
      }

      // chargemment terminé
      return true
    } catch (error) {
      log({ message: 'loadPlace', error })
      emitter.emit('modalMessage', {
        titre: 'Erreur',
        contenu: `Chargement des données initiales(lieu/...) -- erreur: ${error.message}`
      })
      // chargemment terminé
      return true
    } finally {
      this.loading = false
    }
  },
  /**
   * Reset les clients/customers d'un prix lié à une adhésion
   * @param {object} product - proxy/object
   */
  resetPriceCustomers (product) {
    console.log('-> resetPriceCustomers, product =', product)
    product.activated = false
    const price = JSON.parse(JSON.stringify(product.priceLinkWithMembership))
    let products = this.forms.find(form => form.uuid === this.currentUuidEventForm).products
    let prices = products.find(product => product.uuid === price.productUuid).prices
    let priceResult = prices.find(prix => prix.uuid === price.priceUuid)
    priceResult.customers = []
  },
  deleteCurrentEventForm () {
    if (this.forms.find(form => form.uuid === this.currentUuidEventForm).typeForm === 'reservation') {
      this.router.push('/')
      console.log('reset formulaire !')
      // suppression du formulaire "reservation" courant
      const newForms = this.forms.filter(form => form.uuid !== this.currentUuidEventForm)
      this.forms = JSON.parse(JSON.stringify(newForms))
      this.currentUuidEventForm = ''
    } else {
      log({ message: `sessionStore -> deleteCurrentEventForm, ce n'est pas un formulaire de réservation` })
    }
  },
  /**
   * Active l'adhésion liée au prix/price
   * @param {object} price - données du prix
   */
  activationProductMembership (price) {
    // activation du produit adhésion
    const uuid = price.adhesion_obligatoire
    const products = this.forms.find(form => form.uuid === this.currentUuidEventForm).products
    let product = products.find(product => product.uuid === uuid)
    // ajoute d'un customer "champs vide", sauf uuid champ, si supprimé auparavant
    if (price.customers === undefined || price?.customers.length === 0) {
      price.customers = [{ first_name: '', last_name: '', uuid: this.generateUUIDUsingMathRandom() }]
    }
    // vidage du produit adhésion
    product.customers = [{
      first_name: '',
      last_name: '',
      phone: '',
      postal_code: '',
      uuid: ''
    }]
    // adhésion non activée/visible
    product.activated = true
    // conditions de l'adhésion
    product.conditionsRead = false
    product.optionRadio = ''
    // ajout de la propriété "checked" dans "option_generale_checkbox"
    product.option_generale_checkbox.forEach((option) => {
      option.checked = false
    })
  },
  deactivationProductMembership (uuid) {
    const products = this.forms.find(form => form.uuid === this.currentUuidEventForm).products
    let product = products.find(product => product.uuid === uuid)
    if (product !== undefined) {
      product.activated = false
    }
  },
  setLoadingValue (value) {
    this.loading = value
  },
  cleanFormMembership (uuid) {
    // console.log('-> cleanFormMembership, uuid =', uuid)
    // convert proxy to array
    let forms = JSON.parse(JSON.stringify(this.forms))
    console.log('0 - forms =', forms)
    // delete form by uuid
    let newforms = forms.filter(obj => obj.uuid !== uuid)
    // insert empty form + uuid
    newforms.push({
      typeForm: 'membership',
      readConditions: false,
      uuidPrice: '',
      first_name: '',
      last_name: '',
      email: this.me.email,
      postal_code: '',
      phone: '',
      option_checkbox: [],
      option_radio: '',
      uuid
    })
    // replace forms
    this.forms = newforms
  },
  // status 226 = 'Paiement validé. Création des billets et envoi par mail en cours.' côté serveur
  // status 208 = 'Paiement validé. Billets envoyés par mail.'
  // status 402 = pas payé
  // status 202 = 'Paiement validé. Création des billets et envoi par mail en cours.' coté front
  async postStripeReturn (uuidStripe) {
    // console.log(`-> fonc postStripeReturn, uuidStripe =`, uuidStripe)
    let messageValidation = 'OK', messageErreur = 'Retour stripe:'

    const stripeStep = getLocalStateKey('stripeStep')
    // console.log('stripeStep =', stripeStep)

    // adhésion, attente stripe adhesion
    if (stripeStep.action === 'expect_payment_stripe_membership') {
      messageValidation = `<h3>Adhésion OK !</h3>`
      messageErreur = `Retour stripe pour l'adhésion:`
      // vidage formulaire
      this.cleanFormMembership(stripeStep.uuidForm)
      // action stripe = aucune
      setLocalStateKey('stripeStep', { action: null })
    }

    const apiStripe = `/api/webhook_stripe/`
    const options = {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ uuid: uuidStripe })
    }

    this.loading = true
    fetch(domain + apiStripe, options).then(response => {
      // console.log('/api/webhook_stripe/ -> response =', response)
      if (response.status !== 226 && response.status !== 208 && response.status !== 202) {
        throw new Error(`${response.status} - ${response.statusText}`)
      }
      return response.json()
    }).then(retour => {
      // message ok
      // console.log('/api/webhook_stripe/ -> retour =', retour)
      emitter.emit('modalMessage', {
        titre: 'Succès',
        dynamic: true,
        typeMsg: 'success',
        contenu: messageValidation
      })
      this.loading = false
      // informer le state de l'adhésion si connecté
      if (this.accessToken !== '') {
        // console.log('-> postStripeReturn, expect_payment_stripe_membership !')
        this.getMe()
      }
    }).catch(function (error) {
      log({ message: 'postStripeReturn, /api/webhook_stripe/ error: ', error })
      emitter.emit('modalMessage', {
        titre: 'Erreur',
        dynamic: true,
        contenu: `${messageErreur} ${error.message}`
      })
      this.loading = false
    })
  },
  addCustomer (productUuid, priceUuid) {
    const products = this.forms.find(form => form.uuid === this.currentUuidEventForm).products
    const product = products.find(prod => prod.uuid === productUuid)
    let customers = product.prices.find(prix => prix.uuid === priceUuid).customers
    customers.push({ first_name: '', last_name: '', uuid: this.generateUUIDUsingMathRandom() })
  }
}