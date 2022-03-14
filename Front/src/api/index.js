// store
import {useStore} from '@/store'

const domain = `${location.protocol}//${location.host}`

export async function loadPlace() {
  const store = useStore()
  const apiLieu = `/api/here/`
  try {
    const response = await fetch(domain + apiLieu)
    if (response.status !== 200) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    const retour = await response.json()
    store.place = retour
  } catch (erreur) {
    // console.log('Store, place, erreur:', erreur)
    emitter.emit('message', {
      tmp: 4,
      typeMsg: 'danger',
      contenu: `Chargement lieu, erreur: ${erreur}`
    })
  }
  console.log('2 - place =', store.place)
}

export async function loadEvents() {
  const store = useStore()
  const apiEvents = `/api/events/`
  try {
    const response = await fetch(domain + apiEvents)
    if (response.status !== 200) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    const retour = await response.json()
    store.events = retour
  } catch (erreur) {
    // console.log('Store, events, erreur:', erreur)
    emitter.emit('message', {
      tmp: 4,
      typeMsg: 'danger',
      contenu: `Chargement des évènements, erreur: ${erreur}`
    })
  }
  console.log('2 -> events =', store.events)
}

export async function loadEvent(slug) {
  const store = useStore()
  // récupération du uuid évènement à partir du slug
  const uuidEventBrut = store.events.find(evt => evt.slug === slug).uuid
  let uuidEvent = uuidEventBrut
  // un retour de navigation("history")  donne un proxy et non un string
  if (typeof (uuidEventBrut) === 'object') {
    // converti le proxy en string son type original avant le retour de navigation
    uuidEvent = JSON.parse(JSON.stringify(uuidEventBrut)).uuid
  }

  // récupération du uuid évènement à partir du slug
  const urlApi = `/api/events/${uuidEvent}`
  try {
    const response = await fetch(domain + urlApi)
    if (response.status !== 200) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    const retour = await response.json()
    // console.log('retour =', retour)
    // maj store events
    for (const key in store.events) {
      if (store.events[key].uuid === uuidEvent) {
        store.events[key] = retour
        break
      }
    }
  } catch (erreur) {
    emitter.emit('message', {
      tmp: 4,
      typeMsg: 'danger',
      contenu: `Chargement de l'évènement ${uuidEvent}, erreur: ${erreur}`
    })
  }
}

export async function emailActivation(id, token) {
  // console.log('-> emailActivation')
  const store = useStore()
  // attention pas de "/" à la fin de "api"
  const api = `/api/user/activate/${id}/${token}`
  try {
    const response = await fetch(domain + api, {
      method: 'GET',
      cache: 'no-cache', // *default, no-cache, reload, force-cache, only-if-cached
      headers: {
        'Content-Type': 'application/json'
      }
    })
    // console.log('-> response =', response)
    if (response.status === 200) {
      const retour = await response.json()
      // message confirmation email
      emitter.emit('modalMessage', {
        titre: 'Succès',
        contenu: 'Utilisateur activé / connecté !'
      })
      // maj token d'accès
      window.accessToken = retour.access
      // get infos user
      store.user = await this.getMe(retour.access)
      // maj du refresh token dans le storeUser
      store.user['refreshToken'] = retour.refresh
    } else {
      throw new Error(`Erreur conrfirmation mail !`)
    }
  } catch (erreur) {
    emitter.emit('message', {
      tmp: 6,
      typeMsg: 'warning',
      contenu: `${domain + api} : ${erreur}`
    })
  }
}

export async function getMe(token) {
  const apiMe = `/api/user/me/`
  const options = {
    method: 'GET',
    cache: 'no-cache',
    headers: {
      'Content-Type': 'application/json',
      'Authorization' : `Bearer ${token}`
    }
  }
  try {
    const response = await fetch(domain + apiMe, options)
    if (response.status === 200) {
      const retour = await response.json()
      return retour
    } else {
      throw new Error(`Erreur ${apiMe} !`)
    }
  } catch (erreur) {
    emitter.emit('message', {
      tmp: 6,
      typeMsg: 'warning',
      contenu: `${domain + apiMe} : ${erreur}`
    })
  }
}

export function getStripeReturn(uuidStripe) {
  console.log(`-> charge getReservations !`)
  const apiStripe = `/api/webhook_stripe/`
  const options = {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Token': window.accessToken
    },
    body: JSON.stringify({uuid: uuidStripe})
  }
  fetch(domain + apiStripe, options).then(response => {
    console.log('response =', response)
    if (response.status !== 200) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    return response.json()
  }).then(retour => {
    console.log('retour =', retour)
    // TODO: modal = achat(s) ok !
    // message achat(s) ok
    emitter.emit('modalMessage', {
      titre: 'Succès',
      contenu: 'Réservation OK !'
    })
  }).catch(function (erreur) {
    emitter.emit('message', {
      tmp: 6,
      typeMsg: 'danger',
      contenu: `Retour achat(s) stripe, erreur: ${erreur}`
    })
  })
}

export async function refreshAccessToken(refreshToken) {
  // console.log('-> refreshAccessToken, refreshToken =', refreshToken)
  const api = `/api/user/token/refresh/`
  try {
    const response = await fetch(domain + api, {
      method: 'POST',
      cache: 'no-cache',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({refresh: refreshToken})
    })
    const retour = await response.json()
    if (response.status === 200) {
      window.accessToken = retour.access
    } else {
      throw new Error(`Erreur obtention nouvel "access token" !`)
    }
  } catch (erreur) {
    emitter.emit('message', {
      tmp: 8,
      typeMsg: 'warning',
      contenu: `${domain + api} : ${erreur}`
    })
    window.accessToken = ''
  }
}

export function getReservations() {
  console.log(`-> charge getReservations !`)
  const apiReservations = `/api/reservations/`
  const options = {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      'Token': window.accessToken
    }
  }
  fetch(domain + apiReservations, options).then(response => {
    console.log('response =', response)
    /*
    if (response.status !== 200) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }

     */
    return response.json()
  }).then(retour => {
    console.log('retour =', retour)
  }).catch(function (erreur) {
    emitter.emit('message', {
      tmp: 6,
      typeMsg: 'danger',
      contenu: `Liste des réservations, erreur: ${erreur}`
    })
  })
}

