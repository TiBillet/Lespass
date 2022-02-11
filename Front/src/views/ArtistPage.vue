<template>
  <div class="container">
    <h1>Page artiste {{ slug }}</h1>
    <h2>En attent de construction !</h2>
  </div>
</template>

<script setup>
import {useRoute} from 'vue-router'

const route = useRoute()
const slug = route.params.slug

</script>

<style scoped>

</style>