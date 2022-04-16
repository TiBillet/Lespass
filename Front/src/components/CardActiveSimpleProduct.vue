<template>
<!--  <fieldset class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded">-->
  <fieldset class="col-md-6 shadow-sm p-3 mb-5 bg-body rounded">

    <legend>{{ product.name }}</legend>

    <div class="form-check form-switch">
      <input class="form-check-input" type="checkbox" :id="`active-simple-product${simpleProduct.uuid}`"
             @change="updateActiveSimpleProduct('activation', $event.target.checked)"
             :checked="simpleProduct.activation">
      <label class="form-check-label text-dark" :for="`active-simple-product${simpleProduct.uuid}`">
        Je donne un euro de plus pour soutenir les actions de la coopérative <a href="https://wiki.tibillet.re">TiBillet</a> en faveur de la culture et de l'économie sociale et solidaire.
      </label>
    </div>

    <div v-if="simpleProduct.activation === true">
      <!-- prix -->
      <div class="input-group mb-2 has-validation">
        <div class="col form-check" v-for="(price, index) in simpleProduct.prices" :key="index">
          <!-- sélectionne automatiquement le premier prix -->
          <input v-if="index === 0" :value="price.uuid"
                 :class="`form-check-input simple-product-active-${nameMemo}-uuid-price`" type="radio"
                 :name="`prix${nameMemo}`" :id="`simpleproductuuidprice${nameMemo}${index}`"
                 @change="updateActiveSimpleProduct('uuidPrix', $event.target.value)" checked>

          <input v-else :value="price.uuid" :class="`form-check-input simple-product-active-${nameMemo}-uuid-price`"
                 type="radio"
                 :name="`prix${nameMemo}`" :id="`simpleproductuuidprice${nameMemo}${index}`"
                 @change="updateActiveSimpleProduct('uuidPrix', $event.target.value)">
          <label class="form-check-label" :for="`simpleproductuuidprice${nameMemo}${index}`">{{ price.prix }}€</label>
        </div>
      </div>
    </div>

  </fieldset>
</template>

<script setup>
console.log('-> CardActiveSimpleProduct.vue')
/*
carte gérant:
- affichage du nom du produit
- active/désactive l'achat de se produit
- selection automatiquement le premier prix
- TODO: afficher image si présente
*/
// vue
import {ref, onMounted, onUpdated} from 'vue'

// store
import {useStore} from '@/store'

const props = defineProps({
  product: Object,
  nameMemo: String,
  indexMemo: String,
  activation: Boolean
})
const store = useStore()

// mémorise par défaut
let record = true

let simpleProduct = ref({})

// mémorise le composant dans le store ou la variable globale window
try {
  if (props.indexMemo === '' || props.indexMemo === undefined || props.nameMemo === '' || props.nameMemo === undefined) {
    throw new Error(`Erreur index memo vide !`)
  }

  if (props.indexMemo !== '' && props.nameMemo !== '') {
    // init de base pour la persistance de tous les composants "nameMemo" dans le store
    if (store.memoComposants[props.nameMemo] === undefined) {
      store.memoComposants[props.nameMemo] = {}
    }

    // init de l'instance de clef "props.indexMemo"
    if (store.memoComposants[props.nameMemo][props.indexMemo] === undefined) {
      console.log('Mémorisation initiale')
      store.memoComposants[props.nameMemo][props.indexMemo] = props.product
      simpleProduct.value = props.product
      simpleProduct.value['activation'] = props.activation
      simpleProduct.value['uuidPrix'] = props.product.prices[0].uuid
      console.log(`simpleProduct.value['uuidPrix'] =`, simpleProduct.value['uuidPrix'])
      store.memoComposants[props.nameMemo][props.indexMemo]['initDate'] = new Date().toLocaleString()
    } else {
      // instance existante
      simpleProduct.value = store.memoComposants[props.nameMemo][props.indexMemo]
      // console.log('Mémorisation existante')
    }
  } else {
    throw new Error(`Erreur index memo et/ou  name memo vide !`)
  }
} catch (erreur) {
  record = false
  // console.log(erreur)
  console.log('Mémorisation du composant impossible')
  // instance sans mémorisation dans le store
  simpleProduct.value = props.product
  simpleProduct.value['activation'] = props.activation
  // utilisation hors local storage
  if (window.store === undefined) {
    window.store = {}
  }
  if (window.store[props.nameMemo] === undefined) {
    window.store[props.nameMemo] = simpleProduct.value
    window.store[props.nameMemo]['activation'] = props.activation
    window.store[props.nameMemo]['uuidPrix'] = ''
  } else {
    simpleProduct.value = window.store[props.nameMemo]
  }

}

// console.log('simpleProduct.value =', JSON.stringify(simpleProduct.value, null, 2))

function updateRadioButon() {
  const eles = document.querySelectorAll(`.simple-product-active-${props.nameMemo}-uuid-price`)
  for (let i = 0; i < eles.length; i++) {
    const ele = eles[i]
    console.log('-> ele =', ele)
    ele.removeAttribute('checked')
    if (ele.value === simpleProduct.value.uuidPrix) {
      ele.checked = true
    }
  }
}

onMounted(() => {
  updateRadioButon()
})

onUpdated(() => {
  updateRadioButon()
})


function updateActiveSimpleProduct(key, value) {
  // console.log(key + " = " + value)
  if (record === true) {
    simpleProduct.value[key] = value
  }
}
</script>

<style>
</style>