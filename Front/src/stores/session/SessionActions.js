import { log } from '../../communs/LogError'
import * as CryptoJS from 'crypto-js'
import { setLocalStateKey, getLocalStateKey } from '../../communs/storeLocal'

const domain = `${window.location.protocol}//${window.location.host}`

export const sessionActions = {
  disconnect () {
    console.log('-> disconnect')
    this.me = {
      cashless: {},
      reservations: [],
      membership: [],
      email: ''
    }
    this.accessToken = ''
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
        // info: email dans this.me.email
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
      // console.log('-> getMe, response =', response)
      if (response.status === 200) {
        const retour = await response.json()
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
  async automaticConnection () {
    // console.log('-> automaticConnection')
    const refreshToken = getLocalStateKey('refreshToken')
    // console.log('-> automaticConnection, refreshToken =',refreshToken)
    if (this.accessToken === '' && refreshToken !== undefined) {
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
  /**
   * Formate les données d'un évènement pour un formulaire
   * @param postEvent
   */
  initFormEvent (postEvent) {
    // console.log('-> initFormEvent')
    this.currentUuidEventForm = postEvent.uuid
    // hash retour et sauvegarde dans event
    const returnString = JSON.stringify(postEvent)
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
      postEvent.optionsRadioSelected = false

      // ajout de l'adhésion obligatoire d'un prix de produits dans la liste des produits
      let newProducts = []
      postEvent.products.forEach((product) => {
        newProducts.push(product)
        product.prices.forEach((price) => {
          // pour avoir un champ inputs visible
          price['customers'] = [{ first_name: '', last_name: '', uuid: this.generateUUIDUsingMathRandom() }]
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
            // adhésion non activée/visible
            newProduct['activated'] = false
            // conditions de l'adhésion
            newProduct['conditionsRead'] = false
            newProducts.push(JSON.parse(JSON.stringify(newProduct)))
          }
        })
      })
      postEvent.products = newProducts
      postEvent['email'] = this.me.email
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
  activationProductMembership (uuid) {
    const products = this.forms.find(form => form.uuid === this.currentUuidEventForm).products
    products.find(product => product.uuid === uuid).activated = true
  },
  deactivationProductMembership (uuid) {
    const products = this.forms.find(form => form.uuid === this.currentUuidEventForm).products
    products.find(product => product.uuid === uuid).activated = false
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
    console.log('stripeStep =', stripeStep)

    // adhésion, attente stripe adhesion
    if (stripeStep.action === 'expect_payment_stripe') {
      messageValidation = `<h3>Adhésion OK !</h3>`
      messageErreur = `Retour stripe pour l'adhésion:`
      // debugger
      // vidage formulaire
      this.cleanFormMembership(stripeStep.uuidForm)
      // action stripe = aucune
      setLocalStateKey('stripeStep', { action: null })
    }

    /*
    // reservation(s)
    if (this.stripeEtape !== null) {
      messageValidation = `<h3>Paiement validé.</h3>`
      messageErreur = `Retour stripe pour une/des réservation(s):`
    }
    */

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
      emitter.emit('modalMessage', {
        titre: 'Succès',
        dynamic: true,
        typeMsg: 'success',
        contenu: messageValidation
      })
      this.loading = false
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