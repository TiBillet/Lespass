<template>
  <Header :data-header="dataHeader"/>
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
console.log('-> Accueil.vue')

// vue
import {useRouter} from 'vue-router'

// store
import {useStore} from '@/store'

// composants
import Header from '../components/Header.vue'
import CardEvent from '../components/CardEvent.vue'
import Calendar from '../components/Calendar.vue'

// store
const store = useStore()
const router = useRouter()
const domain = `${location.protocol}//${location.host}`

let urlImage, urlLogo
  try {
    urlImage = store.place.img_variations.med
  } catch (e) {
    urlImage = `${domain}/media/images/image_non_disponible.svg`
  }
  try {
    urlLogo = store.place.logo_variations.med
  } catch (e) {
    urlLogo = `${domain}/media/images/image_non_disponible.svg`
  }
const dataHeader = {
  urlImage: urlImage,
  shortDescription: store.place.short_description,
  longDescription: store.place.long_description,
  logo: urlLogo,
  titre: store.place.organisation,
  domain: `${location.protocol}//${location.host}`
}


// aller à la page évènement (lien défini si-dessous et dans le store) => /views/Event.vue
emitter.on('goEvenement', (slug) => {
  console.log('-> Emmiter, écoute "goEvenement"; slug =', slug, '  --  type =', typeof (slug))
  router.push({name: 'Event', params: {slug: slug}})
})

</script>

<style>
</style>
