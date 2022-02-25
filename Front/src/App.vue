<template>
  <!-- avant chargement -->
  <section v-if="chargement">
    <div class="position-relative d-flex justify-content-center align-items-center vw-100 vh-100">
      <h1>Chargement des données !</h1>
      <div class="position-absolute d-flex justify-content-center align-items-center vw-100 vh-100">
        <div class="spinner-border text-success" role="status" style="width: 10rem; height: 10rem;"></div>
      </div>
    </div>
  </section>
  <!-- après chargement -->
  <!--  <section v-if="!chargement">-->
  <section v-else>
    <Message/>
    <div class="espace-navbar"></div>
    <Navbar :data-header="getDataHeader()"/>
    <router-view></router-view>
    <Footer :data-header="getDataHeader()"/>
  </section>
</template>

<script setup>
// bootstrap (ui)
import './assets/js/core/popper.min.js'
import './assets/js/core/bootstrap.bundle.min.js'
// en attente (erreur t n'est pas défini)
import './assets/js/plugins/perfect-scrollbar.js'
import './assets/js/now-design-system-pro.js'

// Nucleo Icons (ui)
import './assets/css/nucleo-icons.css'
import './assets/css/nucleo-svg.css'

// css (ui)
import './assets/css/now-design-system-pro.min.css'

// vue
import {ref} from 'vue'
import Message from './components/Message.vue'
import {useStore} from 'vuex'


// composants
import Navbar from './components/Navbar.vue'
import Footer from './components/Footer.vue'

const store = useStore()

const chargement = ref(true)
let nbMaxChargement = 0
let nbChargement = 0
const domain = `${location.protocol}//${location.host}`

function getDataHeader() {
  return {
    urlImage: store.state.place.img_variations.med,
    shortDescription: store.state.place.short_description,
    longDescription: store.state.place.long_description,
    logo: store.state.place.logo_variations.med,
    titre: store.state.place.organisation,
    domain: `${location.protocol}//${location.host}`
  }
}

function verifierEtatChargement() {
  nbChargement++
  console.log('-> verifierEtatChargement, nbChargement =', nbChargement, '  --  nbMaxChargement =', nbMaxChargement)
  if (nbChargement === nbMaxChargement) {
    chargement.value = false
  }
}

// chargement infos lieu
nbMaxChargement++
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
nbMaxChargement++
let apiEvents = `/api/events/`
// console.log(`2 -> charge les évènements ${domain + apiEvents}`)
fetch(domain + apiEvents).then(response => {
  if (!response.ok) {
    throw new Error(`${response.status} - ${response.statusText}`)
  }
  return response.json()
}).then(json => {
  // console.log('events =', JSON.stringify(json, null, 2))
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
nbMaxChargement++
let apiProducts = `/api/products/`
// console.log(`3 -> charge les produits ${domain + apiProducts}`)
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

emitter.on('updateRefreshToken', (refreshToken) => {
  console.log('-> emitter écoute "updateRefreshToken" !')
  store.commit('updateRefreshToken', refreshToken)
})

</script>
<style>
.espace-navbar {
  margin-bottom: 72px;
}
</style>
