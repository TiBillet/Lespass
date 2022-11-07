<template>
  <component :is="layout">
    <router-view/>
  </component>
</template>

<script setup>
// console.log(' -> App.vue !')

import LayoutDefault from '@/layouts/LayoutDefault.vue'
// idée: en fonction de la route mise à jour dans store all changer le layout (import dynamique)
let layout = LayoutDefault
</script>

<style>
/*body {*/
/*  overflow-x: hidden;*/
/*  overflow-y: auto;*/
/*}*/
</style>