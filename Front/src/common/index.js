import {getCurrentInstance} from 'vue'

const domain = `${location.protocol}//${location.host}`

export function getVueGlobal() {
  return getCurrentInstance().appContext.config.globalProperties
}

export async function emailActivation(id, token) {
  // attention pas de "/" à la fin de "api"
  const api = `/api/user/activate/${id}/${token}`
  let etape = 0
  try {
    const response = await fetch(domain + api, {
      method: 'GET',
      cache: 'no-cache', // *default, no-cache, reload, force-cache, only-if-cached
      headers: {
        'Content-Type': 'application/json'
      }
    })
    console.log('response =', response)
    if (response.status === 200) {
      const retour = await response.json()
      console.log('retour =', JSON.stringify(retour, null, 2))
      etape = 1
      // maj du refresh token dans le store
      emitter.emit('updateRefreshToken', retour.refresh)
      // maj token d'accès
      window.accessToken = retour.access
      // maj navbar
      emitter.emit('majNavBar')
    } else {
      // efface l'émail si pas confirmé
      // emitter.emit('updateProfilEmail', '')
      throw new Error(`Erreur conrfirmation mail !`)
    }
  } catch (erreur) {
    emitter.emit('message', {
      tmp: 6,
      typeMsg: 'warning',
      contenu: `Erreur, ${domain + api} : ${erreur}`
    })
  }
}

export async function refreshAccessToken(refreshToken) {
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
    if (response.status !== 200) {
      throw new Error(`Erreur obtention nouvel "access token" !`)
    }
    const retour = await response.json()
    if (response.status === 200) {
      window.accessToken = retour.accesss
      return true
    }
  } catch (erreur) {
    emitter.emit('message', {
      tmp: 8,
      typeMsg: 'warning',
      contenu: `Erreur, ${domain + api} : ${erreur}`
    })
    return false
  }
}