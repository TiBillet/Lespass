<template>
  <!-- pour load events -->
  <p v-if="error !== null" class="text-dark">{{ error }}</p>
  <Loading v-if="loading === true" test="accueil"/>
  <Header v-if="Object.entries(place).length > 0" :header-event="getHeaderPlace()"/>
  <section v-if="Object.entries(events).length > 0" class="pb-0">
    <div class="container">
      <div class="row">
        <div class="col-lg-4 col-md-6 mb-2" v-for="(event, index) in events" :key="index">
          <CardEvent :event="event" @go-event="goEvent"/>
        </div>
      </div>
    </div>
  </section>
  <section v-if="Object.entries(events).length > 0" class="pt-5 pb-0">
    <div id="calendar" class="container">
      <!-- <Calendar categorie-article="B"/> -->
    </div>
  </section>
</template>

<script setup>
console.log('-> Accueil.vue')

// store
import {storeToRefs} from 'pinia'
import {useAllStore} from '@/stores/all'

// routes
import {useRouter} from 'vue-router'

// composants
import Loading from '@/components/Loading.vue'
import Header from '../components/Header.vue'
import CardEvent from '../components/CardEvent.vue'
// import Calendar from '../components/Calendar.vue'


const {place, events, loading, error} = storeToRefs(useAllStore())
const {getEvents} = useAllStore()
const router = useRouter()

// load events
getEvents()


function getHeaderPlace() {
  const domain = `${location.protocol}//${location.host}`
  let urlImage, urlLogo
  try {
    urlImage = place.value.img_variations.fhd
  } catch (e) {
    urlImage = `${domain}/media/images/image_non_disponible.svg`
  }

  try {
    urlLogo = place.value.logo_variations.med
  } catch (e) {
    urlLogo = `${domain}/media/images/image_non_disponible.svg`
  }

  return {
    urlImage: urlImage,
    logo: urlLogo,
    shortDescription: place.value.short_description,
    longDescription: place.value.long_description,
    titre: place.value.organisation,
    domain: domain
  }
}

function goEvent(slug) {
  console.log('-> Emmiter, écoute "goEvenement"; slug =', slug, '  --  type =', typeof (slug))
  router.push({name: 'Event', params: {slug: slug}})
}


/*
// vue
import {useRouter} from 'vue-router'

// store
import {useStore} from '@/store'

// composants
import Header from '../components/Header.vue'
import CardEvent from '../components/CardEvent.vue'
import Calendar from '../components/Calendar.vue'

import {storeLocalGet, storeLocalSet} from '@/storelocal'

// store
const store = useStore()

const router = useRouter()
const domain = `${location.protocol}//${location.host}`

function getHeaderEvent() {
  let urlImage, urlLogo
  if (store.place.img_variations.med === undefined) {
    urlImage = `${domain}/media/images/image_non_disponible.svg`
  } else {
    urlImage = store.place.img_variations.fhd
  }

  if (store.place.logo_variations.med === undefined) {
    urlLogo = `${domain}/media/images/image_non_disponible.svg`
  } else {
    urlLogo = store.place.logo_variations.med
  }
  return {
    urlImage: urlImage,
    logo: urlLogo,
    shortDescription: store.place.short_description,
    longDescription: store.place.long_description,
    titre: store.place.organisation,
    domain: domain
  }
}

// aller à la page évènement (lien défini ci-dessous et dans le store) => /views/Event.vue
emitter.on('goEvenement', (slug) => {
  console.log('-> Emmiter, écoute "goEvenement"; slug =', slug, '  --  type =', typeof (slug))
  router.push({name: 'Event', params: {slug: slug}})
})
*/
</script>

<style>
</style>
