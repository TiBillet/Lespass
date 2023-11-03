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
      <div class="espace-content d-flex flex-column overflow-x-hidden overflow-y-scroll">
        <ListProducts name="Produits existants" :list="lists.products" :show="true" />

        <!--
        <fieldset class="col shadow-sm p-3 mb-5 bg-body rounded">
          <legend>
            <h3 class="font-weight-bolder text-info text-gradient align-self-start">Produits</h3>
          </legend>
          <div>
            <h2>produit sélectionné ou ajouté.</h2>

          </div>
        </fieldset>
        -->
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
import { ref } from "vue";
import { useSessionStore } from "../stores/session";

// components
import CreationStep from "../components/CreationStep.vue";
import CardUpdateHeader from "../components/CardUpdateHeader.vue"
import ListProducts from "../components/ListProducts.vue"

const sessionStore = useSessionStore();
const { updateHeader } = sessionStore;

let header = {
  place: window.location.host.split('.')[0],
  name: "Entrer un nom pour votre évènement.",
  short_description: "Entrer une courte description.",
  long_description: "Entrer une longue description",
  img_url: null
}

let lists = ref({
  products: [],
  options: [],
  prices: []
})

let selected = ref({
  products: [],
  options: [],
  prices: []
})

updateHeader(null)

async function loadLists() {
  lists.value.products = await getJson('/api/products')
}

loadLists()

async function getJson(url) {
  try {
    const response = await fetch(url);
    const retour = await response.json();
    console.log('retour =', retour);
    return retour
  } catch (error) {
    console.log('error =', error);
  }
}


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

// products
// const url = `https://${productR.place}.${env.domain}/api/products/`

// prices
// const url = `https://${priceR.place}.${env.domain}/api/prices/`

// events
// const url = `https://${eventR.place}.${env.domain}/api/events/`
async function postJson(url, rawPostData, token) {
  try {
    const response = await fetch(url, {
      method: "post",
      body: JSON.stringify(rawPostData),
      agent: httpsAgent,
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + token
      }
    });
    console.log("response =", response);
    const retour = await response.json();
    console.log("retour =", retour);
    return { status: response.status, content: retour };
  } catch (error) {
    log(`   - postJson, ${url} error !`, "red");
    console.log(error);
  }
}


*/
</script>

<style scoped></style>