import {defineStore} from 'pinia'

// session storage
export const useStore = defineStore('store', {
  state: () => ({
    currentUuidEvent: '',
    memoComposants: {},
    user: {
      refreshToken: '',
      email: '',
      first_name: '',
      last_name: '',
      phone: null,
      accept_newsletter: false,
      postal_code: null,
      birth_date: '',
      can_create_tenant: true,
      espece: "HU",
      is_staff: false,
      cashless: {},
      adhesion: ''
    },
    place: {},
    events: {}
  }),
  persist: {
    key: 'Tibillet',
    storage: window.sessionStorage
  }
})
