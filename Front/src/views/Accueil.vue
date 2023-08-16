<template>
  <div class="container mt-5">
    <div class="row">
      <div class="col-lg-4 col-md-6 mb-2 test-card-event-container" v-for="(event, index) in $route.params.events" :key="index">
        <CardEvent :event="event"/>
      </div>
    </div>
  </div>
</template>

<script setup>
// console.log('-> Accueil.vue')

// composants
import CardEvent from '@/components/CardEvent.vue'
</script>

<style></style>