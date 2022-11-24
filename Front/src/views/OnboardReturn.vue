<template>
  <div class="container">
    <h1>Page OnboardReturn {{ accStripe }}</h1>
  </div>
</template>

<script setup>

import {useRoute} from 'vue-router'
const route = useRoute()

const accStripe = route.params.accstripe
console.log(accStripe)

</script>

<style scoped>

</style>