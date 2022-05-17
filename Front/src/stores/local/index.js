import {defineStore} from 'pinia'

export const useLocalStore = defineStore({
  id: 'local',
  state: () => ({
    email: '',
    refreshToken: '',
    storeBeforeUseExternalUrl: {},
    adhesion: {
      email: '',
      first_name: '',
      last_name: '',
      phone: null,
      postal_code: null,
      adhesion: '',
      status: ''
    }
  }),
  persist: {
    key: 'Tibillet-local',
    storage: window.localStorage
  }
})