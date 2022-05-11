import {defineStore} from 'pinia'

export const useLocalStore = defineStore({
  id: 'local',
  state: () => ({
    email: '',
    refreshToken: '',
    membership: false,
    storeBeforeUseExternalUrl: {}
  }),
  persist: {
    key: 'Tibillet-local',
    storage: window.localStorage
  }
})