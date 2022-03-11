import {defineStore} from 'pinia'

const domain = `${location.protocol}//${location.host}`

export const useStore = defineStore('store', {
  state: () => ({
    dataLoading: true,
    user: {
      refreshToken: '',
      email: '',
      nom: '',
      prenom: '',
      adresse: '',
      tel: null,
      adhesion: false,
      uuidPrice: '',
    },
    place: {},
    events: {},
    formulaireBillet: {}
  }),
  persist: true,
  actions: {
    async loadPlace(stopViewLoading) {
      const apiLieu = `/api/here/`
      try {
        const response = await fetch(domain + apiLieu)
        if (response.status !== 200) {
          throw new Error(`${response.status} - ${response.statusText}`)
        }
        const retour = await response.json()
        this.place = retour
      } catch (erreur) {
        console.log('Store, place, erreur:', erreur)
        emitter.emit('message', {
          tmp: 4,
          typeMsg: 'danger',
          contenu: `Chargement lieu, erreur: ${erreur}`
        })
      }
      /*
      this.dataLoading = true
      const apiLieu = `/api/here/`
      // console.log(`1 -> charge le lieu ${domain + apiLieu}`)
      fetch(domain + apiLieu).then((response) => {
        if (response.status !== 200) {
          throw new Error(`${response.status} - ${response.statusText}`)
        }
        return response.json()
      }).then((retour) => {
        this.place = retour
        console.log('stopViewLoading =', stopViewLoading)
        if (stopViewLoading === 'stopViewLoading') {
          this.dataLoading = false
        }
      }).catch((erreur) => {
        // console.log('Store, place, erreur:', erreur)
        emitter.emit('message', {
          tmp: 4,
          typeMsg: 'danger',
          contenu: `Chargement lieu, erreur: ${erreur}`
        })
      })
       */
    },
    loadEvents(stopViewLoading) {
      this.dataLoading = true
      const apiEvents = `/api/events/`
      // console.log(`2 -> charge les évènements ${domain + apiEvents}`)
      fetch(domain + apiEvents).then((response) => {
        if (response.status !== 200) {
          throw new Error(`${response.status} - ${response.statusText}`)
        }
        return response.json()
      }).then((retour) => {
        this.events = retour
        if (stopViewLoading === 'stopViewLoading') {
          this.dataLoading = false
        }
      }).catch((erreur) => {
        // console.log('Store, events, erreur:', erreur)
        emitter.emit('message', {
          tmp: 4,
          typeMsg: 'danger',
          contenu: `Chargement des évènements, erreur: ${erreur}`
        })
      })
    },
    loadEvent(uuidEvent, stopViewLoading) {
      console.log('-> loadEvent !')
      this.dataLoading = true
      const urlApi = `/api/events/${uuidEvent}`
      // chargement de l'évènement
      console.log(`-> chargement de l'évènement urlApi =`, urlApi)
      fetch(domain + urlApi).then((response) => {
        if (response.status !== 200) {
          throw new Error(`${response.status} - ${response.statusText}`)
        }
        return response.json()
      }).then((retour) => {
        console.log('retour =', retour)
        // maj store events
        for (const key in this.events) {
          if (this.events[key].uuid === uuidEvent) {
            this.events[key].uuid = retour
            break
          }
        }

        if (stopViewLoading === 'stopViewLoading') {
          this.dataLoading = false
        }

      }).catch((erreur) => {
        emitter.emit('message', {
          tmp: 4,
          typeMsg: 'danger',
          contenu: `Chargement de l'évènement ${uuidEvent}, erreur: ${erreur}`
        })
      })
    }
  }
})