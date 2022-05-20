<template>
  <fieldset class="shadow-sm p-3 mb-5 bg-body rounded">
    <legend>
      <h3 class="font-weight-bolder text-info text-gradient align-self-start">Don</h3>
    </legend>
<!--
    <div class="form-check form-switch">
      <input class="form-check-input" type="checkbox" :id="`active-simple-product${simpleProduct.uuid}`"
             @change="updateActiveSimpleProduct('activation', $event.target.checked)"
             :checked="activation">
      <label class="form-check-label text-dark" :for="`active-simple-product${simpleProduct.uuid}`">
        Je donne un euro de plus pour soutenir les actions de la coopérative <a
          href="https://wiki.tibillet.re">TiBillet</a> en faveur de la culture et de l'économie sociale et solidaire.
      </label>
    </div>

    <div v-if="simpleProduct.activation === true">
      // prix
      <div class="input-group mb-2 has-validation">
        <div class="col form-check" v-for="(price, index) in simpleProduct.prices" :key="index">
          // sélectionne automatiquement le premier prix
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
-->
  </fieldset>
</template>

<script setup>
console.log('-> CordDon.vue')

// store
import {storeToRefs} from 'pinia'
import {useAllStore} from "@/stores/all"

const {place} = storeToRefs(useAllStore())

console.log('place =', place.value)

const props = defineProps({
  activation: Boolean
})

</script>

<style scoped>

</style>