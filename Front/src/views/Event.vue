<template>
  <div class="container mt-5 test-view-event">
    <!-- artistes -->
    <div v-for="(artist, index) in getEventForm.artists" :key="index">
      <CardArtist :artist="artist.configuration" class="mb-6"/>
    </div>

    <form @submit.prevent="validerAchats($event)" class="needs-validation" novalidate>
      <CardEmail v-model:email.checkemail="getEventForm.email"/>

       <!--
      Billet(s)
      Si attribut "image", une image est affiché à la place du nom
      Attribut 'style-image' gère les propriétées(css) de l'image (pas obligaoire, style par défaut)
       -->
      <CardBillet v-model:products="getEventForm.products" />

      <button type="submit" class="btn bg-gradient-dark w-100">Valider la réservation</button>
    </form>
  </div>
</template>

<script setup>
console.log('-> Event.vue !')
// le près chargement de l'évènement est géré par .../router/routes.js fonction "loadEvent"
const { getEventForm } = useSessionStore()

// store
import { useSessionStore } from '../stores/session'

// composants
import CardArtist from '../components/CardArtist.vue'
import CardEmail from '../components/CardEmail.vue'
import CardBillet from "../components/CardBillet.vue"

async function validerAchats (event) {
  if (!event.target.checkValidity()) {
    event.preventDefault()
    event.stopPropagation()
  }
  event.target.classList.add('was-validated')
  if (event.target.checkValidity() === true) {
    console.log('validation ok!')
  }
}

</script>

<style>
.invalid-feedback {
  margin-top: -4px !important;
  margin-left: 4px !important;
}
</style>