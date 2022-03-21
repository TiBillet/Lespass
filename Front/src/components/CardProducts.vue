<template>
  <div v-for="product in manageProducts" :key="product.uuid">

    <CardAdhesion v-if="manageComponents.includes(product.categorie_article) === true && product.categorie_article === 'A'" :prices="product.prices" :memo="store.currentUuidEvent" :obligatoire="store.place.adhesion_obligatoire"/>


    <CardActiveSimpleProduct v-if="manageComponents.includes(product.categorie_article) === true && product.categorie_article === 'D'" :product="product" :select="true"/>

    <CardBillet v-if="manageComponents.includes(product.categorie_article) === true && (product.categorie_article === 'B' || product.categorie_article === 'F')" :product="product"/>
    <!-- composants non gérés -->
    <fieldset v-if="manageComponents.includes(product.categorie_article) === false"
              class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
      <legend>{{ product.name }}</legend>
    </fieldset>
  </div>
</template>

<script setup>
// store
import {useStore} from '@/store'

// components
import CardAdhesion from '@/components/CardAdhesion.vue'
import CardActiveSimpleProduct from '@/components/CardActiveSimpleProduct.vue'
import CardBillet from '@/components/CardBillet.vue'

const props = defineProps({
  categories: Array, // produits contenu seulement et ordonnancement par index
  products: Object
})
const store = useStore()
const manageComponents = ['A', 'D', 'B', 'F']

// ordonnancement par le tableau catégories des produits et seulement ceux contenue dans celui-ci
const manageProducts = []
for (const categoriesKey in props.categories) {
  const categorie = props.categories[categoriesKey]
  for (const productKey in props.products) {
    const product = props.products[productKey]
    if (product.categorie_article === categorie) {
      manageProducts.push(product)
    }
  }
}
console.log('manageProducts =', manageProducts)
</script>

<style>
</style>