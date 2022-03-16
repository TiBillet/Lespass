<template>
  <fieldset class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
    <legend>options</legend>
    <div class="input-group mb-2 has-validation">
      <span v-for="(option, index) in currentEvent.options_radio" :key="index" class="form-check me-3">
        <input class="form-check-input" type="radio"  name="option1" :id="`option-radio${option.uuid}-${index}`" :value="option.uuid"
               @change="emitMajOptionsEvent('option1',$event.target.value)">
        <label class="form-check-label text-dark" :for="`option-radio${option.uuid}-${index}`">{{ option.name }}</label>
      </span>
    </div>


    <div class="input-group mb-2 has-validation">
      <span v-for="(option, index) in currentEvent.options_checkbox" :key="index" class="form-switch me-3 me-3">
        <input class="form-check-input" type="checkbox" :id="`option-radio${option.uuid}`"
               @change="emitMajOptionsEvent('check', $event.target.checked,option.uuid)">
        <label class="form-check-label text-dark" :for="`option-radio${option.uuid}`">{{ option.name }}</label>
      </span>
    </div>

  </fieldset>
</template>

<script setup>
// store
import {useStore} from '@/store'

const store = useStore()
const currentEvent = store.events.filter(evt => evt.uuid === store.currentUuidEvent)[0]

if ( store.formulaireBillet[store.currentUuidEvent]['options'] === undefined) {
  store.formulaireBillet[store.currentUuidEvent]['options'] = {}
}

console.log('currentEvent.options_radio =', Object.fromEntries(currentEvent.options_radio))

for (const key in currentEvent.options_radio) {
  const obj = currentEvent.options_radio[key]
  console.log('obj =', obj.uuid)
}


function emitMajOptionsEvent(name, value, uuid) {
  emitter.emit('majOptionsEvent', {name: name, value: value, uuid: uuid})
}

</script>

<style>

</style>