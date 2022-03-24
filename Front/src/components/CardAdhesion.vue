<template>
  <fieldset class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
    <legend>Adhésion</legend>
    <div class="form-check form-switch">
      <input v-if="adhesion.obligatoire === true" class="form-check-input" type="checkbox"
             id="etat-adhesion" checked disabled>
      <input v-else class="form-check-input" type="checkbox" id="etat-adhesion"
             @change="updateAdhesion('activation', $event.target.checked)" :checked="adhesion.activation">
      <label class="form-check-label text-dark" for="etat-adhesion">Prendre une adhésion
        associative.</label>
    </div>

    <div v-if="adhesion.activation === true || adhesion.obligatoire === true">

      <!-- prix -->
      <div class="input-group mb-2 has-validation">
        <div id="prices-parent" class="col form-check mb-3" v-for="(price, index) in adhesion.prices" :key="index">
          <input :value="price.uuid"
                 class="form-check-input card-adhesion-uuid-price" type="radio"
                 name="prixAdhesion" :id="`uuidPriceRadio${index}`"
                 @change="updateAdhesion('uuidPrix', $event.target.value)">
          <label class="form-check-label" :for="`uuidPriceRadio${index}`">{{ price.name }} - {{ price.prix }}€</label>
          <div v-if="index === 0" class="invalid-feedback">
            Sélectionner un tarif d'adhésion svp !
          </div>
        </div>
      </div>

      <!-- nom -->
      <div class="input-group mb-2 has-validation">
        <span class="input-group-text" id="basic-addon1">Nom</span>
        <input :value="adhesion.lastName" type="text"
               class="form-control" aria-label="Nom pour l'adhésion" required
               @keyup="updateAdhesion('lastName', $event.target.value)">
        <div class="invalid-feedback">Un nom svp !</div>
      </div>

      <!-- prénom -->
      <div class="input-group mb-2 has-validation">
        <span class="input-group-text" id="basic-addon1">Prénom</span>
        <input :value="adhesion.firstName" type="text"
               id="adhesion-prenom" class="form-control" aria-label="Prénom pour l'adhésion" required
               @keyup="updateAdhesion('firstName', $event.target.value)">
        <div class="invalid-feedback">Un prénom svp !</div>
      </div>
      <!-- code postal -->
      <div class="input-group mb-2 has-validation">
        <span class="input-group-text" id="basic-addon1">Code postal</span>
        <input :value="adhesion.postalCode" id="adhesion-adresse"
               type="number"
               class="form-control" aria-label="Code postal" required
               @keyup="updateAdhesion('postalCode', $event.target.value)">
        <div class="invalid-feedback">Code postal svp !</div>
      </div>
      <!-- téléphone -->
      <div class="input-group mb-2 has-validation">
        <span class="input-group-text" id="basic-addon1">Fixe ou Mobile</span>
        <input :value="adhesion.phone" type="tel"
               class="form-control" pattern="^[0-9-+\s()]*$"
               aria-label="Fixe ou Mobile" required
               @keyup="updateAdhesion('phone', $event.target.value)">
        <div class="invalid-feedback">Un numéro de téléphone svp !</div>
      </div>
      <!-- date de naissance -->
      <div class="input-group mb-2 has-validation">
        <span class="input-group-text" id="basic-addon1">Date de naissance</span>
        <input :value="adhesion.birthDate" type="text"
               class="form-control datepicker"
               placeholder="Date de naissance" pattern="^[0-9-+\s()]*$"
               aria-label="Date de naissance" required
               @change="updateAdhesion('birthDate', $event.target.value)"
               @click="$event.target.type='date'; $event.target.click()">
        <div class="invalid-feedback">Un numéro de téléphone svp !</div>
      </div>

    </div>
  </fieldset>
</template>

<script setup>
console.log('-> CardAdhesion.vue !')
import {ref, onMounted, onUpdated} from 'vue'

// store
import {useStore} from '@/store'

// attributs/props
const props = defineProps({
  prices: Object,
  indexMemo: String, // pour persister l'état du composant dans le store,
  obligatoire: Boolean // active de force l'adhésion
})
// console.log('props =', JSON.stringify(props, null, 2))

const store = useStore()

// mémorise par défaut
let record = true

let adhesion = ref({})
const dataInit = {
  firstName: "",
  lastName: "",
  phone: null,
  postalCode: null,
  birthDate: null,
  uuidPrix: '',
  activation: false
}

// mémorise le composant dans le store ou la variable globale window
try {
  if (props.indexMemo === '' || props.indexMemo === undefined) {
    throw new Error(`Erreur index memo vide !`)
  }
  if (props.indexMemo !== '') {
    // init de base pour la persistance de tous les composants "CardAdhesion" dans le store
    if (store.memoComposants['CardAdhesion'] === undefined) {
      store.memoComposants['CardAdhesion'] = {}
    }
    // init de l'instance de clef "props.indexMemo"
    if (store.memoComposants.CardAdhesion[props.indexMemo] === undefined) {
      // console.log('Mémorisation initiale')
      store.memoComposants.CardAdhesion[props.indexMemo] = dataInit
      adhesion.value = dataInit
      adhesion.value['prices'] = props.prices
      adhesion.value['obligatoire'] = props.obligatoire
      store.memoComposants.CardAdhesion[props.indexMemo]['initDate'] = new Date().toLocaleString()
    } else {
      // instance existante
      adhesion.value = store.memoComposants.CardAdhesion[props.indexMemo]
      adhesion.value['prices'] = props.prices
      adhesion.value['obligatoire'] = props.obligatoire
      // console.log('Mémorisation existante')
    }
  }
} catch (erreur) {
  record = false
  console.log('Mémorisation du composant impossible')
  // instance sans mémorisation dans le store
  adhesion.value = dataInit
  adhesion.value['prices'] = props.prices
  adhesion.value['obligatoire'] = props.obligatoire
  // utilisation hors local storage
  if (window.store === undefined) {
    window.store = {}
  }
  if (window.store['CardAdhesion'] === undefined) {
    window.store['CardAdhesion'] = dataInit
    adhesion.value = dataInit
    adhesion.value['prices'] = props.prices
    adhesion.value['obligatoire'] = props.obligatoire
  } else {
    adhesion.value = window.store.CardAdhesion
  }
}

if (adhesion.value.obligatoire === true) {
  adhesion.value.activation = true
}

function updateRadioButon() {
  const eles = document.querySelectorAll(`.card-adhesion-uuid-price`)
  for (let i = 0; i < eles.length; i++) {
    const ele = eles[i]
    // console.log('ele =', ele)
    ele.removeAttribute('checked')
    if (ele.value === adhesion.value.uuidPrix) {
      ele.checked = true
    }
  }
}

onMounted(() => {
  updateRadioButon()
})

onUpdated(() => {
  updateRadioButon()
})

function updateAdhesion(key, value) {
  // console.log(key + " = " + value)
  if (record === true) {
    adhesion.value[key] = value
  }
}
</script>

<style>
</style>