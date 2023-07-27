import { defineStore } from 'pinia'

import { useSessionStore } from '@/stores/session'
import { log } from '../../communs/LogError'

const domain = `${location.protocol}//${location.host}`
const initState = {
  initStore: false,
  refreshToken: '',
  me: {
    cashless: {},
    reservations: [],
    membership: []
  },
  stripeEtape: null
}

export const useLocalStore = defineStore('TiBillet-local', {
  state: () => (initState),
  getters: {
    getIsLogin (state) {
      return state.refreshToken !== '' ? true : false
    },
    getUserHasThisMembership (state) {
      return (membershipUuid) => {
        if (state.me.membership.length === 0) {
          return false
        } else {
          // TODO: vérifier que l'utilisateur a cette adhésion "membershipUuid"
          // attention dev, pas encore géré
          return true
        }
      }
    },
    getEmailStore (state) {
      return state.me?.email
    },
    getRefreshToken (state) {
      return state.refreshToken
    }
  },
  actions: {
    initLocalStore () {
      this.initStore = true
    },
    async automaticConnection () {
      console.log('-> automaticConnection')
      console.log('refreshToken =', this.refreshToken)
      if (window.accessToken === '' && this.refreshToken !== '') {

        const api = `/api/user/token/refresh/`
        try {
          const response = await fetch(domain + api, {
            method: 'POST',
            cache: 'no-cache',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ refresh: this.refreshToken })
          })
          const retour = await response.json()
          if (response.status === 200) {
            window.accessToken = retour.access
            this.me = await this.getMe(window.accessToken)
          }
        } catch (error) {
          log({ message: 'emailActivation, /api/user/activate/, error:', error })
          emitter.emit('modalMessage', {
            titre: 'Erreur, maj accessToken !',
            contenu: `${domain + api} : ${error.message}`
          })
        }

      }
    },
    disconnect () {
      console.log('-> disconnect')
      this.me = {
        cashless: {},
        reservations: [],
        membership: []
      }
      this.refreshToken = ''
    },
    async emailActivation (id, token) {
      console.log('emailActivation')
      const sessionStore = useSessionStore()
      // attention pas de "/" à la fin de "api"
      const api = `/api/user/activate/${id}/${token}`
      try {
        sessionStore.loading = true
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
          // info: email dans this.me.email

          sessionStore.loading = false
        } else {
          throw new Error(`Erreur conrfirmation mail !`)
        }
      } catch (error) {
        log({ message: 'emailActivation, /api/user/activate/, error:', error })
        sessionStore.loading = false
        emitter.emit('modalMessage', {
          titre: 'Erreur',
          typeMsg: 'danger',
          contenu: `Activation email : ${error.message}`
        })
        return {
          cashless: {},
          reservations: [],
          membership: []
        }
      }
    },
    async getMe (accessToken) {
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
          const retour = await response.json()
          return retour
        } else {
          throw new Error(`Erreur ${apiMe} !`)
        }
      } catch (error) {
        sessionStore.loading = false
        log({ message: 'getMe, /api/user/me/, error:', error })
        emitter.emit('modalMessage', {
          titre: 'Erreur',
          typeMsg: 'danger',
          contenu: `Obtention infos utilisateur, /api/user/me/ : ${error.message}`
        })
      }
    }
  },
  persist: true
})