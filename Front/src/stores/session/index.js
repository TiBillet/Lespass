// store
import { defineStore } from 'pinia'
import * as CryptoJS from 'crypto-js'
import { log } from '../../communs/LogError'
// import {emitEvent} from "../../communs/EmitEvent"

const domain = `${window.location.protocol}//${window.location.host}`

export const useSessionStore = defineStore({
  id: 'session',
  state: () => ({
    identitySite: true,
    loading: false,
    error: '',
    language: 'fr',
    routeName: '',
    header: null,
    membershipProducts: null,
    events: [],
    event: null,
    eventHashReturn: 'first'
  }),
  getters: {
    getArtists (state) {
      const currentEvent = state.events.find(event => event.slug === state.eventSlug)
      // console.log('-> getArtists, currentEvent =', currentEvent)
      // console.log('-> getArtists, state.eventSlug =', state.eventSlug)
      return currentEvent.artists
    },
    getEvent (state) {
      return state.events.find(event => event.slug === state.eventSlug)
    }
  },
  actions: {
    setIdentitySite (value) {
      this.identitySite = value
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

      } catch (error) {
        this.error = error
        log({ message: 'loadPlace', error })
      } finally {
        this.loading = false
      }
    },
    async loadEvent (slug) {
      log({ message: 'loadEvent, slug = ' + slug })
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

      // hash retour et sauvegarde dans event
      const returnString = JSON.stringify(retour)
      const hashReturn = CryptoJS.HmacMD5(returnString, 'NODE_18_lts').toString()

      // actualisation event
      if (this.eventHashReturn === 'first' || this.eventHashReturn !== hashReturn) {
        this.eventHashReturn = hashReturn
        log({ message: 'Modification data session event !' })
        this.event = retour.content
      }

      this.loading = false
      if (retour.status === 'error') {
        log({ message: 'useEventStore, getEventBySlug: ', error: retour.error })
        emitter.emit('modalMessage', {
          titre: 'Erreur',
          contenu: `Chargement de l'évènement '${slug}' -- erreur: ${retour.error.message}`
        })
      }
    },
    /**
     * Charge tous les évènements dans le store session
     * @returns {Promise<void>}
     */
    async loadEvents () {
      this.error = ''
      this.loading = true
      try {
        const apiEvents = `/api/events/`
        const response = await fetch(domain + apiEvents)
        if (response.status !== 200) {
          throw new Error(`${response.status} - ${response.statusText}`)
        }
        this.events = await response.json()
      } catch (error) {
        this.error = error
        log({ message: 'loadEvents', error })
      } finally {
        this.loading = false
      }
    }
  },
  persist: {
    key: 'Tibillet-session',
    storage: window.sessionStorage
  }
})