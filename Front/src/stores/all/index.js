// store
import {defineStore} from 'pinia'

const domain = `${location.protocol}//${location.host}`

export const useAllStore = defineStore({
  id: 'all',
  state: () => ({
    language: 'fr',
    events: {},
    place: {},
    routeName: '',
    header: {
      titre: '',
      urlImage: null,
      shortDescription: ''
    },
    loading: false,
    error: null
  }),
  actions: {
    async getEvents() {
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
    async getPlace() {
      console.log('-> action getPlace !')
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
          console.log('redirection stopée --> all/index.js, retour.activer_billetterie = false ')
          // window.location = "https://wiki.tibillet.re/"
        }
      } catch (error) {
        this.error = error
        // console.log('useAllStore, getPlace: type =', error)
        // redirection sur le wiki tibillet si 404
        if (error.toString().indexOf('404')) {
          console.log('redirection stopée --> all/index.js, erreur getPlace ')
          // window.location = "https://wiki.tibillet.re/"
        }
        this.loading = false
      } finally {
        this.loading = false
      }
    },
    getPricesAdhesion(productUuid) {
      // console.log('-> fonc getPricesAdhesion !')
      try {
        return this.place.membership_products.find(obj => obj.uuid === productUuid).prices
      } catch (error) {
        // console.log('store all, getPricesAdhesion:', error)
        return []
      }
    },
    getNameAdhesion(productUuid) {
      console.log('-> fonc getNameAdhesion !')
      try {
        return this.place.membership_products.find(obj => obj.uuid === productUuid).name
      } catch (error) {
        // console.log('store all, getNameAdhesion:', error)
        return ''
      }
    },
    getListAdhesions() {
      if (this.place.membership_products !== undefined) {
        return this.place.membership_products
      } else {
        return []
      }
    },
    setHeaderPlace() {
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
  persist: {
    key: 'Tibillet-all',
    storage: window.sessionStorage
  }
})