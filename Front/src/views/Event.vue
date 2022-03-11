<template>
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
        <CardArtist :data-artist="artist"/>
        <hr>
      </div>
    </div>
  </div>
{{ currentEvent }}
  <!-- achats -->
  <div class="container mt-5">
    <div class="row">
      <form @submit.prevent="goValiderAchats($event)" class="needs-validation" novalidate>

        <!-- <CardProfil :infos="store.formulaireBillet[uuidEvent]"/> -->

        <!--
        <Adhesion :adhesion="adhesion"/>

        <div v-for="produit in currentEvent.products" :key="produit.uuid">
          <CardBillet v-if="produit.categorie_article === 'B' && produit.publish === true" :data-product="produit"
                      :uuid-event="currentEvent.uuid"/>
        </div>
        <div class="col-md-12 col-lg-9">
          <button type="submit" class="btn bg-gradient-dark w-100">Valider la réservation</button>
        </div>
-->
      </form>
    </div>
  </div>
</template>

<script setup>
console.log('-> Event.vue !')

// vue
import {ref} from 'vue'
import {useRoute} from 'vue-router'

// composants
import Header from '@/components/Header.vue'
import CardPlace from '@/components/CardPlace.vue'
import CardArtist from '@/components/CardArtist.vue'
import CardProfil from "@/components/CardProfil.vue"

// store
import {useStore} from '@/store'

const route = useRoute()
const slug = route.params.slug
const store = useStore()
const domain = `${location.protocol}//${location.host}`
// const chargement = ref(true)
let currentEvent = {}

// récupération du uuid évènement à partir du slug
const uuidEventBrut = store.events.find(evt => evt.slug === slug).uuid
let uuidEvent = uuidEventBrut
// un retour de navigation("history")  donne un proxy et non un string
if (typeof (uuidEventBrut) === 'object') {
  // converti le proxy en string son type original avant le retour de navigation
  uuidEvent = JSON.parse(JSON.stringify(uuidEventBrut)).uuid
}

const urlApi = `/api/events/${uuidEvent}`
// chargement de l'évènement
console.log(`-> chargement de l'évènement urlApi =`, urlApi)
try {
  const response = await fetch(domain + urlApi)
  if (response.status !== 200) {
    throw new Error(`${response.status} - ${response.statusText}`)
  }
  const retour = await response.json()
  console.log('retour =', retour)
  // maj store events
  for (const key in store.events) {
    if (store.events[key].uuid === uuidEvent) {
      store.events[key] = retour
      currentEvent = retour
      break
    }
  }
} catch (erreur) {
  emitter.emit('message', {
    tmp: 4,
    typeMsg: 'danger',
    contenu: `Chargement de l'évènement ${uuidEvent}, erreur: ${erreur}`
  })
}
console.log('3 - currentEvent =', currentEvent)

function getDataHeader() {
  let urlImage
  try {
    urlImage = currentEvent.value.img_variations.med
  } catch (e) {
    urlImage = `${domain}/media/images/image_non_disponible.svg`
  }
  return {
    urlImage: urlImage,
    shortDescription: currentEvent.value.short_description,
    longDescription: currentEvent.value.long_description,
    titre: currentEvent.value.name,
    domain: domain
  }
}

function getDataCardPlace() {
  let urlImage
  try {
    urlImage = store.place.img_variations.med
  } catch (e) {
    urlImage = `${domain}/media/images/image_non_disponible.svg`
  }
  return {
    urlImage: urlImage,
    titre: store.place.organisation,
    lonDescription: store.place.long_description,
    shortDescription: store.place.short_description
  }
}

/*
// ---- gestion des évènements "emitter" ----
// écoute la fin du chargement de l'évènement
emitter.on('loading', (etat) => {
  if (etat === false) {
    // chargement.value = false
    // init formulaire si n'existe pas
    console.log('test init formulaireBillet =', store.formulaireBillet[uuidEvent])
    if (store.formulaireBillet[uuidEvent] === undefined) {
      store.formulaireBillet[uuidEvent] = {
        attentionEmail: false,
        email: '',
        confirmeEmail: '',
        position: 'fosse',
        identifiants: []
      }
      console.log('test après formulaireBillet =', store.formulaireBillet[uuidEvent])
    }
    // actualise les données
    currentEvent.value = store.events.find(evt => evt.slug === slug)
  }
})

// mise à jour du profil
emitter.on('emitUpdateProfil', (data) => {
  console.log('réception "emitUpdateProfil", data=', JSON.stringify(data, null, 2))
  store.formulaireBillet[uuidEvent][data.key] = data.value
})
*/
</script>

<style>
</style>