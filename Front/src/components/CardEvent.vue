<!--inspiré de card4 : https://demos.creative-tim.com/now-ui-design-system-pro/sections/page-sections/general-cards.html-->
<template>
  <div class="card">
    <div class="card-header p-0 position-relative z-index-1">
      <a class="d-block">
        <img
            class="img-fluid border-radius-md border-bottom-end-radius-0 border-bottom-start-radius-0 shadow"
            :src="event.img_variations.med"
            loading="lazy"
            alt="Image de l'évènement !"/>
      </a>
    </div>

    <div class="card-body">


      <span
          class="card-title mt-3 h5 d-block text-dark">
        {{ event.name }}
      </span>

      <p class="text-dark">
        {{ formateDate(event.datetime) }}

        <span class="text-primary text-uppercase text-sm font-weight-bold">
        <span v-for="(produit, index) in event.products" :key="index">
          <span v-if="produit.categorie_article === 'B'">
            <span v-for="price in produit.prices" :key="produit.uuid">
              - {{ price.prix }}€
            </span>
          </span>
          <span v-if="produit.categorie_article === 'F'">
            <span v-for="price in produit.prices" :key="produit.uuid">
              - ENTRÉE LIBRE
            </span>
          </span>
        </span>
      </span>
      </p>

      <p class="card-description mb-4"
         v-if="event.short_description !== null">
        {{ event.short_description }}
      </p>
      <p class="card-description mb-4"
         v-if="event.short_description === null && event.artists[0] !== undefined">
        {{ event.artists[0].configuration.short_description }}
      </p>

      <a :href="event.url" class="btn btn-outline-primary btn-sm">Réserver</a>

    </div>
  </div>

</template>

<script setup>

// asset
const img = import('../../src/assets/img/loading.svg')

const emit = defineEmits(['goEvent'])

const props = defineProps({
  event: Object
})


function formateDate(dateString) {
  const date = new Date(dateString)
  return `${date.toLocaleDateString()} - ${date.toLocaleTimeString()}`
}
</script>

<style>
</style>