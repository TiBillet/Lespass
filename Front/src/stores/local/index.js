import {defineStore} from 'pinia'

const domain = `${location.protocol}//${location.host}`

export const useLocalStore = defineStore({
  id: 'local',
  state: () => ({
    email: '',
    refreshToken: '',
    storeBeforeUseExternalUrl: {}
  }),
  persist: {
    key: 'Tibillet-local',
    storage: window.localStorage
  }
})