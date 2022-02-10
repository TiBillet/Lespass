<template>
  <div class="position-relative d-flex justify-content-center align-items-center vw-100 vh-100">
    <h1>Chargement des données !</h1>
    <div class="position-absolute d-flex justify-content-center align-items-center vw-100 vh-100">
      <div class="spinner-border text-success" role="status" style="width: 10rem; height: 10rem;"></div>
    </div>
  </div>
</template>

<script setup>
// bootstrap (ui)
import '../assets/js/core/popper.min.js'
import '../assets/js/core/bootstrap.bundle.min.js'
// en attente (erreur t n'est pas défini)
// import './assets/js/plugins/perfect-scrollbar.min.js'

// Nucleo Icons (ui)
import '../assets/css/nucleo-icons.css'
import '../assets/css/nucleo-svg.css'

// css (ui)
import '../assets/css/now-design-system-pro.min.css'

// vue
import {useStore} from 'vuex'
import {useRouter} from 'vue-router'

const store = useStore()
const router = useRouter()
const nbMaxChargement = 3
let nbChargement = 0
const domain = `${location.protocol}//${location.host}`

function verifierEtatChargement() {
  nbChargement++
  if (nbChargement === nbMaxChargement) {
    router.push({name: 'Accueil'})
    // console.log('ok')
    // console.log('place =', store.state.place)
  }
}

// chargement infos lieu
let apiLieu = `/api/here/`
console.log(`1 -> charge le lieu ${domain + apiLieu}`)
fetch(domain + apiLieu)
    .then(response => {
      if (!response.ok) {
        throw new Error(`${response.status} - ${response.statusText}`)
      }
      return response.json()
    })
    .then(json => {
      store.commit('initPlace', json)
      verifierEtatChargement()
    })
    .catch(function (erreur) {
      emitter.emit('message', {
        tmp: 4,
        typeMsg: 'danger',
        contenu: `Chargement lieu, erreur: ${erreur}`
      })
    })

// chargement infos évènements
let apiEvents = `/api/events/`
console.log(`2 -> charge les évènements ${domain + apiEvents}`)
fetch(domain + apiEvents).then(response => {
  if (!response.ok) {
    throw new Error(`${response.status} - ${response.statusText}`)
  }
  return response.json()
}).then(json => {
  store.commit('initEvents', json)
  verifierEtatChargement()
}).catch(function (erreur) {
  emitter.emit('message', {
    tmp: 4,
    typeMsg: 'danger',
    contenu: `Chargement des évènements, erreur: ${erreur}`
  })
})

// chargement des prix
let apiProducts = `/api/products/`
console.log(`3 -> charge les produits ${domain + apiProducts}`)
fetch(domain + apiProducts).then(response => {
  if (!response.ok) {
    throw new Error(`${response.status} - ${response.statusText}`)
  }
  return response.json()
}).then(json => {
  store.commit('initProducts', json)
  verifierEtatChargement()
}).catch(function (erreur) {
  emitter.emit('message', {
    tmp: 4,
    typeMsg: 'danger',
    contenu: `Chargement des prix, erreur: ${erreur}`
  })
})


</script>

<style>
</style>
