import {defineStore} from 'pinia'

const domain = `${location.protocol}//${location.host}`

export const useAllStore = defineStore({
  id: 'all',
  state: () => ({
    language: 'fr',
    events: [],
    place: {},
    loading: false,
    error: null
  }),
  actions: {
    async getEvents() {
      this.events = []
      this.loading = true
      try {
        const apiEvents = `/api/events/`
        const response = await fetch(domain + apiEvents)
        if (response.status !== 200) {
          throw new Error(`${response.status} - ${response.statusText}`)
        }
        const retour = await response.json()
        console.log('getEvents, type retour =', typeof(retour))
        this.events = retour
      } catch (error) {
        console.log('useAllStore, getEvents:', erreur)
        this.error = error
      } finally {
        this.loading = false
      }
    },
    async getPlace(slug) {
      this.place = {}
      this.loading = true
      try {
        const apiLieu = `/api/here/`
        const response = await fetch(domain + apiLieu)
        if (response.status !== 200) {
          throw new Error(`${response.status} - ${response.statusText}`)
        }
        const retour = await response.json()
        console.log('useAllStore, getPlace:', retour)
        this.place = retour
      } catch (error) {
        this.error = error
        console.log('Store, event(slug), erreur:', erreur)
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