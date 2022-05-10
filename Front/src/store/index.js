import {defineStore} from 'pinia'

// session storage
export const useStore = defineStore({
  id: 'store',
  state: () => ({
    language: 'fr',
    currentUuidEvent: '',
    memoComposants: {},
    adhesion: false,
    place: {},
    events: []
  }),
  persist: {
    key: 'Tibillet',
    storage: window.sessionStorage
  }
})
