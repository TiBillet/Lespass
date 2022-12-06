<template>
  <component :is="layout">
    <router-view :key="route.fullPath"></router-view>
  </component>
</template>

<script setup>
// vue
import {useRoute} from 'vue-router'

// console.log(' -> App.vue !')
import LayoutDefault from '@/layouts/LayoutDefault.vue'
// idée: en fonction de la route mise à jour dans store all changer le layout (import dynamique)
let layout = LayoutDefault
const route = useRoute()
</script>

<style>
</style>