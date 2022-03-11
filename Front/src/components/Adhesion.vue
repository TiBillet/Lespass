<template>
  <!-- pour formulaire -->
  <fieldset v-if="adhesion.form === true" class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
    <legend>Adhésion</legend>

    <div class="form-check form-switch">
      <input v-if="adhesion.adhesionObligatoire === true" class="form-check-input" type="checkbox"
             id="etat-adhesion" checked disabled>
      <input v-else class="form-check-input" type="checkbox" id="etat-adhesion"
             @change="emitMajAdhesion('activation', $event.target.checked)" :checked="adhesionActivation">
      <label class="form-check-label text-dark" for="etat-adhesion">Prendre une adhésion
        associative.</label>
    </div>

    <div v-if="adhesionActivation === true">
      <!-- prix -->
      <div class="row has-validation">
        <div class="col form-check mb-3" v-for="(price, index) in adhesion.prices" :key="index">
          <input v-if="index === 0" :value="price.uuid" class="form-check-input input-uuid-price" type="radio"
                 name="prixAdhesion" :id="`uuidPriceRadio${index}`"
                 @change="emitMajAdhesion('uuidPrice', $event.target.value)">
          <input v-else :value="price.uuid" class="form-check-input input-uuid-price" type="radio"
                 name="prixAdhesion" :id="`uuidPriceRadio${index}`"
                 @change="emitMajAdhesion('uuidPrice', $event.target.value)">
          <label class="form-check-label" :for="`customRadio${index}`">{{ price.name }} - {{ price.prix }}€</label>
          <div v-if="index === 0" id="uuid-price-error" class="invalid-feedback">
            Sélectionner un tarif d'adhésion svp !
          </div>
        </div>
      </div>

      <!-- nom -->
      <div class="input-group mb-2 has-validation">
        <input :value="adhesion.nom" type="text"
               class="form-control"
               placeholder="Nom" aria-label="Nom pour l'adhésion" required
               @keyup="emitMajAdhesion('nom', $event.target.value)">
        <div class="invalid-feedback">Un nom svp !</div>
      </div>
      <!-- prénom -->
      <div class="input-group mb-2 has-validation">
        <input :value="adhesion.prenom" type="text"
               id="adhesion-prenom" class="form-control"
               placeholder="Prénom" aria-label="Prénom pour l'adhésion" required
               @keyup="emitMajAdhesion('prenom', $event.target.value)">
        <div class="invalid-feedback">Un prénom svp !</div>
      </div>
      <!-- adresse -->
      <div class="input-group mb-2 has-validation">
        <input :value="adhesion.adresse" id="adhesion-adresse"
               type="text"
               class="form-control" placeholder="Adresse" aria-label="Adresse pour l'adhésion" required
               @keyup="emitMajAdhesion('adresse', $event.target.value)">
        <div class="invalid-feedback">Une adresse svp !</div>
      </div>
      <!-- téléphone -->
      <div class="input-group mb-2 has-validation">
        <input :value="adhesion.tel" type="tel"
               class="form-control"
               placeholder="Fixe ou Mobile" pattern="^[0-9-+\s()]*$"
               aria-label="Adresse pour l'adhésion" required
               @keyup="emitMajAdhesion('tel', $event.target.value)">
        <div class="invalid-feedback">Un numéro de téléphone svp !</div>
      </div>
    </div>

  </fieldset>

  <!-- modal adhésion -->
  <div v-if="adhesion.form === false" class="modal fade" id="modal-form-adhesion" tabindex="-1" role="dialog"
       aria-labelledby="modal-form-adhesion"
       aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered modal-" role="document">
      <div class="modal-content">
        <div class="modal-body p-0">
          <div class="card card-plain">
            <div class="card-header pb-0 text-left">
              <h3 class="font-weight-bolder text-info text-gradient">Adhésion</h3>
            </div>
            <div class="card-body">
              <form @submit.prevent="emitValiderAdhesion($event)" role="form text-left">

                <!-- nom -->
                <div class="input-group mb-2 has-validation">
                  <input :value="adhesion.nom" type="text"
                         class="form-control"
                         placeholder="Nom" aria-label="Nom pour l'adhésion" required
                         @keyup="emitMajAdhesion('nom', $event.target.value)">
                  <div class="invalid-feedback">Un nom svp !</div>
                </div>
                <!-- prénom -->
                <div class="input-group mb-2 has-validation">
                  <input :value="adhesion.prenom" type="text"
                         id="adhesion-prenom" class="form-control"
                         placeholder="Prénom" aria-label="Prénom pour l'adhésion" required
                         @keyup="emitMajAdhesion('prenom', $event.target.value)">
                  <div class="invalid-feedback">Un prénom svp !</div>
                </div>
                <!-- adresse -->
                <div class="input-group mb-2 has-validation">
                  <input :value="adhesion.adresse" id="adhesion-adresse"
                         type="text"
                         class="form-control" placeholder="Adresse" aria-label="Adresse pour l'adhésion" required
                         @keyup="emitMajAdhesion('adresse', $event.target.value)">
                  <div class="invalid-feedback">Une adresse svp !</div>
                </div>
                <!-- téléphone -->
                <div class="input-group mb-2 has-validation">
                  <input :value="adhesion.tel" type="tel"
                         class="form-control"
                         placeholder="Fixe ou Mobile" pattern="^[0-9-+\s()]*$"
                         aria-label="Adresse pour l'adhésion" required
                         @keyup="emitMajAdhesion('tel', $event.target.value)">
                  <div class="invalid-feedback">Un numéro de téléphone svp !</div>
                </div>


                <div class="text-center">
                  <button type="submit" class="btn btn-round bg-gradient-info btn-lg w-100 mt-4 mb-0">Valider</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>


</template>

<script setup>
console.log('-> Adhesion.vue !')
// vue
import {ref} from 'vue'

/*
// store
import {useStore} from '@/store'

const store = useStore()
 */
// attributs/props
const props = defineProps({
  adhesion: Object
})

const adhesionActivation = ref(props.adhesion.activation)

console.log('props.adhesion =', props.adhesion)

function emitMajAdhesion(key, value) {
  console.log(key + " = " + value)
  emitter.emit('majAdhesion', {key: key, value: value})
  if (key === 'activation') {
    adhesionActivation.value = value
  }
}

function emitValiderAdhesion(event) {
  if (event.target.checkValidity() === true) {
    // TODO: emitter.emit('validerAdhesion', {})

    // ferme le modal
    const elementModal = document.querySelector('#modal-form-adhesion')
    const modal = bootstrap.Modal.getInstance(elementModal) // Returns a Bootstrap modal instance
    modal.hide()

    // TODO: si réservation adhésion ok => modifier le bouton "adhésion" en info. adhérant

    console.log('Valider adhésion ok !')
  }
}
</script>

<style>
</style>