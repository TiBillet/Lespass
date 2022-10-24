<template>
    <fieldset class="shadow-sm p-3 mb-5 bg-body rounded"
            v-for="product in event.products.filter(prod => prod.categorie_article === 'S')"
            :key="product.uuid">
    <legend>
      <h3 class="font-weight-bolder text-info text-gradient align-self-start">Cashless</h3>
      <p>Les organisateurs du lieux utilisent un système de carte cashless. C'est gratuit, valable à vie
        et remboursable à tout moment. Souhaitez vous recharger maintenant pour gagner du temps ? Si vous n'avez pas
        encore de carte, elle vous sera remise, chargée, contre la confirmation de cette reservation.</p>
    </legend>
    <!-- email -->
    <div class="input-group mb-2">
      <span class="input-group-text" @click="inputFocus('charge_cashless')">Montant (€) : </span>
      <input id="charge_cashless" :value="getChargeCashless"
             @change.stop="updateChargeCashless($event.target.value)" type="number"
             :data-uuid="product.uuid" class="form-control">
    </div>

  </fieldset>
</template>

<script setup>

// store
import {storeToRefs} from 'pinia'
import {useEventStore} from '@/stores/event'

const {updateChargeCashless, getChargeCashless} = useEventStore()
const {event} = storeToRefs(useEventStore())

function inputFocus(id) {
  document.querySelector(`#${id}`).focus()
}
</script>

<style scoped>

</style>