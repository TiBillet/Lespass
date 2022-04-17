<template>
  <div v-for="product in manageProducts" :key="product.uuid">

    <CardAdhesion
        v-if="manageComponents.includes(product.categorie_article) === true && product.categorie_article === 'A'"
        :prices="product.prices" :index-memo="store.currentUuidEvent" :obligatoire="store.place.adhesion_obligatoire"/>

    <!-- name-memo = nom de l'enristrement dans le "store.memoComposants", index-memo = évènement en cours et activation = active la sélection du produit -->
    <CardActiveSimpleProduct
        v-if="manageComponents.includes(product.categorie_article) === true && product.categorie_article === 'D'"
        :product="product" name-memo="Don" :index-memo="store.currentUuidEvent" :activation="true"/>

    <CardBillet
        v-if="manageComponents.includes(product.categorie_article) === true && (product.categorie_article === 'B' || product.categorie_article === 'F')"
        :product="product" :index-memo="store.currentUuidEvent"/>
    <!-- composants non gérés -->
    <fieldset v-if="manageComponents.includes(product.categorie_article) === false"
              class="shadow-sm p-3 mb-5 bg-body rounded">
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
</script>

<style>
</style>