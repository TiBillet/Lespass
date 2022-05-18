// store
import {useLocalStore} from '@/stores/local'

const domain = `${location.protocol}//${location.host}`

// status 226 = 'Paiement validé. Création des billets et envoi par mail en cours.' côté serveur
// status 208 = 'Paiement validé. Billets envoyés par mail.'
// status 402 = pas payé
// status 202 = 'Paiement validé. Création des billets et envoi par mail en cours.' coté front
export function postStripeReturn(uuidStripe) {
  console.log(`-> fonc api postStripeReturn !`)

  // stockage adhesion en local
  const {adhesion} = useLocalStore()

  let messageValidation = 'OK', messageErreur = 'Retour stripe:'
  if ( adhesion.status === 'attente_stripe') {
    messageValidation = `<h2>Adhésion OK !</h2>`
    messageErreur = `Retour stripe pour l'adhésion:`
  }

  const apiStripe = `/api/webhook_stripe/`
  const options = {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({uuid: uuidStripe})
  }
  fetch(domain + apiStripe, options).then(response => {
    console.log('/api/webhook_stripe/ -> response =', response)
    // TODO: vérifier tous les status possible du serveur
    // if (response.status !== 202) {
    if (response.status !== 226) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    return response.json()
  }).then(retour => {
    // maj status adhésion
    adhesion.status = 'membership'
    console.log('/api/webhook_stripe/ -> retour =', retour)
    // message achat(s) ok
    emitter.emit('modalMessage', {
      titre: 'Succès',
      dynamique: true,
      contenu: messageValidation
    })
  }).catch(function (erreur) {
    adhesion.status = ''
    console.log('/api/webhook_stripe/ -> erreur: ', erreur)
    emitter.emit('modalMessage', {
      titre: 'Erreur',
      dynamique: true,
      contenu: `${messageErreur} ${erreur}`
    })
  })


}

/* 4242
export async function emailActivation(id, token) {
  // console.log('-> emailActivation')
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
      console.log('->  adhsesion(getMe) ?')
      getMe(window.accessToken)
      storeLocalSet('refreshToken', retour.refresh)
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
  console.log('-> fonc getMe, token =', token)
  const apiMe = `/api/user/me/`
  const options = {
    method: 'GET',
    cache: 'no-cache',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token} `
    }
  }
  emitter.emit('statusLoading', true)
  try {
    const response = await fetch(domain + apiMe, options)
    // console.log('response =', response)
    if (response.status === 200) {
      const retour = await response.json()
      emitter.emit('statusAdhesion', retour)
    } else {
      throw new Error(`Erreur ${apiMe} !`)
    }
  } catch (erreur) {
    console.log('-> getMe, erreur:', erreur)
    emitter.emit('message', {
      tmp: 6,
      typeMsg: 'warning',
      contenu: `${domain + apiMe} : ${erreur}`
    })
  }
  emitter.emit('statusLoading', false)
}

export async function refreshAccessToken(refreshToken) {
  console.log('-> refreshAccessToken, refreshToken =', refreshToken)
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
      getMe(window.accessToken)
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
 */