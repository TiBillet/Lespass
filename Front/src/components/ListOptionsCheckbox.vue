<template>
  <fieldset class="shadow-sm p-3 mb-5 bg-body rounded">
    <legend>Options</legend>
    <div class="input-group mb-2 has-validation">
        <span v-for="(option, index) in options" :key="index" class="form-switch me-3">
          <input v-if="option.activation === true" class="form-check-input" type="checkbox"
                 :id="`option-radio${option.uuid}`"
                 @change.stop="updateOptions($event.target.checked,option.uuid)" checked>
          <input v-else class="form-check-input" type="checkbox" :id="`option-radio${option.uuid}`"
                 @change.stop="updateOptions($event.target.checked,option.uuid)">
          <label class="form-check-label text-dark" :for="`option-radio${option.uuid}`">{{ option.name }}</label>
        </span>
    </div>
  </fieldset>

</template>

<script setup>
console.log('-> ListOptionsCheckbox.vue !')

// vue
import {ref} from 'vue'

// store
import {useStore} from '@/store'

// attributs/props
const props = defineProps({
  optionsCheckbox: Object,
  indexMemo: String
})
const store = useStore()

// mémorise par défaut
let record = true

// ini props.optionsCheckbox, desactive chaque option
const dataInit = JSON.parse(JSON.stringify(props.optionsCheckbox))
for (let i = 0; i < dataInit.length; i++) {
  dataInit[i]['activation'] = false
}

let options = ref({})


try {
  if (props.indexMemo === '' || props.indexMemo === undefined) {
    throw new Error(`Erreur index memo vide !`)
  }
  if (props.indexMemo !== '') {
    // init de base pour la persistance de tous les composants "CardAdhesion" dans le store
    if (store.memoComposants['ListOptionsCheckbox'] === undefined) {
      store.memoComposants['ListOptionsCheckbox'] = {}
    }
    // init de l'instance de clef "props.indexMemo"
    if (store.memoComposants.ListOptionsCheckbox[props.indexMemo] === undefined) {
      // console.log('Mémorisation initiale')
      store.memoComposants.ListOptionsCheckbox[props.indexMemo] = dataInit
      // quand a été initialisé le composant
      store.memoComposants.ListOptionsCheckbox[props.indexMemo]['initDate'] = new Date().toLocaleString()
      options.value = store.memoComposants.ListOptionsCheckbox[props.indexMemo]
    } else {
      // instance existante
      options.value = store.memoComposants.ListOptionsCheckbox[props.indexMemo]
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
  // init 'ListOptionsCheckbox' en dans le window.store
  if (window.store['ListOptionsCheckbox'] === undefined) {
    window.store['ListOptionsCheckbox'] = dataInit
    options.value = dataInit
  } else {
    options.value = window.store.ListOptionsCheckbox
  }

}
console.log('options.value =', options.value.length)

function updateOptions(value, uuidOptions) {
  console.log('-> fonc updateOptions, value =', value, '  --  uuidOptions =', uuidOptions)
  const option = options.value.find(opt => opt.uuid === uuidOptions)
  option.activation = value
  console.log('options =', JSON.stringify(options.value, null, 2))
}
</script>

<style>

</style>