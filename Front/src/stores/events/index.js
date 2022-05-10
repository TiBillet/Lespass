import {defineStore} from 'pinia'

const domain = `${location.protocol}//${location.host}`

export const useEventsStore = defineStore({
  id: 'events',
  state: () => ({
    events: [],
    event: {},
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
        this.events = retour
      } catch (error) {
        this.error = error
      } finally {
        this.loading = false
      }
    },
    async getEventBySlug(slug) {
      const urlApi = `/api/eventslug/${slug}`
      this.event = {}
      this.loading = true
      try {
        const response = await fetch(domain + urlApi)
        if (response.status !== 200) {
          throw new Error(`${response.status} - ${response.statusText}`)
        }
        const retour = await response.json()
        console.log('-> getEventBySlug, retour =', retour)
        for (const productKey in retour.products) {
          const product = retour.products[productKey]
          for (const prixKey in product.prices) {
            // ajout d'une propriété 'customers' à chaque prix
            product.prices[prixKey]['customers'] = []
          }

        }
        this.event = retour
      } catch (error) {
        this.error = error
        console.log('Store, event(slug), erreur:', erreur)
        emitter.emit('message', {
          tmp: 4,
          typeMsg: 'danger',
          contenu: `Chargement de l'évènement '${slug}', erreur: ${erreur}`
        })
      } finally {
        this.loading = false
      }
    }
  },
  persist: {
    key: 'Tibillet-event',
    storage: window.sessionStorage
  }
})