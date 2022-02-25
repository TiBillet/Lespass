<template>
  <h1>Corfirmation email</h1>
</template>

<script setup>
console.log('-> EmailConfirmation.vue !')
// vue
import {useStore} from 'vuex'
import {useRoute} from 'vue-router'

// common
import {getVueGlobal, verifyToken} from '@/common'

const store = useStore()
const route = useRoute()
const idActivate = route.params.id
const tokenActivate = route.params.token
const domain = `${location.protocol}//${location.host}`
// pour accéder à la variable "acces" définie dans main.js
const getGlobalApp = getVueGlobal()


console.log('route =', route.name)

console.log('store.state.refreshToken = ->'+store.state.refreshToken+'<-')
if (store.state.refreshToken === '') {

// attention pas de "/" à la fin de "api"
  const api = `/api/user/activate/${idActivate}/${tokenActivate}`
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
      store.commit('updateRefreshToken', retour.refresh)
      // maj navbar
      emitter.emit('infoMajRefreshToken')
      // maj token
      getGlobalApp.access = retour.access
      console.log('this =', getGlobalApp.access)
    } else {
      // efface l'émail si pas confirmé
      store.commit('updateProfilEmail', '')
      emitter.emit('message', {
        tmp: 6,
        typeMsg: 'warning',
        contenu: `Erreur conrfirmation mail "${store.state.profil.email}" !`
      })
    }
  } catch (erreur) {
    emitter.emit('message', {
      tmp: 6,
      typeMsg: 'warning',
      contenu: `Erreur, ${domain + api} : ${erreur}`
    })
  }
} else {
  console.log('-> verifyToken !!')
  // verifyToken()
}

</script>

<style scoped>

</style>