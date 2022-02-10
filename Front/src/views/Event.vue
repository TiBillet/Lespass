<template>

  <section v-if="chargement">
    <div class="position-relative d-flex justify-content-center align-items-center vw-100 vh-100">
      <h1>Chargement des données !</h1>
      <div class="position-absolute d-flex justify-content-center align-items-center vw-100 vh-100">
        <div class="spinner-border text-success" role="status" style="width: 10rem; height: 10rem;"></div>
      </div>
    </div>
  </section>
  <section v-if="!chargement">
    <Header :data-header="getDataHeader()"/>
    <div class="container mt-7">
      <!-- lieu -->
      <div class="row">
        <div class="col-lg-12">
          <CardPlace :data-card="getDataCardPlace()"/>
        </div>
      </div>
      <!-- artistes -->
      <div class="row mt-5">
        <div v-for="artist in currentEvent.artists" class="col-lg-4 mb-lg-0 mb-4">
          <CardArtiste :data-artist="artist" />
        </div>
      </div>
    </div>
  </section>

  <!--


  // liste des produits de l'évènement
  <ProductsList :event="currentEvent" />
-->
</template>

<script setup>
import {ref} from 'vue'
import {useStore} from 'vuex'
import {useRoute} from 'vue-router'

// composants
import Header from '../components/Header.vue'
import CardPlace from '../components/CardPlace.vue'
import CardArtiste from '../components/CardArtiste.vue'

let chargement = ref(true)

const store = useStore()
const route = useRoute()
const slug = route.params.slug

// récupération du uuid évènement à partir du slug
const uuidEvent = store.state.events.find(evt => evt.slug === slug).uuid

// récupère l'évènement à jour
let currentEvent = store.getters.getEventBySlug(slug)

const domain = `${location.protocol}//${location.host}`

// chargement de l'évènement
const urlApi = `/api/events/${uuidEvent}`
fetch(domain + urlApi).then(response => {
  if (!response.ok) {
    throw new Error(`${response.status} - ${response.statusText}`)
  }
  return response.json()
}).then(retour => {
  console.log('retour event =', retour)
  store.commit('updateEvent', retour)
  chargement.value = false

}).catch(function (erreur) {
  emitter.emit('message', {
    tmp: 4,
    typeMsg: 'danger',
    contenu: `Chargement de l'évènement ${uuidEvent}, erreur: ${erreur}`
  })
})

function getDataHeader() {
  return {
    urlImage: currentEvent.img_variations.med,
    shortDescription: currentEvent.short_description,
    longDescription: currentEvent.long_description,
    titre: currentEvent.name,
    domain: domain
  }
}

function getDataCardPlace() {
  return {
    urlImage: store.state.place.img_variations.med,
    titre: store.state.place.organisation,
    lonDescription: store.state.place.long_description,
    shortDescription: store.state.place.short_description
  }

}

/*
// composants
import Header from '../components/Header.vue'


import ProductsList from '../components/ProductsList.vue'

const emitter = mitt()

let place = store.state.place

// reset emitter
// emitter.all.clear()

// charge l'évènemet et le met à jour dans le state
store.dispatch('loadEventBySlug', slug)

// récupère l'évènement à jour
let currentEvent = store.getters.getEventBySlug(slug)

let dataHeader = {
  urlImage: currentEvent.img,
  shortDescription: currentEvent.short_description
}

let dataCardPlace = {
  urlImage: place.img,
  titre: place.organisation,
  lonDescription: place.long_description
}
*/
</script>

<style scoped>

</style>