<template>
    <form id="tibillet-form-record-event" @submit.prevent="">
        <div class="container-fuild">
            <CardUpdateHeader v-model="header" />
        </div>
        <div class="container">
            <div class="btn tibillet-bg-primary w-100" role="button" aria-label="Enregistrer l'évènement"
                @click="recordEvent('#tibillet-form-record-event')">
                Enregistrer l'évènement
            </div>
        </div>
    </form>
</template>

<script setup>
console.log('-> CreateEvent.vue');

// store
import { useSessionStore } from '@/stores/session'

// components
import CardUpdateHeader from "../components/CardUpdateHeader.vue"

const sessionStore = useSessionStore()
const { updateHeader } = sessionStore
updateHeader(null)

let header = {
    place: window.location.host.split('.')[0],
    name: "Entrer un nom pour votre évènement.",
    short_description: "Entrer une courte description.",
    long_description: "Entrer une longue description",
    img_url: null
}

let reste = {
    artists: [],
    products: [],
    options_checkbox: [],
    options_radio: [],
    tag: []
}

function recordEvent(selectorForm) {
    const event = { ...header, ...reste }
    console.log('-> recordEvent, event =', JSON.stringify(event, null, 2));
}

</script>

<style scoped></style>