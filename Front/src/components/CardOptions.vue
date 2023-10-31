<template>
  <fieldset v-if="getEventFormOptions.nbOptionsCheckbox > 0 || getEventFormOptions.nbOptionsRadio > 1"
            class="shadow-sm p-3 mb-5 bg-body rounded">
    <legend>
      <div class="d-flex flex-row align-items-center justify-content-between">
        <h3 class="font-weight-bolder text-info text-gradient align-self-start">Options</h3>
        <button class="btn tibillet-bg-primary ms-3" type="button" title="Annuler les options !" @click="resetEventOptions()">
          <i class="fa fa-trash ms-1" aria-hidden="true"></i><span class="btn-inner--icon ms-1">Annuler</span>
        </button>
      </div>
    </legend>

    <!-- options radio -->
    <div v-if="getEventFormOptions.nbOptionsRadio > 1">Choix unique:</div>
    <InputRadio v-if="getEventFormOptions.nbOptionsRadio > 1" :data-radio="convertOptionsRadio()" v-model="getEventForm.optionRadioSelected"
                  msg-role="Option évènement choix unique" :validation="false" />

    <!-- options checkbox -->
    <div v-if="getEventFormOptions.nbOptionsCheckbox > 0">Choix multiples:</div>
    <div v-if="getEventFormOptions.nbOptionsCheckbox > 0" class="input-group mb-2 has-validation">
      <div v-for="(option, index) in getEventFormOptions.optionsCheckbox" :key="index"
           class="form-check form-switch me-3">
          <InputSwitch  v-model="option['checked']" :label="option.name" :true-value="true" :false-value="false"
          msg-role="'Option évènement choix multiples - ' + option.name"/>
      </div>
    </div>
  </fieldset>
</template>

<script setup>
// console.log('-> CardOptions.vue !')
// store
import { useSessionStore } from '../stores/session'

// components
import InputRadio from './InputRadio.vue'
import InputSwitch from './InputSwitch.vue';

const { getEventFormOptions, getEventForm, resetEventOptions } = useSessionStore()

function convertOptionsRadio() {
  let options = []
  getEventFormOptions.optionsRadio .forEach(data => {
    options.push({
      label: data.name,
      value: data.uuid
    })
  })
  return { options, name: 'membership-options-radio'}
}

</script>

<style scoped></style>