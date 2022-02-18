<template>
  <div class="card card-blog card-plain">
    <div v-if="event.img_variations.length > 0">
      <a class="d-block">
        <img class="img-fluid shadow border-radius-lg" :src="event.img_variations.thumbnail" loading="lazy"
             alt="Image de l'évènement !"/>
      </a>
    </div>

    <div class="card-body px-1 pt-3">
      <h5>{{ event.name }}</h5>

      <p v-if="event.long_description !== null">{{ event.long_description }}</p>
      <p v-if="event.long_description === null && event.short_description !== null">{{ event.short_description }}</p>

      <div class="d-flex flex-column" v-for="(uuidProd, index) in event.products" :key="index">
        <div v-for="produit in produits.filter(prod => prod.uuid === uuidProd)" :key="produit.uuid">
          <div v-if="produit.categorie_article === 'B'">
            <div v-for="price in produit.prices" :key="produit.uuid">
              {{ price.name }} - {{ price.prix }}€
            </div>
          </div>
        </div>
      </div>

      <p class="text-dark">{{ formateDate(event.datetime) }}</p>

      <button type="button" class="btn btn-outline-primary btn-sm" @click="goEvenement(event.slug)">
        Réserver
      </button>
    </div>

  </div>
</template>

<script setup>
console.log('-> CardEvent.vue')
import {useStore} from 'vuex'

// asset
const img = import('../assets/img/loading.svg')

const store = useStore()

const props = defineProps({
  event: Object
})

// convertion du proxy en array
let produits = JSON.parse(JSON.stringify(store.state.products))

function formateDate(dateString) {
  const date = new Date(dateString)
  return `${date.toLocaleDateString()} - ${date.toLocaleTimeString()}`
}

function goEvenement(slug) {
  // console.log('-> evenement, slug =', slug)
  emitter.emit("goEvenement", slug)
}
</script>

<style>
</style>