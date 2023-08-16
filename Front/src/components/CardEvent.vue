<!--inspiré de card4 : https://demos.creative-tim.com/now-ui-design-system-pro/sections/page-sections/general-cards.html-->
<template>
  <div class="card test-card-event">
    <div class="card-header p-0 position-relative z-index-1">
      <a class="d-block">
        <img
            class="img-fluid shadow border-radius-lg"
            :src="event.img_variations.crop"
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

      <div class="btn btn-outline-primary btn-sm" @click="$router.push({ path: '/event/' + event.slug })">Réserver</div>

    </div>
  </div>

</template>

<script setup>
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