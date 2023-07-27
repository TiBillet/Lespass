import {defineStore} from 'pinia'
import {useAllStore} from '@/stores/all'
import {useEventStore} from '@/stores/event'

const domain = `${location.protocol}//${location.host}`

export const useLocalStore = defineStore({
  id: 'local',
  state: () => ({
    refreshToken: '',
    email: null,
    me: {
      cashless: {},
      reservations: [],
      membership: []
    },
    stripeEtape: null
  }),
  getters: {
    getIsLogin(state) {
      return state.refreshToken !== '' ? true : false
    },
    getUserHasThisMembership(state) {
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
    getEmail (state) {
      return state.email
    },
    getRefreshToken (state) {
      return state.refreshToken
    }
  },
  actions: {},
  persist: {
    key: 'Tibillet-local',
    storage: window.localStorage
  }
})
