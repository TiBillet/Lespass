<template>
    <CreationStep title="Créer votre espace" sub-title="Ajouter un évènement"
        validation-creation-msg="validerCreationPlace">

        <!-- Présentation -->
        <div id="presentation" class="creation-tab-content">
            <div class="espace-content d-flex flex-column">
                <CardUpdateHeader v-model="header" />
            </div>
        </div>

        <!-- Produits -->
        <div id="produits" class="creation-tab-content">
            <div class="espace-content d-flex flex-wrap justify-content-around">
                <h1>Produits</h1>
            </div>
        </div>

        <!-- Prix -->
        <div id="prix" class="creation-tab-content">
            <div class="espace-content d-flex flex-wrap justify-content-around">
                <h1>Prix</h1>
            </div>
        </div>

        <!-- Options -->
        <div id="options" class="creation-tab-content">
            <div class="espace-content d-flex flex-wrap justify-content-around">
                <h1>Options</h1>
            </div>
        </div>

        <!-- Tags -->
        <div id="tags" class="creation-tab-content">
            <div class="espace-content d-flex flex-wrap justify-content-around">
                <h1>Tags</h1>
            </div>
        </div>

        <!-- Validation -->
        <div id="validation" class="creation-tab-content">
            <div class="espace-content d-flex flex-wrap justify-content-around">
                <h1>Validation</h1>
            </div>
        </div>

    </CreationStep>
</template>

<script setup>
console.log('-> CreateEvent.vue');
import { useSessionStore } from "../stores/session";

// components

import CreationStep from "../components/CreationStep.vue";
import CardUpdateHeader from "../components/CardUpdateHeader.vue"

const sessionStore = useSessionStore();
const { updateHeader } = sessionStore;

let header = {
    place: window.location.host.split('.')[0],
    name: "Entrer un nom pour votre évènement.",
    short_description: "Entrer une courte description.",
    long_description: "Entrer une longue description",
    img_url: null
}

updateHeader(null)


/*
// store
import { useSessionStore } from '@/stores/session'

// components
import CardUpdateHeader from "../components/CardUpdateHeader.vue"
import CardCreateProduct from "../components/CardCreateProduct.vue"


const sessionStore = useSessionStore()
const { updateHeader } = sessionStore
updateHeader(null)


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
*/
</script>

<style scoped></style>