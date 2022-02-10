<template>
  <section>
    <div class="container py-4">
      <h2 class="text-black">Produits</h2>
       <div class="row row-cols-auto">
        <div class="col-lg-4 col-md-6 mb-2" v-for="(data, index) in event.products" :key="index">
          <CardProduct v-if="testPrix(data)" :uuid-event="event.uuid" :product="data" />
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
  console.log('-> ProductsList.vue')

  // composants
  import CardProduct from './CardProduct.vue'

  const props = defineProps({
    event: Object
  })

  function testPrix(data) {
    if (data.prices.length > 0) {
      return true
    } else {
      return false
    }
  }
</script>

<style>

</style>