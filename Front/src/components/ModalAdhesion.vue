<template>
  <!-- modal adhésion -->
  <div class="modal fade" id="modal-form-adhesion" tabindex="-1" role="dialog"
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
              <form @submit.prevent="validerAdhesion($event)" role="form text-left">

                <!-- prix -->
                <div class="input-group mb-2 has-validation">
                  <div id="prices-parent" class="col form-check mb-3" v-for="(price, index) in prices" :key="index">
                    <input :value="price.uuid"
                           class="form-check-input input-uuid-price" type="radio"
                           name="prixAdhesion" :id="`uuidPriceRadio${index}`">
                    <label class="form-check-label" :for="`uuidPriceRadio${index}`">{{ price.name }} - {{
                        price.prix
                      }}€</label>
                    <div v-if="index === 0" class="invalid-feedback">
                      Sélectionner un tarif d'adhésion svp !
                    </div>
                  </div>
                </div>

                <!-- nom -->
                <div class="input-group mb-2 has-validation">
                  <span class="input-group-text" id="basic-addon1">Nom</span>
                  <input :value="adhesionFormModal.lastName" type="text"
                         class="form-control" aria-label="Nom pour l'adhésion" required>
                  <div class="invalid-feedback">Un nom svp !</div>
                </div>

                <!-- prénom -->
                <div class="input-group mb-2 has-validation">
                  <span class="input-group-text" id="basic-addon1">Prénom</span>
                  <input :value="adhesionFormModal.firstName" type="text"
                         id="adhesion-prenom" class="form-control" aria-label="Prénom pour l'adhésion" required>
                  <div class="invalid-feedback">Un prénom svp !</div>
                </div>

                <!-- code postal -->
                <div class="input-group mb-2 has-validation">
                  <span class="input-group-text" id="basic-addon1">Code postal</span>
                  <input :value="adhesionFormModal.postalCode" id="adhesion-adresse"
                         type="number"
                         class="form-control" aria-label="Code postal" required>
                  <div class="invalid-feedback">Code postal svp !</div>
                </div>

                <!-- téléphone -->
                <div class="input-group mb-2 has-validation">
                  <span class="input-group-text" id="basic-addon1">Fixe ou Mobile</span>
                  <input :value="adhesionFormModal.phone" type="tel"
                         class="form-control" pattern="^[0-9-+\s()]*$"
                         aria-label="Fixe ou Mobile" required>
                  <div class="invalid-feedback">Un numéro de téléphone svp !</div>
                </div>

                <!-- date de naissance -->
                <div class="input-group mb-2 has-validation">
                  <span class="input-group-text" id="basic-addon1">Date de naissance</span>
                  <input :value="adhesionFormModal.birthDate" type="text"
                         class="form-control datepicker"
                         placeholder="Date de naissance" pattern="^[0-9-+\s()]*$"
                         aria-label="Date de naissance" required
                         @click="$event.target.type='date'; $event.target.click()">
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
// store
import {useStore} from '@/store'

// attributs/props
const props = defineProps({
  prices: Object
})

const store = useStore()

let adhesionFormModal = store.user
console.log('adhésion, modal: props.prices =', props.prices)

</script>

<style scoped>

</style>