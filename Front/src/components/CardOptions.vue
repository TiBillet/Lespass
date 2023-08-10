<template>
  <fieldset v-if="getEventFormOptions.nbOptionsCheckbox > 0 || getEventFormOptions.nbOptionsRadio > 1"
            class="shadow-sm p-3 mb-5 bg-body rounded">
    <legend>
      <div class="d-flex flex-row align-items-center justify-content-between">
        <h3 class="font-weight-bolder text-info text-gradient align-self-start">Options</h3>
        <button class="btn btn-primary ms-3" type="button" title="Annuler les options !" @click="resetEventOptions()">
          <span class="btn-inner--icon">Annuler<i class="fa fa-trash ms-1" aria-hidden="true"></i></span>
        </button>
      </div>
    </legend>

    <!-- options radio -->
    <div>Choix unique:</div>
    <div v-if="getEventFormOptions.nbOptionsRadio > 1" class="input-group mb-2 has-validation">
      <div v-for="(option, index) in getEventFormOptions.optionsRadio" :key="index" class="form-check ps-0 me-3">
        <input class="form-check-input " type="radio" name="event-option-radio" :id="`option-event-radio${index}`"
               style="margin-left: 0;"
               v-model="getEventForm.optionRadioSelected" :value="option.uuid">
        <label class="form-check-label" :for="`option-event-radio${index}`">
          {{ option.name }}
        </label>
      </div>
    </div>

    <!-- options checkbox -->
    <div>Choix multiples:</div>
    <div v-if="getEventFormOptions.nbOptionsCheckbox > 0" class="input-group mb-2 has-validation">
      <div v-for="(option, index) in getEventFormOptions.optionsCheckbox" :key="index"
           class="form-check form-switch me-3">
        <input class="form-check-input" type="checkbox" :id="`option-event-checkbox${option.uuid}`"
               v-model="option['checked']" true-value="true" false-value="false">
        <label class="form-check-label text-dark ms-0" :for="`option-event-checkbox${option.uuid}`">{{
            option.name
          }}</label>
      </div>
    </div>

  </fieldset>
</template>

<script setup>
// console.log('-> CardOptions.vue !')
// store
import { useSessionStore } from '../stores/session'

const { getEventFormOptions, getEventForm, resetEventOptions } = useSessionStore()
</script>

<style scoped></style>