<template>
  <div class="card card-blog card-plain" :id="`event${ index }`">
    <!-- media/images/xxxxx.fhd/hdr/med/thumbnail.ext image -->
    <div v-if="infos.img_variations.length > 0">
      <a class="d-block">
        <img class="img-fluid shadow border-radius-lg" :src="infos.img_variations.thumbnail" loading="lazy"
             alt="Image de l'évènement !"/>
      </a>
    </div>

    <div class="card-body px-1 pt-3">
      <h5>{{ infos.name }}</h5>

      <p v-if="infos.long_description !== null">{{ infos.long_description }}</p>
      <p v-if="infos.long_description === null && infos.short_description !== null">{{ infos.short_description }}</p>

      <div lass="d-flex flex-column" v-for="uuidProd in infos.products" :key="index">
        <div v-for="produit in produits.filter(prod => prod.uuid === uuidProd)" :key="produit.uuid">
          <div v-if="produit.categorie_article === 'B'">
            <!-- <div class="fw-bold">{{ produit.name }} :</div> -->
            <div v-for="price in produit.prices" :key="produit.uuid">
              {{ price.name }} - {{ price.prix }}€
            </div>
          </div>
        </div>
      </div>

      <p class="text-dark">{{ formateDate(infos.datetime) }}</p>

      <button type="button" class="btn btn-outline-primary btn-sm" @click="goEvenement(infos.slug)">
        Réserver
      </button>
    </div>

  </div>

</template>

<script setup>
console.log('-> CardEvent.vue')
import {useStore} from 'vuex'

const img = import('../assets/img/loading.svg')
const props = defineProps({
  infos: Object,
  index: Number
})
const store = useStore()

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

<style scoped>

</style>