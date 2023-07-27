<template>
  <div v-if="events !== null" class="container mt-5">
    <div class="row">
      <div class="col-lg-4 col-md-6 mb-2 test-card-event-container" v-for="(event, index) in events" :key="index">
        <CardEvent :event="event"/>
      </div>
    </div>
  </div>
</template>

<script setup>
// console.log('-> Accueil.vue')
import { ref } from 'vue'

// composants
import CardEvent from '@/components/CardEvent.vue'

// store
import { useSessionStore } from '@/stores/session'

let { loading, error } = useSessionStore()
let events = ref(null)
const domain = `${window.location.protocol}//${window.location.host}`

// Charge tous les évènements
async function init () {
  try {
    loading = true
    const apiEvents = `/api/events/`
    const response = await fetch(domain + apiEvents)
    if (response.status !== 200) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    events.value = await response.json()
  } catch (error) {
    emitter.emit('modalMessage', {
      titre: 'Erreur',
      contenu: `Chargement des évènements  -- erreur: ${error.message}`
    })
    log({ message: 'load events: ' + error.message })
  } finally {
    loading = false
  }
}

init()
</script>

<style>
</style>
