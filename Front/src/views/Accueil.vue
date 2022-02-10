<template>
  <Navbar :data-header="dataHeader"/>
  <Header :data-header="dataHeader"/>
  <section class="pt-5 pb-0">
    <div class="container">
      <div class="row">
        <div class="col-lg-4 col-md-6 mb-2" v-for="(item, index) in store.state.events" :key="index">
          <CardEvent :infos="item" :index="index"/>
        </div>
      </div>
    </div>
  </section>
  <section class="pt-5 pb-0">
    <div id="calendar" class="container">
      <Calendar categorie-article="B"/>
    </div>
  </section>
  <Footer :data-header="dataHeader"/>
</template>

<script setup>
console.log('-> Accueil.vue')
// composants
import Navbar from '../components/Navbar.vue'
import Header from '../components/Header.vue'
import Footer from '../components/Footer.vue'
import CardEvent from '../components/CardEvent.vue'
import Calendar from '../components/Calendar.vue'

// vue
import {useStore} from 'vuex'
import {useRouter} from 'vue-router'

const store = useStore()
const router = useRouter()

console.log('place =', store.state.place)

const dataHeader = {
  urlImage: store.state.place.img_variations.med,
  shortDescription: store.state.place.short_description,
  longDescription: store.state.place.long_description,
  logo: store.state.place.logo_variations.med,
  titre: store.state.place.organisation,
  domain: `${location.protocol}//${location.host}`
}

// aller à la page évènement (lien défini si-dessous et dans le store) => /views/Event.vue
emitter.on('goEvenement', (slug) => {
  console.log('-> Emmiter, écoute, slug =', slug, '  --  type =', typeof(slug))
  router.push({name: 'Event', params: {slug: slug}})
})
</script>

<style>
</style>
