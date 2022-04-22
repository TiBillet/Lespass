// store
import {useStore} from '@/store'

// myStore
import {StoreLocal} from '@/divers'

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
    console.log('Store, events, erreur:', erreur)
    emitter.emit('message', {
      tmp: 4,
      typeMsg: 'danger',
      contenu: `Chargement des évènements, erreur: ${erreur}`
    })
  }

}

export async function loadEventBySlug(slug) {
  console.log('-> fonction loadEventBySlug !')
  const store = useStore()
  console.log('store.events =', store.events)
  try {
    // récupération du uuid évènement à partir du slug
    const urlApi = `/api/eventslug/${slug}`

    const response = await fetch(domain + urlApi)
    if (response.status !== 200) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    const retour = await response.json()
    console.log('retour =', retour)
    // maj store events
    // TODO: remplacer le code si_dessous par la fonction .find()
    if (store.currentUuidEvent !== undefined) {
      for (const key in store.events) {
        if (store.events[key].uuid === store.currentUuidEvent) {
          store.events[key] = retour
          break
        }
      }
    }
  } catch (erreur) {
    console.log('Store, event(slug), erreur:', erreur)
    emitter.emit('message', {
      tmp: 4,
      typeMsg: 'danger',
      contenu: `Chargement de l'évènement '${slug}', erreur: ${erreur}`
    })
  }
}

export async function emailActivation(id, token) {
  // console.log('-> emailActivation')
  const storeLocal = StoreLocal.use('localStorage', 'Tibilet-identite')

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
      storeLocal.refreshToken = retour.refresh
      emitter.emit('statusConnection', true)
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
      // console.log('retour =', JSON.stringify(retour, null, 2))
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

// status 226 = 'Paiement validé. Création des billets et envoi par mail en cours.' côté serveur
// status 208 = 'Paiement validé. Billets envoyés par mail.'
// status 402 = pas payé
// status 202 = 'Paiement validé. Création des billets et envoi par mail en cours.' coté front
export function postStripeReturn(uuidStripe) {
  console.log(`-> fonc api postStripeReturn !`)
  const store = useStore()
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
    console.log('/api/webhook_stripe/ -> response =', response)
    // TODO: vérifier tous les status possible du serveur
    // if (response.status !== 202) {
    if (response.status !== 226) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    return response.json()
  }).then(retour => {

    console.log('/api/webhook_stripe/ -> retour =', retour)
    // store.$state = { counter: 666, name: 'Paimon' }
    const piniaCache = JSON.parse(window.sessionStorage.getItem('Tibillet'))
    console.log('piniaCache =', piniaCache)
    console.log('store.memoComposants =', store.memoComposants)
    // vider les contenus du memoComposants de l'évènement courant
    const memoComponentsProperty = ['CardAdhesion', 'Don', 'Options', 'CardBillet']
    for (let i = 0; i < memoComponentsProperty.length; i++) {
      const property = memoComponentsProperty[i]
      console.log('property =', property)
      delete store.memoComposants[property][store.currentUuidEvent]
      console.log(`store.memoComposants.${property} =`, store.memoComposants[property])
      console.log('--------------')
    }

    // message achat(s) ok
    emitter.emit('modalMessage', {
      titre: 'Succès',
      dynamique: true,
      contenu: '<h2>Validation OK !<h2>'
    })
  }).catch(function (erreur) {
    console.log('/api/webhook_stripe/ -> erreur: ', erreur)
    emitter.emit('message', {
      tmp: 6,
      typeMsg: 'danger',
      contenu: `Retour achat(s) stripe, erreur: ${erreur}`
    })
  })
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

export function postAdhesionModal(data) {
  console.log(`-> fonc postAdhesionModal !`)
  const apiMemberShip = `/api/membership/`
  const options = {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Token': window.accessToken
    },
    body: JSON.stringify(data)
  }

  console.log('options =', JSON.stringify(options, null, 2))
  fetch(domain + apiMemberShip, options).then(response => {
    console.log('response =', response)
    if (response.status !== 201) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    return response.json()
  }).then(retour => {
    // console.log('retour =', retour)

    // sauver état du store(session) pour nouvel onglet ou page(entraine nouvelle session "storage") redirigé par stripe
    const store = useStore()
    const storeLocal = StoreLocal.use('localStorage', 'Tibilet-identite')
    storeLocal.storeBeforeUseExternalUrl = store.memoComposants

    // redirection stripe formulaire paiement
    window.location = retour.checkout_url
  }).catch(function (erreur) {
    console.log('erreur =', erreur)
    emitter.emit('message', {
      tmp: 10,
      typeMsg: 'danger',
      contenu: `Retour adhésion, erreur: ${erreur}`
    })
  })

}
