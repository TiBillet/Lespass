import {createStore} from 'vuex'
import createPersistedState from 'vuex-persistedstate'

export default createStore({
  state: {
    refreshToken: '',
    chargement: false,
    formulaireBillet: {},
    events: [],
    place: {},
    profil: {
      email: '',
      confirmeEmail: '',
      attentionEmail: false
    },
    adhesion: {
      nom: '',
      prenom: '',
      adresse: '',
      tel: null
    }
  },
  plugins: [createPersistedState()],
  mutations: {
    resetState(state) {
      state = {
        formulaire: {},
        events: [],
        place: {}
      }
    },
    initPlace(state, data) {
      state.place = data
    },
    initEvents(state, data) {
      state.events = data
    },
    initProducts(state, data) {
      state.products = data
    },
    updateRefreshToken(state, token) {
      state.refreshToken = token
    },
    updateProfilEmail(state, email) {
      state.profil.email = email
      state.profil.confirmeEmail = email
      state.profil.attentionEmail = true
    },
    resetFormulaires(state) {
      state.formulaire = {}
    },
    initFormulaireBillet(state, uuidEvent) {
      state.formulaireBillet[uuidEvent] = {
        email: '',
        confirmeEmail: '',
        attentionEmail: false,
        position: 'fosse',
        adhesion: false,
        adhesionInfos: {},
        identifiants: []
      }
    },
    majFormulaireBilletAdhesionActive(state, data) {
      state.formulaireBillet[data.uuidEvent].adhesion = data.valeur
    },
    majFormulaireBillet(state, data) {
      console.log('-> store, majFormulaire, data =', data)
      if (data.sujet.indexOf('.') === -1) {
        state.formulaireBillet[data.uuidEvent][data.sujet] = data.valeur
      } else {
        // le sujet se trouve après le point
        const sujet = data.sujet.split('.')[1]
        // adhésion
        if (data.sujet.includes('adhesion') === true) {
          state.formulaireBillet[data.uuidEvent].adhesionInfos[sujet] = data.valeur
        }
      }
      // console.log('formulaire = ', state.formulaireBillet)
    },
    alerteReseau(state, data) {
      state.erreurReseau = data
    },
    updateEvent(state, data) {
      const uuidEvent = data.uuid
      for (const key in state.events) {
        // maj de l'évènement avec "data"
        if (state.events[key].uuid === uuidEvent) {
          state.events[key] = data
          break
        }
      }
    },
    supprimerIdentifiant(state, data) {
      state.formulaireBillet[data.uuidEvent].identifiants = state.formulaireBillet[data.uuidEvent].identifiants.filter(ele => ele.id !== data.id)
    },
    ajouterIdentiant(state, data) {
      // console.log('store, ajouterIdentiant, data =', data)
      const tarifs = state.formulaireBillet[data.uuidEvent].identifiants.filter(iden => iden.uuidTarif === data.uuidTarif)
      if (tarifs.length + 1 <= data.max) {
        state.formulaireBillet[data.uuidEvent].identifiants.push({
          id: Date.now(),
          uuidTarif: data.uuidTarif,
          nom: '',
          prenom: ''
        })
      }
    },
    majIdentifiant(state, data) {
      // console.log('store, majIdentifiant, data =', data)
      state.formulaireBillet[data.uuidEvent].identifiants.find(ele => (ele.id === data.id))[data.champ] = data.valeur
    },
    updateProfil(state, data) {
      state.profil = data
    }
  },
  getters: {
    getEventBySlug: (state) => (slug) => {
      // console.log('--- getEventBySlug ---')
      return state.events.find(evt => evt.slug === slug)
    }
  },
  actions: {},
  modules: {}
})
