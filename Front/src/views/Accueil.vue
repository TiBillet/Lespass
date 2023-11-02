<template>
  <div class="container mt-7">
    <div class="row">
      <div v-if="getIsStaff" class="col-lg-4 col-md-6 mb-7 test-card-event-container">
        <CardEvent :event="fakeEvent" :place="getHeaderPlace" />
      </div>

      <div class="col-lg-4 col-md-6 mb-7 test-card-event-container" v-for="(event, index) in $route.params.events"
        :key="index">
        <CardEvent :event="event" :place="getHeaderPlace" />
      </div>
    </div>
  </div>
</template>

<script setup>
// console.log('-> Accueil.vue')
import { storeToRefs } from 'pinia'

// store
import { useSessionStore } from '@/stores/session'

// composants
import CardEvent from '@/components/CardEvent.vue'

const sessionStore = useSessionStore()
const { updateHeader, getHeaderPlace } = sessionStore
const { getIsStaff } = storeToRefs(sessionStore)
updateHeader(getHeaderPlace)

const fakeEvent = {
  "uuid": "fakeEven-ece7-4b30-aa15-b4ec444a6a73",
  "name": "Nom de l'évènement",
  "short_description": "Cliquer sur le bouton si-dessous.",
  "long_description": null,
  "categorie": "CARDE_CREATE",
  "tag": [],
  "products": [],
  "options_radio": [],
  "options_checkbox": [],
  "img_variations": {
    "crop": "/media/images/1080_v39ZV53.crop"
  },
  "artists": [],
}

</script>

<style></style>