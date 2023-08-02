<template>
  <div v-if="loadingEvent">
    <!-- artistes -->
    <div class="container">
      <div v-for="(artist, index) in getArtists" :key="index">
        <CardArtist :artist="artist.configuration" class="mb-6"/>
      </div>
    </div>

    <!-- les produits -->
    <div class="container mt-5 test-view-event">
      <form @submit.prevent="validerAchats($event)" class="needs-validation" novalidate>
        <CardEmail/>


        <button type="submit" class="btn bg-gradient-dark w-100">Valider la réservation</button>
      </form>
    </div>
  </div>
</template>

<script setup>
console.log('-> Event.vue !')
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { useSessionStore } from '../stores/session'

// composants
import CardArtist from '@/components/CardArtist.vue'
import CardEmail from '@/components/CardEmail.vue'

//store
const sessionStore = useSessionStore()
// actions
const { loadEvent, getArtists } = sessionStore

const loadingEvent = ref(false)
const route = useRoute()
const slug = route.params.slug

// gestion synchrone du chargement de l'évènement
const waitLoadEvent = async () => {
  loadingEvent.value = await loadEvent(slug)
}

function validerAchats (event) {
  if (!event.target.checkValidity()) {
    event.preventDefault()
    event.stopPropagation()
  }
  event.target.classList.add('was-validated')
  if (event.target.checkValidity() === true) {
    console.log('validation ok!')
  }
}

waitLoadEvent()
</script>

<style>
.invalid-feedback {
  margin-top: -4px !important;
  margin-left: 4px !important;
}
</style>