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
            optionsCheckbox.push({ uuid: membership.uuid, checked: false })
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
  },
  getEvent (state) {
    return state.event
  },
  getBilletsFromEvent (state) {
    const event = state.events.find(event => event.uuid === state.currentEventUuid)
    // "B" billets payants et "F" gratuits + "A" adhésion lié à un prix d'un autre produit dans l'évènement
    const categories = ['F', 'B', 'A']
    return event.products.filter(prod => categories.includes(prod.categorie_article))
  },
  getEmail (state) {
    return state.me.email
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
  },
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
  getIsMemberShip (state) {
    return (membershipUuuid) => {
      // TODO
      // dev
      return false
    }
  }
}