import {defineStore} from 'pinia'

const domain = `${location.protocol}//${location.host}`

export const useEventStore = defineStore({
  id: 'event',
  state: () => ({
    event: {},
    forms: [],
    loading: false,
    error: null
  }),
  actions: {
    async getEventBySlug(slug) {
      const urlApi = `/api/eventslug/${slug}`
      this.error = null
      this.event = {}
      this.loading = true
      try {
        const response = await fetch(domain + urlApi)
        if (response.status !== 200) {
          throw new Error(`${response.status} - ${response.statusText}`)
        }
        const retour = await response.json()
        // console.log('-> getEventBySlug, retour =', retour)
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
        console.log('useEventStore, getEventBySlug:', error)
        emitter.emit('message', {
          tmp: 4,
          typeMsg: 'danger',
          contenu: `Chargement de l'évènement '${slug}', erreur: ${error}`
        })
      } finally {
        this.loading = false
      }
    },
    generateUUIDUsingMathRandom() {
      var d = new Date().getTime();//Timestamp
      var d2 = (performance && performance.now && (performance.now() * 1000)) || 0;//Time in microseconds since page-load or 0 if unsupported
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = Math.random() * 16;//random number between 0 and 16
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
    getCustomersByUuidPrix(priceUuid) {
      // console.log('-> fonc getCustomersByUuidPrix !')
      try {
        return this.forms.find(obj => obj.event === this.event.uuid).prices.find(obj => obj.uuid === priceUuid).customers
      } catch (e) {
        return []
      }
    },
    addCustomer(priceUuid, categorieArticle) {
      console.log('-> fonc addCustomer !')
      console.log('priceUuid =', priceUuid)
      console.log('categorieArticle =', categorieArticle)
      let prix = this.forms.find(obj => obj.event === this.event.uuid).prices
      let lePrix = prix.find(obj => obj.uuid === priceUuid)
      // pas encore d'ajout de ce prix
      if (lePrix === undefined) {
        prix.push({
          uuid: priceUuid,
          categorie_article: categorieArticle,
          qty: 0,
          customers: []
        })
        lePrix = prix.find(obj => obj.uuid === priceUuid)
      }
      lePrix.customers.push({
        uuid: this.generateUUIDUsingMathRandom(),
        first_name: "",
        last_name: ""
      })
      lePrix.qty = lePrix.customers.length
    },
    deleteCustomer(priceUuid, customerUuid) {
      // console.log('-> fonc deleteCustomer !')
      let prix = this.forms.find(obj => obj.event === this.event.uuid).prices
      const customers = prix.find(obj => obj.uuid === priceUuid).customers.filter(obj => obj.uuid !== customerUuid)
      const qty = customers.length
      // maj customers
      this.forms.find(obj => obj.event === this.event.uuid).prices.find(obj => obj.uuid === priceUuid).customers = customers
      // maj qty
      this.forms.find(obj => obj.event === this.event.uuid).prices.find(obj => obj.uuid === priceUuid).qty = qty
      // supprime leproduit si quantité = 0
      prix = this.forms.find(obj => obj.event === this.event.uuid).prices.filter(obj2 => obj2.qty > 0)
      this.forms.find(obj => obj.event === this.event.uuid).prices = prix

      // console.log('customers =', customers)
    },
    updateCustomer(priceUuid, customerUuid, value, variable) {
      console.log('-> fonc updateCustomer !')
      // console.log('priceUuid =', priceUuid)
      // console.log('customerUuid =', customerUuid)
      const customers = this.forms.find(obj => obj.event === this.event.uuid).prices.find(obj2 => obj2.uuid === priceUuid).customers
      let customer = customers.find(obj => obj.uuid === customerUuid)
      customer[variable] = value
    }
  },
  persist: {
    key: 'Tibillet-event',
    storage: window.sessionStorage
  }
})