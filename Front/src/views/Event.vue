<template>
    <!-- artistes -->
    <div v-for="(artist, index) in getEventForm.artists" :key="index">
       <CardArtist :artist="artist.configuration" class="mb-6"/>
    </div>

</template>

<script setup>
console.log('-> Event.vue !')
// le près chargement de l'évènement est géré par .../router/routes.js fonction "loadEvent"
const {  getEventForm } = useSessionStore()

// store
import { useSessionStore } from '@/stores/session'

// composants
import CardArtist from '@/components/CardArtist.vue'


</script>

<style>
.invalid-feedback {
  margin-top: -4px !important;
  margin-left: 4px !important;
}
</style>