<template>
  <div class="modal fade" id="membership-owned-modal" tabindex="-1" role="dialog"
       aria-labelledby="Exemple de message sous forme d'un modal."
       aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered modal-dialog-scrollable modal-xl" role="document">
      <div class="modal-content">
        <div class="modal-header">
          <h2 class="modal-title">Mes Adhésions</h2>
          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close">
            <span aria-hidden="true">&times;</span>
          </button>
        </div>
        <!-- contenu  -->
        <div class="modal-body">

          <!-- <pre class="text-dark">{{me.membership}}</pre> -->

          <fieldset class="shadow-sm p-3 mb-5 bg-body rounded" v-for="(adhesion, index) in me.membership" :key="index">
            <legend>
              <h5 class="font-weight-bolder text-info text-gradient align-self-start w-85">
                {{adhesion.product_name}} - {{adhesion.price_name}} {{adhesion.contribution_value}} €
              </h5>
            </legend>
            <div class="flex-row">
              <h5>Nom / prénom : {{adhesion.last_name}} {{adhesion.first_name}}</h5>
              <h5>Inscription : {{dateToFrenchFormat(adhesion.last_contribution)}}</h5>
              <h5>Echéance : {{dateToFrenchFormat(adhesion.deadline)}}</h5>
              <h5>Email : {{adhesion.email}}</h5>
            </div>
          </fieldset>

        </div>
        <div class="modal-footer">
          <button type="button" class="btn bg-gradient-secondary" data-bs-dismiss="modal">Close</button>
        </div>
      </div>
    </div>
  </div>

</template>

<script setup>
// store
import {storeToRefs} from 'pinia'
import {useLocalStore} from '@/stores/local'

const {me} = storeToRefs(useLocalStore())

function dateToFrenchFormat(dateString) {
  const nomMois = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
  const dateArray = dateString.split('T')[0].split('-')
  const mois = nomMois[parseInt(dateArray[1])]
  return dateArray[2] + ' ' + mois + ' ' + dateArray[0]
}

</script>

<style scoped>

</style>