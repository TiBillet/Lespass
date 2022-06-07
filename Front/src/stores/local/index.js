import {defineStore} from 'pinia'
import {useAllStore} from '@/stores/all'

const domain = `${location.protocol}//${location.host}`

export const useLocalStore = defineStore({
  id: 'local',
  state: () => ({
    refreshToken: '',
    me: {
      cashless: {},
      reservations: {}
    },
    stripeEtape: ''
  }),
  actions: {
    // status 226 = 'Paiement validé. Création des billets et envoi par mail en cours.' côté serveur
    // status 208 = 'Paiement validé. Billets envoyés par mail.'
    // status 402 = pas payé
    // status 202 = 'Paiement validé. Création des billets et envoi par mail en cours.' coté front
    async postStripeReturn(uuidStripe) {
      console.log(`-> fonc postStripeReturn !`)

      let messageValidation = 'OK', messageErreur = 'Retour stripe:'

      // adhésion
      if (this.stripeEtape === 'attente_stripe_adhesion') {
        messageValidation = `<h2>Adhésion OK !</h2>`
        messageErreur = `Retour stripe pour l'adhésion:`
      }

      // reservation(s)
      if (this.stripeEtape === 'attente_stripe_reservation') {
        messageValidation = `<h2>Réservation(s) OK !</h2>`
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
          contenu: messageValidation
        })
      }).catch(function (erreur) {
        this.stripeEtape = ''
        console.log('/api/webhook_stripe/ -> erreur: ', erreur)
        emitter.emit('modalMessage', {
          titre: 'Erreur',
          dynamic: true,
          contenu: `${messageErreur} ${erreur}`
        })
      })

    },
    async emailActivation(id, token) {
      console.log('store, all/index.js -> emailActivation')
      // console.log('-> id =', id)
      // console.log('-> token =', token)

      const mainStore = useAllStore()

      // attention pas de "/" à la fin de "api"
      const api = `/api/user/activate/${id}/${token}`
      try {
        mainStore.loading = true
        console.log('deb -> mainStore.loading =', mainStore.loading)
        const response = await fetch(domain + api, {
          method: 'GET',
          cache: 'no-cache', // *default, no-cache, reload, force-cache, only-if-cached
          headers: {
            'Content-Type': 'application/json'
          }
        })
        // console.log('-> response =', response)
        if (response.status === 200) {
          const retour = await response.json()
          // message confirmation email
          emitter.emit('modalMessage', {
            titre: 'Succès',
            contenu: 'Utilisateur activé / connecté !'
          })
          // maj token d'accès
          window.accessToken = retour.access
          this.refreshToken = retour.refresh
          this.me = await this.getMe(window.accessToken)
          // console.log('-> retourMe:', retourMe)
          mainStore.loading = false
        } else {
          throw new Error(`Erreur conrfirmation mail !`)
        }
      } catch (erreur) {
        console.log(`emailActivation, erreur: ${erreur}`)
        mainStore.error = erreur
        emitter.emit('modalMessage', {
          titre: 'Erreur',
          contenu: `Activation email : ${erreur}`
        })
      }
      console.log('fin -> loading =', mainStore.loading)
    },
    async getMe(accessToken) {
      // console.log('-> action getMe, accessToken =', accessToken)
      const apiMe = `/api/user/me/`
      const options = {
        method: 'GET',
        cache: 'no-cache',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${accessToken} `
        }
      }
      try {
        const response = await fetch(domain + apiMe, options)
        // console.log('response =', response)
        if (response.status === 200) {
          return await response.json()
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
        if (this.me.cashless.cards !== undefined) {
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
    }
  },
  persist: {
    key: 'Tibillet-local',
    storage: window.localStorage
  }
})
