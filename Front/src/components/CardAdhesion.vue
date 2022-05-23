<template>
  <fieldset v-if="adhesion.status !== 'membership'" class="shadow-sm p-3 mb-5 bg-body rounded">
    <legend>
      <!-- Adhésion -->
      <div class="card-header pb-0 d-flex align-items-center">
        <h3 class="font-weight-bolder text-info text-gradient align-self-start w-85">Adhésion</h3>
        <div class="d-flex align-items-center modal-click-info" @click="goStatus()">
          <span>status</span>
          <i class="fas fa-question mb-1"></i>
        </div>
      </div>
    </legend>

    <div class="form-check form-switch">
      <input v-if="adhesion.activation === true && place.adhesion_obligatoire === true" class="form-check-input" type="checkbox"
             id="etat-adhesion" checked disabled>
      <input v-else class="form-check-input" type="checkbox" id="etat-adhesion"
             @change="setActivationAdhesion($event.target.checked)" :checked="adhesion.activation">

      <label v-if="adhesion.activation === true" class="form-check-label text-dark" for="etat-adhesion">
        L'adhésion à l'association est obligatoire pour participer. Connectez vous si vous êtes déja adhérant.
      </label>
      <label v-else class="form-check-label text-dark" for="etat-adhesion">
        Prendre une adhésion associative.
      </label>
    </div>
    <div v-if="adhesion.activation === true">
      <!-- prix -->
      <div class="input-group mb-2 has-validation">
        <div :id="`adesion-modal-price-parent${index}`" class="col form-check mb-3"
             v-for="(price, index) in getPricesAdhesion" :key="index">
          <input v-if="index === 0" :value="price.uuid" v-model="adhesion.uuidPrix"
                 class="form-check-input input-adesion-modal-price" type="radio"
                 name="prixAdhesionModal" :id="`uuidadhesionmodalpriceradio${index}`"
                 required>
          <input v-else :value="price.uuid" v-model="adhesion.uuidPrix"
                 class="form-check-input input-adesion-modal-price" type="radio"
                 name="prixAdhesionModal" :id="`uuidadhesionmodalpriceradio${index}`">
          <label class="form-check-label" :for="`uuidadhesionmodalpriceradio${index}`">{{ price.name }} - {{
              price.prix
            }}€</label>
          <div v-if="index === 0" class="invalid-feedback">
            Un tarif ?
          </div>
        </div>
      </div>

      <!-- nom -->
      <div class="input-group mb-2 has-validation">
        <span class="input-group-text" @click="inputFocus('adhesion-nom')">Nom</span>
        <input id="adhesion-nom" v-model="adhesion.last_name" type="text"
               class="form-control" aria-label="Nom pour l'adhésion" required>
        <div class=" invalid-feedback">Un nom svp !
        </div>
      </div>

      <!-- prénom -->
      <div class="input-group mb-2 has-validation">
        <span class="input-group-text" @click="inputFocus('adhesion-prenom')">Prénom</span>
        <input id="adhesion-prenom" v-model="adhesion.first_name" type="text"
               class="form-control" aria-label="Prénom pour l'adhésion" required>
        <div class="invalid-feedback">Un prénom svp !</div>
      </div>

      <!-- code postal -->
      <div class="input-group mb-2 has-validation">
        <span class="input-group-text" @click="inputFocus('adhesion-code-postal')">Code postal</span>
        <input id="adhesion-code-postal" v-model="adhesion.postal_code"
               type="number" class="form-control" aria-label="Code postal" required>
        <div class="invalid-feedback">Code postal svp !</div>
      </div>

      <!-- téléphone -->
      <div class="input-group has-validation">
        <span class="input-group-text" @click="inputFocus('adhesion-tel')">Fixe ou Mobile</span>
        <input id="adhesion-tel" v-model="adhesion.phone" type="tel"
               class="form-control" pattern="^[0-9-+\s()]*$"
               aria-label="Fixe ou Mobile" required>
        <div class="invalid-feedback">Un numéro de téléphone svp !</div>
      </div>
      <p class="mb-2">Non obligatoire, uniquement utile pour vous envoyer les confirmations d'achats."</p>
    </div>
  </fieldset>
</template>

<script setup>
console.log('-> CardAdhesion.vue !')

// vue
import {useRouter} from 'vue-router'

// store
import {storeToRefs} from 'pinia'
import {useAllStore} from "@/stores/all"
import {useLocalStore} from "@/stores/local"

// state "ref"
const {place} = storeToRefs(useAllStore())
// action
const {getPricesAdhesion} = useAllStore()
// state ref
const {adhesion} = storeToRefs(useLocalStore())
// action
const {sychronizeMembershipWithObligationPlace, setActivationAdhesion} = useLocalStore()
// vue-router
const router = useRouter()

sychronizeMembershipWithObligationPlace()

function inputFocus(id) {
  document.querySelector(`#${id}`).focus()
}

function goStatus() {
  // aller au status
  router.push('/status')
}
</script>

<style scoped>
.modal-click-info {
  cursor: pointer;
}
</style>