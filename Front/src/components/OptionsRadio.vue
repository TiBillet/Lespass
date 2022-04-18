<template>
  <fieldset class="shadow-sm p-3 mb-5 bg-body rounded">
    <legend>
      <h3 class="font-weight-bolder text-info text-gradient align-self-start">{{ name }}</h3>
    </legend>
    <div class="input-group mb-2 has-validation">

      <div v-for="(option, index) in options" :key="index" class="form-check ps-0 me-3">
        <input v-if="option.selection === true" class="form-check-input " type="radio" name="OptionRadioName"
               :id="`flexOptionRadio${index}`"
               style="margin-left: 0;"
               @change.stop="updateOptions($event.target.checked,option.uuid)" checked>
        <input v-else class="form-check-input " type="radio" name="OptionRadioName" :id="`flexOptionRadio${index}`"
               style="margin-left: 0;"
               @change.stop="updateOptions($event.target.checked,option.uuid)">
        <label class="form-check-label" :for="`flexOptionRadio${index}`">
          {{ option.name }}
        </label>
      </div>

    </div>
  </fieldset>
</template>

<script setup>
console.log('-> OptionsRadio.vue !')
// vue
import {ref} from 'vue'

// store
import {useStore} from '@/store'

// attributs/props
const props = defineProps({
  optionsRadio: Object,
  indexMemo: String,
  name: String
})
const store = useStore()

// mémorise par défaut
let record = true

// TODO: réagencer le tableau si options_radio pas ordonnées ?

// ini props.optionsRadio, desactive chaque option
const dataInit = JSON.parse(JSON.stringify(props.optionsRadio))
for (let i = 0; i < dataInit.length; i++) {
  dataInit[i]['selection'] = false
}

let options = ref({})

try {
  if (props.indexMemo === '' || props.indexMemo === undefined) {
    throw new Error(`Erreur index memo vide !`)
  }
  if (props.indexMemo !== '') {
    // init de base pour la persistance de tous les composants "CardAdhesion" dans le store
    if (store.memoComposants['OptionsRadio'] === undefined) {
      store.memoComposants['OptionsRadio'] = {}
    }
    // init de l'instance de clef "props.indexMemo"
    if (store.memoComposants.OptionsRadio[props.indexMemo] === undefined) {
      // console.log('Mémorisation initiale')
      store.memoComposants.OptionsRadio[props.indexMemo] = dataInit
      // quand a été initialisé le composant
      store.memoComposants.OptionsRadio[props.indexMemo]['initDate'] = new Date().toLocaleString()
      options.value = store.memoComposants.OptionsRadio[props.indexMemo]
    } else {
      // instance existante
      options.value = store.memoComposants.OptionsRadio[props.indexMemo]
      console.log('Mémorisation existante')
    }
  }
} catch (erreur) {
  record = false
  console.log('Mémorisation du composant impossible')
  // utilisation hors local storage
  if (window.store === undefined) {
    window.store = {}
  }
  // init 'OptionsRadio' en dans le window.store
  if (window.store['OptionsRadio'] === undefined) {
    window.store['OptionsRadio'] = dataInit
    options.value = dataInit
  } else {
    options.value = window.store.OptionsRadio
  }

}
console.log('options.value =', options.value)

function updateOptions(status, uuid) {
  // console.log('-> fonc updateOptions, status=', status, '  --  uuid=', uuid)
  // toutes les sélection à false
  for (let i = 0; i < options.value.length; i++) {
    options.value[i].selection = false
  }
  // maj option sélectionnée à true
  const option = options.value.find(opt => opt.uuid === uuid)
  option.selection = status
}

</script>

<style scoped>
</style>