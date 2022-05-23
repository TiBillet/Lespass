<template>
  <div class="position-relative d-flex justify-content-center align-items-center vw-100 vh-100 bg-light au-dessus">
    <h1 v-if="test !== null || test !== undefined">Chargement "{{ test }}" des données !</h1>
    <h1 v-else>Chargement "{{ test }}" des données !</h1>
    <div class="position-absolute d-flex justify-content-center align-items-center vw-100 vh-100">
      <div class="spinner-border text-success" role="status" style="width: 10rem; height: 10rem;"></div>
    </div>
  </div>
</template>

<script setup>
// attributs/props
let props = defineProps({
  test: String
})

</script>

<style scoped>
.au-dessus {
  z-index: 99;
}
</style>