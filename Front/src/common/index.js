import {getCurrentInstance} from 'vue'
// store
import {useStore} from '@/store'

const domain = `${location.protocol}//${location.host}`

/*
export function getVueGlobal() {
  return getCurrentInstance().appContext.config.globalProperties
}
*/

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
      // maj du refresh token dans le storeUser
      store.user.refreshToken = retour.refresh
      // maj token d'accès
      window.accessToken = retour.access
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

export async function getReservations() {
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

export async function getStripeReturn(uuidStripe) {
  console.log(`-> charge getReservations !`)
  const apiStripe = `/api/webhook_stripe/`
  const options = {
    method: 'Post',
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