import {defineStore} from 'pinia'
import {useAllStore} from '@/stores/all'

const domain = `${location.protocol}//${location.host}`

export const useEventStore = defineStore({
  id: 'event',
  state: () => ({
    event: {},
    showProduct: {
      cashless: false,
      gift: false
    },
    forms: [],
    loading: false,
    error: null
  }),
  actions: {
    async getEventBySlug(slug, email) {
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

        for (const productKey in retour.products) {
          const product = retour.products[productKey]
          // console.log('-> product =', product)
          // les produits peuvent ils être affiché (attention tous les produits ne sont pas encore gérés)
          // cashless
          if (product.categorie_article === 'S' && product.prices.length > 0) {
            this.showProduct.cashless = true
          }

          // ajout d'une propriété 'customers' à chaque prix
          for (const prixKey in product.prices) {
            product.prices[prixKey]['customers'] = []
          }
        }
        this.event = retour
        this.initEventForm(email)
        // updata data header
        this.getEventHeader()

      } catch (error) {
        this.error = error
        console.log('useEventStore, getEventBySlug:', error)
        emitter.emit('modalMessage', {
          titre: 'Erreur',
          contenu: `Chargement de l'évènement '${slug}', erreur: ${error}`
        })
      } finally {
        this.loading = false
      }
    },
    // init le formulaire d'un évènement (CardBillet, CardOptions)
    initEventForm(email) {
      // console.log('-> action initEventForm !')
      const allStore = useAllStore()
      // init data form / event uuid
      let form = this.forms.find(obj => obj.event === this.event.uuid)
      if (form === undefined) {

        this.forms.push({
          name: this.event.name,
          initDate: new Date().toLocaleString(),
          event: this.event.uuid,
          email: allStore.adhesAllmail, // pas d'observeur/proxy
          emailConfirme: allStore.adhesAllmail,
          options_radio: this.event.options_radio,
          options_checkbox: this.event.options_checkbox,
          prices: [],
          chargeCashless: 0
        })
        form = this.forms.find(obj => obj.event === this.event.uuid)

        // options, ajout de la propriétée 'activation' à toutes les options
        const options = ['options_checkbox', 'options_radio']
        for (const optionsKey in options) {
          let eventOptions = form[options[optionsKey]]
          for (const eventOptionsKey in eventOptions) {
            // console.log('->', eventOptions[eventOptionsKey])
            eventOptions[eventOptionsKey]['activation'] = false
          }
        }

        // ajout de la propriété "don", l'activation de chaque don sera à false par défaut
        form['gifts'] = []
        const dons = this.event.products.filter(prod => prod.categorie_article === 'D')
        console.log('init dons')
        for (const donsKey in dons) {
          const don = dons[donsKey]
          form.gifts.push({
            uuidGift: don.uuid,
            name: don.name,
            price: don.prices[0].uuid, // sélection du premier prix
            enable: false
          })
        }
      }
      console.log('email =', email)
      if (email !== undefined) {
        this.updateEmail('emailConfirme', email)
        this.updateEmail('email', email)
      }
    },
    generateUUIDUsingMathRandom() {
      let d = new Date().getTime();//Timestamp
      let d2 = (performance && performance.now && (performance.now() * 1000)) || 0;//Time in microseconds since page-load or 0 if unsupported
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        let r = Math.random() * 16;//random number between 0 and 16
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
    addCustomer(priceUuid) {
      // console.log('-> fonc addCustomer !')
      let prix = this.forms.find(obj => obj.event === this.event.uuid).prices
      let lePrix = prix.find(obj => obj.uuid === priceUuid)
      // pas encore d'ajout de ce prix
      if (lePrix === undefined) {
        prix.push({
          uuid: priceUuid,
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
      // console.log('-> fonc updateCustomer !')
      const customers = this.forms.find(obj => obj.event === this.event.uuid).prices.find(obj2 => obj2.uuid === priceUuid).customers
      let customer = customers.find(obj => obj.uuid === customerUuid)
      customer[variable] = value
    },
    stop(priceUuid, stock, maxPerUser) {
      // console.log('-> fonc stop !')
      const price = this.forms.find(obj => obj.event === this.event.uuid).prices.find(obj2 => obj2.uuid === priceUuid)
      // --- gestion de l'affichage du bouton "+" ---
      // aucun ajout
      if (price === undefined) {
        return false
      }
      const nbCustomers = price.customers.length

      // message nb billet max par utilisateur atteint
      if (nbCustomers === maxPerUser) {
        emitter.emit('modalMessage', {
          titre: 'Attention',
          contenu: `Le nombre maximun de billet par utilisateur est atteint !`
        })
      }

      // stock pas géré et maxi par user géré
      if (stock === null && nbCustomers < maxPerUser) {
        return false
      }
      // stock et maxi par user géré
      if (stock !== null && (stock - nbCustomers) >= 1 && nbCustomers < maxPerUser) {
        return false
      }
      return true
    },
    updateOptions(inputType, value, uuidOption) {
      let form = this.forms.find(obj => obj.event === this.event.uuid)
      // console.log('-> fonc updateOptions, type =', inputType, '  --  value =', value, '  --  uuidOptions =', uuidOptions)
      if (inputType === 'options_radio') {
        // toutes les activation radio à false
        for (let i = 0; i < form.options_radio.length; i++) {
          form.options_radio[i].activation = false
        }
      }
      const option = form[inputType].find(opt => opt.uuid === uuidOption)
      option.activation = value
    },
    allOptionsFalse() {
      let form = this.forms.find(obj => obj.event === this.event.uuid)
      for (let i = 0; i < form.options_radio.length; i++) {
        form.options_radio[i].activation = false
      }
      for (let i = 0; i < form.options_checkbox.length; i++) {
        form.options_checkbox[i].activation = false
      }
    },
    updateChargeCashless(value) {
      // console.log('updateCashless =', value)
      this.forms.find(obj => obj.event === this.event.uuid).chargeCashless = parseFloat(value)
    },
    enableGifts(list) {
      if (list !== undefined && list.length > 0) {
        const gifts = this.forms.find(obj => obj.event === this.event.uuid).gifts
        // console.log('gifts =', gifts)
        for (const listKey in list) {
          const giftNameToEnable = list[listKey]
          try {
            if (gifts.find(obj2 => obj2.name === giftNameToEnable) === undefined) {
              throw('Nom du don inconnu !')
            } else {
              let gift = gifts.find(obj2 => obj2.name === giftNameToEnable)
              gift.enable = true
            }
          } catch (err) {
            console.log('event store, func. enableGifts :', err)
          }
        }
      }
    },
    changePriceGift(uuidGift, priceUuid) {
      let gift = this.forms.find(obj => obj.event === this.event.uuid).gifts.find(obj2 => obj2.uuidGift === uuidGift)
      gift.price = priceUuid
    },
    setEnableGift(uuidGift, value) {
      let gift = this.forms.find(obj => obj.event === this.event.uuid).gifts.find(obj2 => obj2.uuidGift === uuidGift)
      gift.enable = value
    },
    getEventHeader() {
      // console.log('-> action getHeaderEvent')
      let urlImage
      try {
        urlImage = this.event.img_variations.fhd
      } catch (e) {
        urlImage = `${domain}/media/images/image_non_disponible.svg`
      }
      const allStore = useAllStore()
      allStore.header = {
        urlImage: urlImage,
        shortDescription: this.event.short_description,
        longDescription: this.event.long_description,
        titre: this.event.name
      }
    }

  },
  getters: {
    getExistGift: (state) => {
      let retour = false
      if (state.event.products.filter(prod => prod.categorie_article === 'D').length > 0) {
        retour = true
      }
      return retour
    },
    getEnableGift: (state) => {
      // console.log('-> fonc getEnableGift')
      return (uuidGift) => { // récupération de l'argument
        const gifts = state.forms.find(obj => obj.event === state.event.uuid).gifts
        return gifts.find(obj2 => obj2.uuidGift === uuidGift).enable
      }
    },
    getPriceGift: (state) => {
      return (uuidGift) => {
        return state.forms.find(obj => obj.event === state.event.uuid).gifts.find(obj2 => obj2.uuidGift === uuidGift).price
      }
    },
    getOptions: (state) => {
      let form = state.forms.find(obj => obj.event === state.event.uuid)
      const options_checkbox = form.options_checkbox
      const nb_options_checkbox = options_checkbox.length
      const options_radio = form.options_radio
      const nb_options_radio = options_radio.length
      return {
        options_checkbox,
        options_radio,
        nb_options_checkbox,
        nb_options_radio
      }
    },
    getChargeCashless: (state) => {
      const form = state.forms.find(obj => obj.event === state.event.uuid)
      return form.chargeCashless
    }
  },
  persist: {
    key: 'Tibillet-event',
    storage: window.sessionStorage
  }
})