<template>
  <component :is="LayoutDefault">
    <router-view />
  </component>
</template>

<script setup>
// console.log(' -> App.vue !')
import LayoutDefault from '@/layouts/LayoutDefault.vue'
</script>

<style>
</style>
