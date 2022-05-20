<template>
  <fieldset v-if="getOptions.nb_options_checkbox > 0 && getOptions.nb_options_radio > 1"
            class="shadow-sm p-3 mb-5 bg-body rounded">
    <legend>
      <h3 class="font-weight-bolder text-info text-gradient align-self-start">Options</h3>
    </legend>

    <!-- options checkbox -->
    <div v-if="getOptions.nb_options_checkbox > 0" class="input-group mb-2 has-validation">
        <span v-for="(option, index) in getOptions.options_checkbox" :key="index" class="form-switch me-3">
          <input v-if="option.activation === true" class="form-check-input" type="checkbox"
                 :id="`option-checkbox${option.uuid}`"
                 @change.stop="updateOptions('options_checkbox',$event.target.checked,option.uuid)" checked>
          <input v-else class="form-check-input" type="checkbox" :id="`option-checkbox${option.uuid}`"
                 @change.stop="updateOptions('options_checkbox',$event.target.checked,option.uuid)">
          <label class="form-check-label text-dark" :for="`option-checkbox${option.uuid}`">{{ option.name }}</label>
        </span>
    </div>

    <!-- options radio -->
    <div v-if="getOptions.nb_options_radio > 1" class="input-group mb-2 has-validation">
      <div v-for="(option, index) in getOptions.options_radio" :key="index" class="form-check ps-0 me-3">
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
console.log('-> CardOptions.vue !')

// store
import {storeToRefs} from 'pinia'
import {useEventStore} from '@/stores/event'

// state event
const {event} = storeToRefs(useEventStore())
// action(s) du state event
const {getOptions, updateOptions} = useEventStore()

/*
// vue
import {ref} from 'vue'

// store
import {useStore} from '@/store'

// attributs/props
const props = defineProps({
  uuidEvent: String,
})
const store = useStore()

// mémorise par défaut
let record = true

// ini props.options desactive chaque option
//checkbox (convert proxy to array)
const dataInitCheckbox = JSON.parse(JSON.stringify(props.event.options.checkbox))
for (let i = 0; i < dataInitCheckbox.length; i++) {
  dataInitCheckbox[i]['activation'] = false
}
// radio (convert proxy to array)
const dataInitRadio = JSON.parse(JSON.stringify(props.options.radio))
for (let i = 0; i < dataInitRadio.length; i++) {
  dataInitRadio[i]['activation'] = false
}

const dataInit = {
  radio: dataInitRadio,
  checkbox: dataInitCheckbox
}

let options = ref({})

try {
  if (props.indexMemo === '' || props.indexMemo === undefined) {
    throw new Error(`Erreur index memo vide !`)
  }
  if (props.indexMemo !== '') {
    // init de base pour la persistance de tous les composants "CardAdhesion" dans le store
    if (store.memoComposants['Options'] === undefined) {
      store.memoComposants['Options'] = {}
    }
    // init de l'instance de clef "props.indexMemo"
    if (store.memoComposants.Options[props.indexMemo] === undefined) {
      // console.log('Mémorisation initiale')
      store.memoComposants.Options[props.indexMemo] = dataInit
      // quand a été initialisé le composant
      store.memoComposants.Options[props.indexMemo]['initDate'] = new Date().toLocaleString()
      options.value = store.memoComposants.Options[props.indexMemo]
    } else {
      // instance existante
      options.value = store.memoComposants.Options[props.indexMemo]
      // console.log('Mémorisation existante')
    }
  }
} catch (erreur) {
  record = false
  console.log('Mémorisation du composant impossible')
  // utilisation hors local storage
  if (window.store === undefined) {
    window.store = {}
  }
  // init 'Options' en dans le window.store
  if (window.store['Options'] === undefined) {
    window.store['Options'] = dataInit
    options.value = dataInit
  } else {
    options.value = window.store.Options
  }

}
// console.log('options.value =', options.value)

function updateOptions(inputType, value, uuidOptions) {
  // console.log('-> fonc updateOptions, type =', inputType, '  --  value =', value, '  --  uuidOptions =', uuidOptions)
  if (inputType === 'radio') {
    // toutes les activation radio à false
    for (let i = 0; i < options.value.radio.length; i++) {
      options.value.radio[i].activation = false
    }
  }
  const option = options.value[inputType].find(opt => opt.uuid === uuidOptions)
  option.activation = value
}

 */
</script>

<style scoped>
</style>