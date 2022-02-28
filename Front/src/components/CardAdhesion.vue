<template>
  <!-- adhésion -->
  <fieldset v-if="data.publish === true" class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
    <legend>Adhésion</legend>
    <div class="form-check form-switch">
      <input v-if="store.state.place.adhesion_obligatoire === true" class="form-check-input" type="checkbox"
             id="etat-adhesion" checked disabled>
      <input v-else v-model="data.activation" class="form-check-input" type="checkbox" id="etat-adhesion"
             @change="majAdhesion('activation', $event.target.checked)">
      <label class="form-check-label text-dark" for="etat-adhesion">Prendre une adhésion
        associative.</label>
    </div>
    <div v-if="activationAdhesion === true">
      <!-- prix -->
      <div class="row has-validation">
        <div class="col form-check mb-3" v-for="(price, index) in data.prices" :key="index">
          <input v-if="index === 0" v-model="data.uuidPrice" :value="price.uuid" class="form-check-input input-uuid-price" type="radio"
                 name="prixAdhesion" :id="`uuidPriceRadio${index}`" @change="majAdhesion('uuidPrice', $event.target.value)">
          <input v-else v-model="data.uuidPrice" :value="price.uuid" class="form-check-input input-uuid-price" type="radio"
                 name="prixAdhesion" :id="`uuidPriceRadio${index}`" @change="majAdhesion('uuidPrice', $event.target.value)">
          <label class="form-check-label" :for="`customRadio${index}`">{{ price.name }} - {{ price.prix }}€</label>
          <div v-if="index === 0" id="uuid-price-error" class="invalid-feedback">Sélectionner un tarif d'adhésion svp !</div>
        </div>
      </div>

      <!-- nom -->
      <div class="input-group mb-2 has-validation">
        <input v-model="data.nom" type="text"
               class="form-control"
               placeholder="Nom" aria-label="Nom pour l'adhésion" required
               @keyup="majAdhesion('nom', $event.target.value)">
        <div class="invalid-feedback">Un nom svp !</div>
      </div>
      <!-- prénom -->
      <div class="input-group mb-2 has-validation">
        <input v-model="data.prenom" type="text"
               id="adhesion-prenom" class="form-control"
               placeholder="Prénom" aria-label="Prénom pour l'adhésion" required
               @keyup="majAdhesion('prenom', $event.target.value)">
        <div class="invalid-feedback">Un prénom svp !</div>
      </div>
      <!-- adresse -->
      <div class="input-group mb-2 has-validation">
        <input v-model="data.adresse" id="adhesion-adresse"
               type="text"
               class="form-control" placeholder="Adresse" aria-label="Adresse pour l'adhésion" required
               @keyup="majAdhesion('adresse', $event.target.value)">
        <div class="invalid-feedback">Une adresse svp !</div>
      </div>
      <!-- téléphone -->
      <div class="input-group mb-2 has-validation">
        <input v-model="data.tel" type="tel"
               class="form-control"
               placeholder="Fixe ou Mobile" pattern="^[0-9-+\s()]*$"
               aria-label="Adresse pour l'adhésion" required
               @keyup="majAdhesion('tel', $event.target.value)">
        <div class="invalid-feedback">Un numéro de téléphone svp !</div>
      </div>
    </div>
  </fieldset>
</template>

<script setup>
console.log('-> CardAdhesion.vue !')
// vue
import {useStore} from 'vuex'
import {computed, ref} from 'vue'

const emit = defineEmits(['update:adhesion'])

const store = useStore()
// attributs/props
const props = defineProps({
  adhesion: {
    type: Object,
    default: () => ({})
  }
})
let activationAdhesion = ref(store.state.adhesion.activation)

console.log('props.adhesion.activation =', props.adhesion.activation)
if (store.state.place.adhesion_obligatoire === true) {
  props.adhesion.activation = true
  store.commit('updateAdhesion', {key: 'activation', value: true})
  activationAdhesion.value = true
}

function majAdhesion(key, value) {
  console.log(key + " = " + value)
  store.commit('updateAdhesion', {key: key, value: value})
  if (key === 'activation') {
    activationAdhesion.value = store.state.adhesion.activation
  }
}

const data = computed({
  get: () => props.adhesion.value,
  set: (value) => emit('update:adhesion', value),
})

// etat adhésion est égal au choix de l'utilisateur
// let adhesion = ref(store.state.place.adhesion_obligatoire)

console.log('props =', props)

/*
// etat adhésion du lieu qui prime sur le choix de l'utilisateur
if (store.state.place.adhesion_obligatoire === true) {
  adhesion.value = store.state.place.adhesion_obligatoire
}
console.log('adhesion =', adhesion.value)
 */
</script>

<style scoped>

</style>