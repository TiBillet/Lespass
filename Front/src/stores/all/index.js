// store
import {defineStore} from 'pinia'

const domain = `${location.protocol}//${location.host}`

export const useAllStore = defineStore({
  id: 'all',
  state: () => ({
    language: 'fr',
    events: {},
    place: {},
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
        const retour = await response.json()
        // console.log('getEvents, type retour =', retour)
        this.events = retour
      } catch (error) {
        // console.log('useAllStore, getEvents:', error)
        this.error = error
      } finally {
        this.loading = false
      }
    },
    async getPlace(slug) {
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
        // console.log('getPlace, retour =', retour)
        this.place = retour
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
      } finally {
        this.loading = false
      }
    }
  },
  persist: {
    key: 'Tibillet-all',
    storage: window.sessionStorage
  }
})