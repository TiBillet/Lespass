<template>


  <div class="row">
    <div class="col-lg-6 justify-content-center d-flex flex-column">
      <div class="card">
        <img :src="dataCard.urlImage" alt="Image du lieu" class="img-fluid border-radius-lg">
      </div>
    </div>
    <div class="col-lg-6 justify-content-center d-flex flex-column pl-lg-5 pt-lg-0 pt-3">
      <h6 class="category text-primary mt-3">Lieu</h6>
      <h3 class="card-title">
        <a href="javascript:;" class="text-dark text-decoration-underline-hover">{{ dataCard.titre }}</a>
      </h3>
      <p v-if="dataCard.lonDescription !== null" class="card-description">{{ dataCard.lonDescription }}</p>
      <p v-if="dataCard.lonDescription === null && dataCard.shortDescription !== null" class="card-description">
        {{ dataCard.shortDescription }}</p>
    </div>
  </div>


</template>
<script setup>
// console.log('-> CardPlace.vue')

const props = defineProps({
  dataCard: Object
})
</script>