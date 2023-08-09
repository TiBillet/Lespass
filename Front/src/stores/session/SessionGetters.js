import { log } from '../../communs/LogError'

const domain = `${window.location.protocol}//${window.location.host}`

export const sessionGetters = {
  getAccessToken (state) {
    return state.accessToken
  },
  getCurrentFormUuid (state) {
    return state.currentFormUuid
  },
  getFormMembership (state) {
    return (uuid) => {
      if (uuid !== '') {
        let form = state.forms.find(obj => obj.uuid === uuid)
        if (form === undefined) {
          let optionsCheckbox = []
          let membershipProduct = JSON.parse(JSON.stringify(state.membershipProducts)).find(obj => obj.uuid === uuid).option_generale_checkbox
          membershipProduct.forEach((membership) => {
            console.log('membership =', membership)
            membership['checked'] = false
            optionsCheckbox.push(membership)
          })

          state.forms.push({
            readConditions: false,
            uuidPrice: '',
            first_name: '',
            last_name: '',
            email: this.me.email,
            postal_code: '',
            phone: '',
            option_checkbox: optionsCheckbox,
            option_radio: '',
            uuid
          })
        }
        return state.forms.find(form => form.uuid === uuid)
      } else {
        return {
          readConditions: false,
          uuidPrice: '',
          first_name: '',
          last_name: '',
          email: this.me.email,
          postal_code: '',
          phone: '',
          option_checkbox: [],
          option_radio: ''
        }
      }
    }
  },
  getIsLogin (state) {
    return state.accessToken !== '' ? true : false
  },
  getEventForm (state) {
    return state.forms.find(formRec => formRec.uuid === state.currentUuidEventForm)
  },
  getEmailForm (state) {
    const form = state.forms.find(formRec => formRec.uuid === state.currentUuidEventForm)
    return form.email
  }/*,
  getEvent (state) {
    return state.event
  },
  getBilletsFromEvent (state) {
    const event = state.events.find(event => event.uuid === state.currentEventUuid)
    // "B" billets payants et "F" gratuits + "A" adhésion lié à un prix d'un autre produit dans l'évènement
    const categories = ['F', 'B', 'A']
    return event.products.filter(prod => categories.includes(prod.categorie_article))
  }*/,
  getEmail (state) {
    return state.me.email
  },
  getDataAdhesion (state) {
    return (membershipsUuid) => {
      return state.membershipProducts.find(membership => membership.uuid === membershipsUuid)
    }
  },
  getRelatedProductIsActivated (state) {
    return (productUuid) => {
      const form = state.forms.find(formRec => formRec.uuid === state.currentUuidEventForm)
      return form.products.find(prod => prod.uuid === productUuid).activated
    }
  },
  getIsMemberShip (state) {
    return (membershipUuuid) => {
      if (state.me.membership.length > 0) {
        const productExist = state.me.membership.find(obj => obj.product_uuid === membershipUuuid)
        return productExist !== undefined ? true : false
      } else {
        return false
      }
    }
  },
  getBtnAddCustomerCanBeSeen (state) {
    return (productUuid, priceUuid) => {
      let customers = []
      if (state.forms.length > 0) {
        const products = state.forms.find(form => form.uuid === this.currentUuidEventForm).products
        const product = products.find(prod => prod.uuid === productUuid)
        const price = product.prices.find(prix => prix.uuid === priceUuid)
        customers = price.customers
      }
      // pas de clients/no customer
      if (customers.length === 0) {
        return true
      }
      // stock pas géré et maxi par user géré
      if (price.stock === null && customers.length < price.max_per_user) {
        return true
      }
      // stock et maxi par user géré
      if (price.stock !== null && (price.stock - customers.length) >= 1 && customers.length < price.max_per_user) {
        return true
      }
      return false
    }
  },/*
  getCustomers (state) {
    return (data) => {
      console.log('data =', data)
      return []
      // const form = state.forms.find(formRec => formRec.uuid === state.currentUuidEventForm)
      // const product = form.products.find(prod => prod.uuid === productUuid)
      // return product.prices.find(price => price.uuid === priceUuid).customers
    }
  },*/
  getListAdhesions () {
    if (this.membershipProducts !== null) {
      return this.membershipProducts
    } else {
      return []
    }
  },
  getMembershipData (state) {
    // console.log('-> getPartialDataAdhesion !')
    return (productUuid) => {
      if (productUuid !== '') {
        const dataArray = JSON.parse(JSON.stringify(state.membershipProducts))
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
    }
  },
  getMembershipPrices (state) {
    return (productUuid) => {
      // console.log('-> getPricesAdhesion !')
      try {
        return state.membershipProducts.find(obj => obj.uuid === productUuid).prices
      } catch (error) {
        return []
      }
    }
  },
  getMembershipOptionsRadio (state) {
    return (productUuid) => {
      try {
        return state.membershipProducts.find(obj => obj.uuid === productUuid).option_generale_radio
      } catch (error) {
        return []
      }
    }
  },
  getMembershipOptionsCheckbox (state) {
    return (productUuid) => {
      try {
        return state.membershipProducts.find(obj => obj.uuid === productUuid).option_generale_checkbox
      } catch (error) {
        return []
      }
    }
  }
}