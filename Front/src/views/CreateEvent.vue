<template>
    <form>
    <div class="container-fuild">
        
            <CardUpdateHeader v-model:data-header="header" />
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

console.log('window.location =', window.location);

let headerRaw = {
    place: window.location.host.split('.')[0],
    name: "Entrer un nom pour votre évènement.",
    short_description: "Entrer une courte description.",
    long_description: "Entrer une longue description",
    img_url: null
}

let headerUpdate = {
    placeActive: false,
    nameActive: false,
    shortDescriptionActive: false,
    longDescriptionActive: false,
    img_urlActive: false
}

let header = {...headerRaw, ...headerUpdate}
console.log('header = ', header);

let reste = {
    artists: [],
    products: [],
    options_checkbox: [],
    options_radio: [],
    tag: []
}

let event = { ...headerRaw, ...reste }
console.log('event = ', event);

</script>

<style scoped></style>