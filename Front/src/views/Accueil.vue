<template>
  <div class="container mt-5">
    <div class="row">
      <div class="col-lg-4 col-md-6 mb-2 test-card-event-container" v-for="(event, index) in events" :key="index">
        <CardEvent :event="event"/>
      </div>
    </div>
  </div>
</template>

<script setup>
// console.log('-> Accueil.vue')

// store
import { storeToRefs } from "pinia"
import { useSessionStore } from '@/stores/session'
// composants
import CardEvent from '@/components/CardEvent.vue'

// réactivité
const { events } = storeToRefs(useSessionStore())
// action
const { loadEvents } = useSessionStore()
loadEvents()
</script>

<style>
</style>
