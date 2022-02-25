<template>


    <!-- Position -->
    <fieldset class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
      <legend>Position</legend>
      <div class="d-flex flex-row">
        <div class="form-check">
          <input value="fosse" id="position1" class="form-check-input" type="radio"
                 v-model="store.state.formulaireBillet[uuidEvent].position"
                 @change="majFormulaireBillet($event, 'position')">
          <label class="form-check-label" for="position1">Fosse</label>
          <div class="invalid-feedback">Position, svp !</div>
        </div>
        <div class="form-check ms-4">
          <input value="gradin" id="position2" class="form-check-input" type="radio"
                 v-model="store.state.formulaireBillet[uuidEvent].position"
                 @change="majFormulaireBillet($event, 'position')">
          <label class="form-check-label" for="position2">Gradin</label>
          <div class="invalid-feedback">Position, svp !</div>
        </div>

      </div>
    </fieldset>

    <BilletInputs :data-product="dataProduct" :uuid-event="uuidEvent"/>

</template>

<script setup>
console.log('-> CardBillet.vue')

// vue
import {useStore} from 'vuex'
import {ref} from 'vue'

// composant
import BilletInputs from './BilletInputs.vue'

const store = useStore()
// attributs/props
const props = defineProps({
  dataProduct: Object,
  uuidEvent: String
})


function majFormulaireBillet(event, sujet) {
  console.log('-> majFormulaireBillet')
  let valeur = event.target.value
  if (sujet === 'attentionEmail') {
    valeur = attentionEmail.value
  }
  if (sujet === 'adhesion') {
    valeur = adhesion.value
  }
  store.commit('majFormulaireBillet', {uuidEvent: props.uuidEvent, sujet: sujet, valeur: valeur})
}

</script>

<style scoped>

</style>