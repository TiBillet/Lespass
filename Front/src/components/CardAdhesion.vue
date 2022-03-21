<template>
  <!-- pour formulaire -->
  <fieldset class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
    <legend>Adhésion</legend>

    <div class="form-check form-switch">
      <input v-if="store.place.adhesion_obligatoire === true" class="form-check-input" type="checkbox"
             id="etat-adhesion" checked disabled>
      <input v-else class="form-check-input" type="checkbox" id="etat-adhesion"
             @change="emitMajAdhesion('activation', $event.target.checked)" :checked="adhesion.activation">
      <label class="form-check-label text-dark" for="etat-adhesion">Prendre une adhésion
        associative.</label>
    </div>

    <div v-if="adhesion.activation === true || store.place.adhesion_obligatoire === true">

      <!-- prix -->
      <div class="input-group mb-2 has-validation">
        <div id="prices-parent" class="col form-check mb-3" v-for="(price, index) in prices" :key="index">
          <input v-model="adhesionPrix" :value="price.uuid"
                 class="form-check-input input-uuid-price" type="radio"
                 name="prixAdhesion" :id="`uuidPriceRadio${index}`"
                 @change="emitMajAdhesion('adhesion', $event.target.value)">
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
               @keyup="emitMajAdhesion('lastName', $event.target.value)">
        <div class="invalid-feedback">Un nom svp !</div>
      </div>
      <!-- prénom -->
      <div class="input-group mb-2 has-validation">
        <span class="input-group-text" id="basic-addon1">Prénom</span>
        <input :value="adhesion.firstName" type="text"
               id="adhesion-prenom" class="form-control" aria-label="Prénom pour l'adhésion" required
               @keyup="emitMajAdhesion('firstName', $event.target.value)">
        <div class="invalid-feedback">Un prénom svp !</div>
      </div>
      <!-- code postal -->
      <div class="input-group mb-2 has-validation">
        <span class="input-group-text" id="basic-addon1">Code postal</span>
        <input :value="adhesion.postalCode" id="adhesion-adresse"
               type="number"
               class="form-control" aria-label="Code postal" required
               @keyup="emitMajAdhesion('postalCode', $event.target.value)">
        <div class="invalid-feedback">Code postal svp !</div>
      </div>
      <!-- téléphone -->
      <div class="input-group mb-2 has-validation">
        <span class="input-group-text" id="basic-addon1">Fixe ou Mobile</span>
        <input :value="adhesion.phone" type="tel"
               class="form-control" pattern="^[0-9-+\s()]*$"
               aria-label="Fixe ou Mobile" required
               @keyup="emitMajAdhesion('phone', $event.target.value)">
        <div class="invalid-feedback">Un numéro de téléphone svp !</div>
      </div>
      <!-- date de naissance -->
      <div class="input-group mb-2 has-validation">
        <span class="input-group-text" id="basic-addon1">Date de naissance</span>
        <input :value="adhesion.birthDate" type="text"
               class="form-control datepicker"
               placeholder="Date de naissance" pattern="^[0-9-+\s()]*$"
               aria-label="Date de naissance" required
               @change="emitMajAdhesion('birthDate', $event.target.value)"
               @click="$event.target.type='date'; $event.target.click()">
        <div class="invalid-feedback">Un numéro de téléphone svp !</div>
      </div>


    </div>
  </fieldset>

</template>

<script setup>
console.log('-> CardAdhesion.vue !')

// vue
import {ref, onMounted} from 'vue'

// store
import {useStore} from '@/store'

const store = useStore()

// attributs/props
const props = defineProps({
  prices: Object,
  form: Boolean
})
console.log('adhésion, props.prices =', props.prices)

let adhesion = {}
let adhesionPrix = ''
let adhesionActivation = ref(false)
const adhesionFormModal = store.user

// init mémorisation formulaire adhésion de l'évènement courant
if (store.formulaireBillet[store.currentUuidEvent]['adhesion'] === undefined) {
  store.formulaireBillet[store.currentUuidEvent]['adhesion'] = {
    email: store.user.email,
    firstName: store.user.first_name,
    lastName: store.user.last_name,
    phone: store.user.phone,
    postalCode: store.user.postal_code,
    birthDate: store.user.birth_date,
    adhesion: store.user.adhesion,
    activation: false
  }
}

// maj
adhesion = store.formulaireBillet[store.currentUuidEvent]['adhesion']
adhesionPrix = store.formulaireBillet[store.currentUuidEvent].adhesion.adhesion
adhesionActivation.value = adhesion.activation


function majPrixAdhesion() {
  console.log('fonc majPrixAdhesion !')
  let ele
  try {
    ele = document.querySelector(`.input-uuid-price[value='${store.formulaireBillet[store.currentUuidEvent].adhesion.adhesion}']`)
    ele.click()
  } catch (erreur) {
    ele = null
  }
}

onMounted(() => {
  majPrixAdhesion()
})

function emitMajAdhesion(key, value) {
  console.log(key + " = " + value)
  emitter.emit('majAdhesion', {key: key, value: value})
  if (key === 'activation') {
    adhesionActivation.value = value
  }
}


function validerAdhesion(event) {
  if (event.target.checkValidity() === true) {
    // TODO: emitter.emit('validerAdhesion', {})

    // ferme le modal
    const elementModal = document.querySelector('#modal-form-adhesion')
    const modal = bootstrap.Modal.getInstance(elementModal) // Returns a Bootstrap modal instance
    modal.hide()

    // TODO: si réservation adhésion ok => modifier le bouton "adhésion" en info. adhérant

    console.log('Valider adhésion ok !')
    console.log('adhesionFormModal =', adhesionFormModal)
  }
}

</script>

<style>
</style>