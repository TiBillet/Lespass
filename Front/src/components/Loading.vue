<template>
  <div class="fixed-top bg-dark transparent-modal vw-100 vh-100">
    <div class="d-flex justify-content-center align-items-center vw-100 vh-100">
      <div class="spinner-border text-info" role="status" :style="styleObject"></div>
    </div>
  </div>

</template>

<script setup>
import {onMounted, onUnmounted} from 'vue'

// taille de l'icon chargement
const styleObject = {
  width: '20rem',
  height: '20rem',
  borderWidth: '0.5em'
}

// bloque le scroll
onMounted(() => {
  // Get the current page scroll position
  const scrollTop = window.pageYOffset || document.documentElement.scrollTop
  const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft

  // if any scroll is attempted, set this to the previous value
  window.onscroll = function () {
    window.scrollTo(scrollLeft, scrollTop)
  }
})

// débloque le scroll
onUnmounted(() => {
  window.onscroll = function () {
  }
})

</script>

<style scoped>
.transparent-modal {
  background-color: #cc33ff;
  opacity: 0.4;
  z-index: 9999;
}
</style>