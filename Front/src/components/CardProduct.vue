<template>
  <div v-for="product in manageProducts" :key="product.uuid">

    <Adhesion v-if="manageComponents.includes(product.name) === true && product.name === 'Adhesion'" :prices="product.prices"
              :form="true"/>

    <CardActiveSimpleProduct v-if="manageComponents.includes(product.name) === true && product.name === 'Don'" :product="product" :select="true"/>

    <!-- composants non gérés -->
    <fieldset v-if="manageComponents.includes(product.name) === false"
              class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
      <legend>{{ product.name }}</legend>
    </fieldset>
  </div>
</template>

<script setup>
// components
import Adhesion from '@/components/Adhesion.vue'
import CardActiveSimpleProduct from '@/components/CardActiveSimpleProduct.vue'

const props = defineProps({
  categories: Array, // produits contenu seulement et ordonnancement par index
  products: Object
})

const manageComponents = ['Adhesion', 'Don']

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