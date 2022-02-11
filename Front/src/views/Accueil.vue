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
  <section v-if="!chargement">

    <Header :data-header="getDataHeader()"/>
    <section class="pt-5 pb-0">
      <div class="container">
        <div class="row">
          <div class="col-lg-4 col-md-6 mb-2" v-for="(item, index) in store.state.events" :key="index">
            <CardEvent :infos="item"/>
          </div>
        </div>
      </div>
    </section>
    <section class="pt-5 pb-0">
      <div id="calendar" class="container">
        <Calendar categorie-article="B"/>
      </div>
    </section>
  </section>
</template>

<script setup>
console.log('-> Accueil.vue')
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
import {ref} from 'vue'
import {useStore} from 'vuex'
import {useRouter} from 'vue-router'


// composants
import Header from '../components/Header.vue'
import CardEvent from '../components/CardEvent.vue'
import Calendar from '../components/Calendar.vue'

const store = useStore()
const router = useRouter()

console.log('place =', store.state.place)

const chargement = ref(true)
const nbMaxChargement = 3
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
  if (nbChargement === nbMaxChargement) {
    chargement.value = false
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

// aller à la page évènement (lien défini si-dessous et dans le store) => /views/Event.vue
emitter.on('goEvenement', (slug) => {
  console.log('-> Emmiter, écoute, slug =', slug, '  --  type =', typeof (slug))
  router.push({name: 'Event', params: {slug: slug}})
})
</script>

<style>
</style>
