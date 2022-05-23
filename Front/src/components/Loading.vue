<template>
  <div class="position-relative d-flex justify-content-center align-items-center vw-100 vh-100 bg-light au-dessus">
    <h1>Chargement des données !</h1>
    <div class="position-absolute d-flex justify-content-center align-items-center vw-100 vh-100">
      <div class="spinner-border text-success" role="status" style="width: 10rem; height: 10rem;"></div>
    </div>
  </div>
</template>

<script setup>
</script>

<style scoped>
.au-dessus {
  z-index: 99;
}
</style>