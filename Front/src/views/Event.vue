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
        <div v-for="(artist, index) in currentEvent.artists" :key="index" class="col-lg-4 mb-lg-0 mb-4">
          <CardArtist :data-artist="artist" />
          <hr>
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
// vue
import {ref} from 'vue'
import {useStore} from 'vuex'
import {useRoute} from 'vue-router'

// composants
import Header from '../components/Header.vue'
import CardPlace from '../components/CardPlace.vue'
import CardArtist from '../components/CardArtist.vue'

let chargement = ref(true)

const store = useStore()
const route = useRoute()
const slug = route.params.slug

// récupération du uuid évènement à partir du slug
const uuidEvent = store.state.events.find(evt => evt.slug === slug).uuid

// récupère l'évènement à jour
let currentEvent = store.getters.getEventBySlug(slug)


console.log('artists = ', currentEvent.artists)

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
</script>

<style scoped>

</style>