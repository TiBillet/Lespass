<template>
  <div class="container">
    <h1>Page OnboardReturn {{ accStripe }}</h1>
  </div>
</template>

<script setup>

import {onMounted, onUnmounted} from 'vue'
import {useRoute} from 'vue-router'
const route = useRoute()

const accStripe = route.params.accstripe

// bloque le scroll
onMounted(() => {
  if (accStripe !== undefined) {
    console.log("On Mounted accStripe : ", accStripe)
  }
})


</script>

<style scoped>

</style>