import {defineStore} from 'pinia'

export const useStore = defineStore('store', {
  state: () => ({
    memoComposants: {},
    currentUuidEvent: '',
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
    events: {},
    formulaireBillet: {}
  }),
  persist: true
})