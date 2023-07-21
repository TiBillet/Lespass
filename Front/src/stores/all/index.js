// store
import { defineStore } from 'pinia'
import * as CryptoJS from 'crypto-js'
import { log } from '../../communs/LogError'

const domain = `${window.location.protocol}//${window.location.host}`

async function loadEventBySlug (slug) {
  const urlApi = `/api/eventslug/${slug}`
  try {
    const response = await fetch(domain + urlApi)
    if (response.status !== 200) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    return { status: 'ok', content: await response.json() }
  } catch (error) {
    return { status: 'error', error: error }
  }
}

export const useAllStore = defineStore({
  id: 'all',
  state: () => ({
    identitySite: true,
    loading: false,
    error: null,
    language: 'fr',
    events: {},
    eventHashReturn: 'first',
    eventSlug: '',
    place: {},
    routeName: '',
    header: {
      titre: '',
      urlImage: null,
      shortDescription: ''
    },
    adhesion: {
      email: '',
      first_name: '',
      last_name: '',
      phone: null,
      postal_code: null,
      adhesion: '',
      // status: '',
      readConditions: false,
      options: []
    },
    tenant: {
      email: '',
      organisation: '',
      short_description: '',
      img_url: '',
      logo_url: '',
      stripe_connect_account: null,
      readConditions: false
    },
    forms: []
  }),
  actions: {
    updateSlug(slug) {
      state.eventSlug = slug
    },
    setIdentitySite (value) {
      this.identitySite = value
    },
    async getEvents () {
      this.error = null
      this.events = {}
      this.loading = true
      try {
        const apiEvents = `/api/events/`
        const response = await fetch(domain + apiEvents)
        if (response.status !== 200) {
          throw new Error(`${response.status} - ${response.statusText}`)
        }
        this.events = await response.json()
      } catch (error) {
        // console.log('useAllStore, getEvents:', error)
        this.error = error
      } finally {
        this.loading = false
      }
    },
    async getPlace () {
      // console.log('-> action getPlace !')
      this.error = null
      this.place = {}
      this.loading = true
      try {
        const apiLieu = `/api/here/`
        const response = await fetch(domain + apiLieu)
        if (response.status !== 200) {
          throw new Error(`${response.status} - ${response.statusText}`)
        }
        const retour = await response.json()
        this.loading = false
        // console.log('getPlace, retour =', retour)
        this.place = retour
        // update data header
        this.setHeaderPlace()
        // redirection sur le wiki tibillet si la billetterie n'est pas activée
        if (retour.activer_billetterie === false) {
          console.log('redirection stopée --> all/EmitEvent.js, retour.activer_billetterie = false ')
          // window.location = "https://wiki.tibillet.re/"
        }
      } catch (error) {
        this.error = error
        // console.log('useAllStore, getPlace: type =', error)
        // redirection sur le wiki tibillet si 404
        if (error.toString().indexOf('404')) {
          console.log('redirection stopée --> all/EmitEvent.js, erreur getPlace ')
          // window.location = "https://wiki.tibillet.re/"
        }
        this.loading = false
      } finally {
        this.loading = false
      }
    },
    getPricesAdhesion (productUuid) {
      // console.log('-> fonc getPricesAdhesion !')
      try {
        return this.place.membership_products.find(obj => obj.uuid === productUuid).prices
      } catch (error) {
        // console.log('store all, getPricesAdhesion:', error)
        return []
      }
    },
    getPartialDataAdhesion (productUuid) {
      // console.log('-> fonc getDataAdhesion !')
      if (productUuid !== '') {
        const dataArray = JSON.parse(JSON.stringify(this.place.membership_products))
        const data = dataArray.find(obj => obj.uuid === productUuid)
        return data
      } else {
        return {
          name: '',
          short_description: '',
          categorie_article: 'INCONNUE',
          option_generale_radio: [],
          option_generale_checkbox: []
        }
      }

    },
    getListAdhesions () {
      if (this.place.membership_products !== undefined) {
        return this.place.membership_products
      } else {
        return []
      }
    },
    setHeaderPlace () {
      let urlImage, urlLogo
      try {
        urlImage = this.place.img_variations.fhd
      } catch (e) {
        urlImage = `${domain}/media/images/image_non_disponible.svg`
      }

      try {
        urlLogo = this.place.logo_variations.med
      } catch (e) {
        urlLogo = `${domain}/media/images/image_non_disponible.svg`
      }

      this.header = {
        urlImage: urlImage,
        logo: urlLogo,
        shortDescription: this.place.short_description,
        longDescription: this.place.long_description,
        titre: this.place.organisation,
        domain: domain
      }
    }
  },
  getters: {
    getArtists (state) {
      const currentEvent = state.events.find(event => event.slug === state.eventSlug)
      console.log('currentEvent =', currentEvent)
      return currentEvent.artists
    },
    getFormEventBySlug (state) {
      return async (slug) => {
        state.eventSlug = slug
        state.error = null
        state.loading = true
        const retour = await loadEventBySlug(slug)

        // hash retour et sauvegarde dans event
        const returnString = JSON.stringify(retour)
        const hashReturn = CryptoJS.HmacMD5(returnString, 'NODE_18_lts').toString()

        console.log({ message: 'state.events = ' })
        log({ object: state.events })
        // actualisation event
        if (state.eventHashReturn === 'reset' || state.eventHashReturn !== hashReturn) {
          state.eventHashReturn = hashReturn
          log({ message: 'Modification data session event !' })
          let event = state.events.find(event => event.slug === slug)
          event = retour.content
        }

        log({ message: '-> getFormEventBySlug, retour = ', raw: retour })
        state.loading = false
        if (retour.status === 'error') {
          log({ message: 'useEventStore, getEventBySlug: ', error: retour.error })
          emitter.emit('modalMessage', {
            titre: 'Erreur',
            contenu: `Chargement de l'évènement '${slug}' -- erreur: ${retour.error.message}`
          })
        }
      }
    },
    getNameAdhesion: (state) => {
      return (uuidProductAdhesion) => {
        const allStore = useAllStore()
        try {
          const dataArray = JSON.parse(JSON.stringify(allStore.place.membership_products))
          return dataArray.find(prod => prod.uuid === uuidProductAdhesion).name
        } catch (error) {
          return ''
        }
      }
    }
  }
  ,
  persist: {
    key: 'Tibillet-all',
    storage: window.sessionStorage
  }
})