<template>
  <div class="fixed-top bg-dark transparent-modal vw-100 vh-100">
    <div class="d-flex justify-content-center align-items-center vw-100 vh-100">
      <div class="spinner-border text-info" role="status" :style="styleObject"></div>
    </div>
  </div>

</template>

<script setup>
const styleObject = {
  width: '20rem',
  height: '20rem',
  borderWidth: '0.5em'
}
</script>

<style scoped>
.transparent-modal {
  background-color: #cc33ff;
  opacity: 0.4;
  z-index: 99;
}
</style>