import {createStore} from 'vuex'
import createPersistedState from 'vuex-persistedstate'

export default createStore({
  state: {
    token: '',
    chargement: false,
    formulaire: {},
    events: [],
    place: {},
    products: []
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
    updateToken(state, data) {
      state.token = data
    },
    resetFormulaires(state) {
      state.formulaire = {}
    },
    initFormulaire(state, uuidEvent) {
      state.formulaire[uuidEvent] = {
        email: '',
        confirmeEmail: '',
        attentionEmail: false,
        position: 'fosse',
        adhesion: false,
        adhesionInfos: {},
        identifiants: []
      }
    },
    majFormulaireAdhesionActive(state, data) {
      state.formulaire[data.uuidEvent].adhesion = data.valeur
    },
    majFormulaire(state, data) {
      console.log('-> store, majFormulaire, data =', data)
      if (data.sujet.indexOf('.') === -1) {
        state.formulaire[data.uuidEvent][data.sujet] = data.valeur
      } else {
        // le sujet se trouve après le point
        const sujet = data.sujet.split('.')[1]
        // adhésion
        if (data.sujet.includes('adhesion') === true) {
          state.formulaire[data.uuidEvent].adhesionInfos[sujet] = data.valeur
        }
      }
      // console.log('formulaire = ', state.formulaire)
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
      state.formulaire[data.uuidEvent].identifiants = state.formulaire[data.uuidEvent].identifiants.filter(ele => ele.id !== data.id)
    },
    ajouterIdentiant(state, data) {
      // console.log('store, ajouterIdentiant, data =', data)
      const tarifs = state.formulaire[data.uuidEvent].identifiants.filter(iden => iden.uuidTarif === data.uuidTarif)
      if (tarifs.length + 1 <= data.max) {
        state.formulaire[data.uuidEvent].identifiants.push({
          id: Date.now(),
          uuidTarif: data.uuidTarif,
          nom: '',
          prenom: ''
        })
      }
    },
    majIdentifiant(state, data) {
      // console.log('store, majIdentifiant, data =', data)
      state.formulaire[data.uuidEvent].identifiants.find(ele => (ele.id === data.id))[data.champ] = data.valeur
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
