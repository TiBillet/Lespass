<template>
  <Header :header-event="getHeaderEvent()"/>
  <button @click="test('get', 'email')">get</button>
  <button @click="test('set', 'email', '')">set email ''</button>
  <button @click="test('set', 'email', 'dijouxnicolas@sfr.fr')">set email 'dijouxnicolas@sfr.fr'</button>
  <section class="pt-5 pb-0">
    <div class="container">
      <div class="row">
        <div class="col-lg-4 col-md-6 mb-2" v-for="(event, index) in store.events" :key="index">
          <CardEvent :event="event"/>
        </div>
      </div>
    </div>
  </section>
  <section class="pt-5 pb-0">
    <div id="calendar" class="container">
      <Calendar categorie-article="B"/>
    </div>
  </section>
</template>

<script setup>
// console.log('-> Accueil.vue')

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

// dev
function test(action, name, value) {
  if (action === 'get') {
    console.log('-> storeLocalGet', name, '=', storeLocalGet(name))
  }
  if (action === 'set') {
    console.log('-> storeLocalset', name, '=', name, '  -- value =', value)
    storeLocalSet(name, value)
  }
}

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

</script>

<style>
</style>
