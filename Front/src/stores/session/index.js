// store
import { defineStore } from 'pinia'
import * as CryptoJS from 'crypto-js'
import { log } from '../../communs/LogError'
import { useLocalStore } from '../local/index'

const domain = `${window.location.protocol}//${window.location.host}`

export const useSessionStore = defineStore({
  id: 'session',
  state: () => ({
    identitySite: true,
    loading: false,
    language: 'fr',
    routeName: '',
    header: null,
    membershipProducts: null,
    currentEventUuid: null,
    events: [],
    email: ''
  }),
  getters: {
    getArtists (state) {
      return state.events.find(event => event.uuid === state.currentEventUuid).artists
    },
    getEvent (state) {
      return state.events.find(event => event.uuid === state.currentEventUuid)
    },
    getBilletsFromEvent (state) {
      const event = state.events.find(event => event.uuid === state.currentEventUuid)
      // "B" billets payants et "F" gratuits + "A" adhésion lié à un prix d'un autre produit dans l'évènement
      const categories = ['F', 'B', 'A']
      return event.products.filter(prod => categories.includes(prod.categorie_article))
    },
    getEmail (state) {
      return state.email
    },
    getDataAdhesion (state) {
      return (membershipsUuid) => {
        return state.membershipProducts.find(membership => membership.uuid === membershipsUuid)
      }
    },
    getProductIsActivated (state) {
      return (productUuid) => {
        const products = state.events.find(event => event.uuid === state.currentEventUuid).products
        return products.find(product => product.uuid === productUuid).activated
      }
    }
  },
  actions: {
    setIdentitySite (value) {
      this.identitySite = value
    },
    updateEmail (value) {
      this.email = value
    },
    /**
     * Formate les données d'un évènement pour un formulaire
     * @param postEvent
     */
    storeEvent (postEvent) {
      this.currentEventUuid = postEvent.uuid

      // hash retour et sauvegarde dans event
      const returnString = JSON.stringify(postEvent)
      const hash = CryptoJS.HmacMD5(returnString, 'NODE_18_lts').toString()

      // lévènement actuel existe il dans le tablea events
      let event = this.events?.find(event => event.uuid === postEvent.uuid)

      // création ou reset de l'objet event si non existant ou données "postEvent" différentes
      if (event === undefined || event.eventHash !== hash) {
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
            price['customers'] = [{ first_name: '', last_name: '' }]
            // ajout de l'adhésion dans la liste de produits de l'évènement
            if (price.adhesion_obligatoire !== null) {
              let newProduct = this.membershipProducts.find(membership => membership.uuid === price.adhesion_obligatoire)
              newProduct['customers'] = [{ first_name: '', last_name: '', phone: '', postal_code: '' }]
              // adhésion non activée/visible
              newProduct['activated'] = false
              newProducts.push(JSON.parse(JSON.stringify(newProduct)))
            }
          })
        })
        postEvent.products = newProducts
        postEvent['email'] = this.email
        this.events.push(postEvent)
      }
    },
    /**
     * Initialise/charge les données du tenant/lieu (place, membershipProducts)
     * @returns {Promise<void>}
     */
    async loadPlace () {
      log({ message: '-> loadPlace' })
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

        // priorité: l'email est pris dans le cache local(résultat d'une validation d'email)
        const { getEmailStore } = useLocalStore()
        console.log('getEmailStore =', getEmailStore)
        this.email = getEmailStore !== '' ? getEmailStore : ''

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
    async loadEvent (slug, next) {
      // log({ message: 'loadEvent, slug = ' + slug })
      this.eventSlug = slug
      this.error = ''
      this.loading = true

      const urlApi = `/api/eventslug/${slug}`
      let retour
      try {
        const response = await fetch(domain + urlApi)
        if (response.status !== 200) {
          throw new Error(`${response.status} - ${response.statusText}`)
        }
        retour = { status: 'ok', content: await response.json() }
      } catch (error) {
        retour = { status: 'error', error: error }
      }

      if (retour.status === 'error') {
        log({ message: 'useEventStore, getEventBySlug: ', error: retour.error })
        emitter.emit('modalMessage', {
          titre: 'Erreur',
          contenu: `Chargement de l'évènement '${slug}' -- erreur: ${retour.error.message}`
        })
        return false
      } else {
        this.storeEvent(retour.content)
      }
      this.loading = false
      next()
    },
    toggleActivationProductMembership (uuid) {
      const products = this.events.find(event => event.uuid === this.currentEventUuid).products
      const status = products.find(product => product.uuid === uuid).activated
      products.find(product => product.uuid === uuid).activated = !status
    }
  },
  persist: {
    key: 'Tibillet-session',
    storage: window.sessionStorage
  }
})