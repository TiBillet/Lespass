<template>
  <Header :header-event="getHeaderEvent()"/>
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
  <!-- adhésion -->
  <ModalAdhesion v-if="store.place.button_adhesion === true" :prices="prices" required/>
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
import ModalAdhesion from '../components/ModalAdhesion.vue'

// store
const store = useStore()

const router = useRouter()
const domain = `${location.protocol}//${location.host}`


const emailBase64 = btoa('dijouxnicolas@sfr.fr')
console.log('email base64 =', emailBase64)

let prices = []
// console.log('store.place.membership_products =', store.place.membership_products)
if (store.place.button_adhesion === true) {
  try {
    prices = store.place.membership_products.filter(adh => adh.categorie_article === 'A')[0].prices
    // console.log('prices =', prices)
  } catch (erreur) {
    emitter.emit('message', {
      tmp: 6,
      typeMsg: 'warning',
      contenu: `Avez-vous renseigné les prix pour l'adhésion ?`
    })
  }
}

function getHeaderEvent() {
  let urlImage, urlLogo
  if (store.place.img_variations.med === undefined) {
    urlImage = `${domain}/media/images/image_non_disponible.svg`
  } else {
    urlImage = store.place.img_variations.med
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

// aller à la page évènement (lien défini si-dessous et dans le store) => /views/Event.vue
emitter.on('goEvenement', (slug) => {
  console.log('-> Emmiter, écoute "goEvenement"; slug =', slug, '  --  type =', typeof (slug))
  router.push({name: 'Event', params: {slug: slug}})
})

</script>

<style>
</style>
