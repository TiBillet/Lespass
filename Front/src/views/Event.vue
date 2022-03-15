<template>
  <Header :header-event="getHeaderEvent()"/>
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
  <!-- achats -->
  <div class="container mt-5">
    <div class="row">
      <form @submit.prevent="goValiderAchats($event)" class="needs-validation" novalidate>

        <CardProfil :infos="store.formulaireBillet[uuidEvent]"/>
        <CardProducts :products="currentEvent.products" :categories="['A', 'D']"/>
        <CardOptions :options="options"/>
        <CardProducts :products="currentEvent.products" :categories="['B']"/>
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
import CardProducts from "@/components/CardProducts.vue"
import CardOptions from "@/components/CardOptions.vue"

// test dev
import {getMe} from '@/api'
import {fakeEvent} from "../../tempo/fakeCurrentEventsTest"

// store
import {useStore} from '@/store'

const route = useRoute()
const slug = route.params.slug
const store = useStore()
const domain = `${location.protocol}//${location.host}`

// récupération du uuid évènement à partir du slug
const uuidEventBrut = store.events.find(evt => evt.slug === slug).uuid
let uuidEvent = uuidEventBrut
// un retour de navigation("history")  donne un proxy et non un string
if (typeof (uuidEventBrut) === 'object') {
  // converti le proxy en string son type original avant le retour de navigation
  uuidEvent = JSON.parse(JSON.stringify(uuidEventBrut)).uuid
}

// currentEvent production
const currentEvent = store.events.find(evt => evt.uuid === uuidEvent)

// currentEvent test dev
// const currentEvent = fakeEvent

console.log('currentEvent =', currentEvent)

store.currentUuidEvent = uuidEvent

// init mémoristation formulaire en fonction de l'évènement en cours
if (store.formulaireBillet[store.currentUuidEvent] === undefined) {
  store.formulaireBillet[store.currentUuidEvent] = {
    attentionEmail: false,
    email: '',
    confirmeEmail: ''
  }
}

// populate profil card if user connected
console.log('store.user.refreshToken =', store.user.refreshToken)
if (store.user.refreshToken !== '') {
  store.formulaireBillet[uuidEvent].attentionEmail = true
  store.formulaireBillet[uuidEvent].email = store.user.email
  store.formulaireBillet[uuidEvent].confirmeEmail = store.user.email
}

function getHeaderEvent() {
  let urlImage
  if (currentEvent.img_variations.med === undefined) {
    urlImage = `${domain}/media/images/image_non_disponible.svg`
  } else {
    urlImage = currentEvent.img_variations.med
  }
  // console.log('urlImage =', urlImage)
  return {
    urlImage: urlImage,
    shortDescription: currentEvent.short_description,
    longDescription: currentEvent.long_description,
    titre: currentEvent.name
  }
}


function getDataCardPlace() {
  let urlImage
  if (store.place.img_variations.med === undefined) {
    urlImage = `${domain}/media/images/image_non_disponible.svg`
  } else {
    urlImage = store.place.img_variations.med
  }

  return {
    urlImage: urlImage,
    titre: store.place.organisation,
    lonDescription: store.place.long_description,
    shortDescription: store.place.short_description
  }
}

// mise à jour données du profil
emitter.on('emitUpdateProfil', (data) => {
  console.log('réception "emitUpdateProfil", data=', JSON.stringify(data, null, 2))
  store.formulaireBillet[store.currentUuidEvent][data.key] = data.value
})

// mise à jour données de l'adhésion
emitter.on('majAdhesion', (data) => {
  console.log('réception "majAdhesion", data=', JSON.stringify(data, null, 2))
  store.formulaireBillet[store.currentUuidEvent].adhesion[data.key] = data.value
})

emitter.on('majActiveSimpleProduct', (data) => {
  console.log('réception "majActiveSimpleProduct", data=', JSON.stringify(data, null, 2))
  store.formulaireBillet[store.currentUuidEvent].activeSimpleProduct[data.uuidProduct][data.key] = data.value
})

emitter.on('majOptionsEvent', (data) => {
  console.log('réception "majOptionsEvent", data=', JSON.stringify(data, null, 2))
  if (data.name === 'check') {
    store.formulaireBillet[store.currentUuidEvent]['options'][data.uuid] = data.value
  }
})

</script>

<style>
</style>