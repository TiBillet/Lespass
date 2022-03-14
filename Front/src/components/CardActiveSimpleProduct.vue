<template>
  <fieldset class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
    <legend>{{ product.name }}</legend>

    <div class="form-check form-switch">
      <input class="form-check-input" type="checkbox" :id="`active${product.uuid}`"
             @change="emitMajActiveSimpleProduct(product.uuid,'activation', $event.target.checked)" :checked="activeProd">
      <label class="form-check-label text-dark" :for="`active${product.uuid}`">Sélectionner/Déselctionner</label>
    </div>


    <div v-if="activeProd === true" >
      <!-- prix -->
      <div class="input-group mb-2 has-validation">
        <div class="col form-check mb-3" v-for="(price, index) in product.prices" :key="index">
          <input :value="price.uuid" class="form-check-input input-uuid-price" type="radio"
                 name="prixAdhesion" :id="`simpleproductuuidprice${product.name}${index}`"
                 @change="emitMajActiveSimpleProduct(product.uuid, 'uuidPrice', $event.target.value)" :checked="select">
          <label class="form-check-label" :for="`simpleproductuuidprice${product.name}${index}`">{{ price.prix }}€</label>
        </div>
      </div>
    </div>
  </fieldset>
</template>

<script setup>
/*
carte gérant:
- affichage du nom du produit
- active/désactive l'achat de se produit
- selection des différent prix de ce produit
- TODO: afficher image si présente
*/

// vue
import {ref} from 'vue'

// store
import {useStore} from '@/store'

const props = defineProps({
  product: Object,
  select: Boolean
})

const store = useStore()

if (store.formulaireBillet[store.currentUuidEvent]['activeSimpleProduct'] === undefined) {
  store.formulaireBillet[store.currentUuidEvent]['activeSimpleProduct'] = {}
}
if (store.formulaireBillet[store.currentUuidEvent].activeSimpleProduct[props.product.uuid] === undefined) {
  store.formulaireBillet[store.currentUuidEvent].activeSimpleProduct[props.product.uuid] = {
    name: props.product.name,
    activation: props.select,
    uuidPrice: props.product.prices[0].uuid
  }
}

const prod = store.formulaireBillet[store.currentUuidEvent].activeSimpleProduct[props.product.uuid]

const activeProd = ref(prod.activation)

function emitMajActiveSimpleProduct(uuidProduct, key, value) {
  emitter.emit('majActiveSimpleProduct', {uuidProduct: uuidProduct, key: key, value: value})
  if (key === 'activation') {
    activeProd.value = value
  }
}

</script>

<style scoped>

</style>