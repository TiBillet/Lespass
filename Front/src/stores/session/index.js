// store
import { defineStore } from "pinia"
import { getLocalStateKey, setLocalStateKey } from "../../communs/storeLocal.js"
import { sessionActions} from "./SessionActions"
import { sessionGetters } from "./SessionGetters"

export const useSessionStore = defineStore({
  id: 'session',
  state: () => ({
    accessToken: '',
    identitySite: true,
    loading: false,
    language: 'fr',
    routeName: '',
    header: null,
    membershipProducts: [],
    event: null,
    me: {
      cashless: {},
      reservations: [],
      membership: [],
      email: ''
    },
    forms: []
  }),
  getters: sessionGetters,
  actions: sessionActions,
  persist: {
    key: 'Tibillet-session',
    storage: window.sessionStorage
  }
})