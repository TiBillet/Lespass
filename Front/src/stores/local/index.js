import {defineStore} from 'pinia'
import {useAllStore} from '@/stores/all'
import {useEventStore} from '@/stores/event'

const domain = `${location.protocol}//${location.host}`

export const useLocalStore = defineStore({
  id: 'local',
  state: () => ({
    refreshToken: '',
    email: '',
    me: {
      cashless: {},
      reservations: [],
      membership: []
    },
    stripeEtape: null
  }),
  actions: {
    // status 226 = 'Paiement validé. Création des billets et envoi par mail en cours.' côté serveur
    // status 208 = 'Paiement validé. Billets envoyés par mail.'
    // status 402 = pas payé
    // status 202 = 'Paiement validé. Création des billets et envoi par mail en cours.' coté front
    async postStripeReturn(uuidStripe) {
      // console.log(`-> fonc postStripeReturn, uuidStripe =`, uuidStripe)
      let messageValidation = 'OK', messageErreur = 'Retour stripe:'

      // adhésion
      if (this.stripeEtape === 'attente_stripe_adhesion') {
        messageValidation = `<h3>Adhésion OK !</h3>`
        messageErreur = `Retour stripe pour l'adhésion:`
      }

      // reservation(s)
      if (this.stripeEtape !== null) {
        messageValidation = `<h3>Paiement validé.</h3>`
        messageErreur = `Retour stripe pour une/des réservation(s):`
      }

      const apiStripe = `/api/webhook_stripe/`
      const options = {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({uuid: uuidStripe})
      }
      fetch(domain + apiStripe, options).then(response => {
        // console.log('/api/webhook_stripe/ -> response =', response)
        if (response.status !== 226 && response.status !== 208 && response.status !== 202) {
          throw new Error(`${response.status} - ${response.statusText}`)
        }
        return response.json()
      }).then(retour => {
        // message ok
        emitter.emit('modalMessage', {
          titre: 'Succès',
          dynamic: true,
          typeMsg: 'success',
          contenu: messageValidation
        })
      }).catch(function (erreur) {
        console.log('/api/webhook_stripe/ -> erreur: ', erreur)
        emitter.emit('modalMessage', {
          titre: 'Erreur',
          dynamic: true,
          contenu: `${messageErreur} ${erreur}`
        })
      })

    },
    async emailActivation(id, token) {
      // console.log('store, all/EmitEvent.js -> emailActivation')
      const mainStore = useAllStore()

      // attention pas de "/" à la fin de "api"
      const api = `/api/user/activate/${id}/${token}`
      try {
        mainStore.loading = true
        const response = await fetch(domain + api, {
          method: 'GET',
          cache: 'no-cache', // *default, no-cache, reload, force-cache, only-if-cached
          headers: {
            'Content-Type': 'application/json'
          }
        })
        if (response.status === 200) {
          const retour = await response.json()
          // message confirmation email
          emitter.emit('modalMessage', {
            titre: 'Succès',
            typeMsg: 'success',
            dynamic: true,
            contenu: '<h3>Utilisateur activé / connecté !</h3>'
          })
          // maj token d'accès
          window.accessToken = retour.access
          this.refreshToken = retour.refresh
          this.me = await this.getMe(window.accessToken)
          this.email = this.me.email

          mainStore.loading = false
        } else {
          throw new Error(`Erreur conrfirmation mail !`)
        }
      } catch (erreur) {
        console.log(`emailActivation, erreur: ${erreur}`)
        mainStore.error = erreur
        mainStore.loading = false
        emitter.emit('modalMessage', {
          titre: 'Erreur',
          contenu: `Activation email : ${erreur}`
        })
      }
    },
    updateEmail(email, value) {
      this.email = value
    },
    async getMe(accessToken) {
      // console.log('-> action getMe, accessToken =', accessToken)
      try {
        const apiMe = `/api/user/me/`
        const options = {
          method: 'GET',
          cache: 'no-cache',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${window.accessToken} `
          }
        }
        const response = await fetch(domain + apiMe, options)
        // console.log('-> getMe, response =', response)
        if (response.status === 200) {
          const retour =  await response.json()
          return retour
        } else {
          throw new Error(`Erreur ${apiMe} !`)
        }
      } catch (erreur) {
        console.log('-> getMe, erreur:', erreur)
      }
    },
    async refreshAccessToken(refreshToken) {
      // console.log('-> refreshAccessToken, refreshToken =', refreshToken)
      const api = `/api/user/token/refresh/`
      try {
        const response = await fetch(domain + api, {
          method: 'POST',
          cache: 'no-cache',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({refresh: refreshToken})
        })
        const retour = await response.json()
        if (response.status === 200) {
          window.accessToken = retour.access
          this.me = await this.getMe(window.accessToken)
        } else {
          // reset all et local store
          this.$reset()
          const allStore = useAllStore()
          allStore.$reset()
          window.accessToken = ''
        }
      } catch (erreur) {
        emitter.emit('modalMessage', {
          titre: 'Erreur, maj accessToken !',
          contenu: `${domain + api} : ${erreur}`
        })
      }
    },
    setActivationAdhesion(value) {
      this.adhesion.activation = value
    },
    sychronizeMembershipWithObligationPlace() {
      const mainStore = useAllStore()
      if (mainStore.place.adhesion_obligatoire === true) {
        this.adhesion.activation = true
      }
    },
    setEtapeStripe(value) {
      this.stripeEtape = value
    },
    infosCardExist() {
      try {
        if (this.me.cashless?.cards !== undefined) {
          return true
        }
      } catch (err) {
        return false
      }
    },
    infosReservationExist() {
      try {
        if (this.me.reservations !== undefined && window.accessToken !== '') {
          return true
        }
      } catch (err) {
        return false
      }
    },
    // Jonas test pour ajouter lien admin dans menu
    isStaff() {
      try {
        if (this.me.is_staff !== undefined && window.accessToken !== '') {
          return this.me.is_staff
        }
      } catch (err) {
        return false
      }
    },
    asP() {
      try {
        if (this.me.as_p !== undefined && window.accessToken !== '') {
          return this.me.as_p
        }
      } catch (err) {
        return false
      }
    },
    // fin Jonas
    iamMembershipOwned(productUuid) {
      try {
        this.me.membership.find(obj => obj.product_uuid === productUuid).product_uuid
        return true
      } catch (e) {
        return false
      }
    }
  },
  getters: {
    getEmail: (state) => {
      return state.email
    }
  },
  persist: {
    key: 'Tibillet-local',
    storage: window.localStorage
  }
})
