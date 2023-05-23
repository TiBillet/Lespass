<template>
  <fieldset v-if="getOptions.nbOptionsCheckbox > 0 || getOptions.nbOptionsRadio > 1"
            class="shadow-sm p-3 mb-5 bg-body rounded">
    <legend>
      <div class="d-flex flex-row align-items-center justify-content-between">
        <h3 class="font-weight-bolder text-info text-gradient align-self-start">Options</h3>
          <button class="btn btn-primary ms-3" type="button" title="Annuler les options !" @click="allOptionsFalse()">
          <span class="btn-inner--icon">Annuler<i class="fa fa-trash ms-1" aria-hidden="true"></i></span>
        </button>
      </div>
    </legend>


    <!-- options checkbox -->
    <div v-if="getOptions.nbOptionsCheckbox > 0" class="input-group mb-2 has-validation">
        <span v-for="(option, index) in getOptions.optionsCheckbox" :key="index" class="form-switch me-3">
          <input v-if="option.activation === true" class="form-check-input" type="checkbox"
                 :id="`option-checkbox${option.uuid}`"
                 @change.stop="updateOptions('options_checkbox',$event.target.checked,option.uuid)" checked>
          <input v-else class="form-check-input" type="checkbox" :id="`option-checkbox${option.uuid}`"
                 @change.stop="updateOptions('options_checkbox',$event.target.checked,option.uuid)">
          <label class="form-check-label text-dark" :for="`option-checkbox${option.uuid}`">{{ option.name }}</label>
        </span>
    </div>

    <!-- options radio -->
    <div v-if="getOptions.nbOptionsRadio > 1" class="input-group mb-2 has-validation">
      <div v-for="(option, index) in getOptions.optionsRadio" :key="index" class="form-check ps-0 me-3">
        <input v-if="option.activation === true" class="form-check-input " type="radio" name="OptionRadioName"
               :id="`flexOptionRadio${index}`"
               style="margin-left: 0;"
               @change.stop="updateOptions('options_radio',$event.target.checked,option.uuid)" checked>
        <input v-else class="form-check-input " type="radio" name="OptionRadioName" :id="`flexOptionRadio${index}`"
               style="margin-left: 0;"
               @change.stop="updateOptions('options_radio',$event.target.checked,option.uuid)">
        <label class="form-check-label" :for="`flexOptionRadio${index}`">
          {{ option.name }}
        </label>
      </div>
    </div>

  </fieldset>
</template>

<script setup>
// console.log('-> CardOptions.vue !')

// store
import { storeToRefs } from 'pinia'
import { useEventStore } from '@/stores/event'

// state event
const { event } = storeToRefs(useEventStore())
// action(s) du state event
const { getOptions, updateOptions, allOptionsFalse } = useEventStore()
</script>

<style scoped>
.style-h3 {
  font-size: 1.875rem;
  line-height: 1.375;
}
</style>