<template>
 <div v-for="product in products" :key="product.uuid">
   <div>{{ product}}</div>
   <hr>
    <!-- produits "F" et "B" --
    <fieldset v-if="['F','B'].includes(product.categorie_article)"
              class="shadow-sm p-3 mb-5 bg-body rounded test-card-billet">
      <legend>
        <img v-if="image === true" :src="product.img" class="image-product" :alt="product.name" :style="stImage">
        <h3 v-else class="font-weight-bolder text-info text-gradient align-self-start">{{ product.name }}</h3>
        <h6 v-if="product.short_description !== null" class="text-info">{{ product.short_description }}</h6>
      </legend>
      <div v-for="price in product.prices" :key="price.uuid" class="mt-5">
        <section
            v-if="price.adhesion_obligatoire === null || (getUserHasThisMembership(price.adhesion_obligatoire) && getIsLogin)">
          <div>{{ price.name }}</div>
        </section>
        /-- adhesion_obligatoire === true --
        <section v-else>
          /-- nom tarif --
          <h4 class="font-weight-bolder text-dark text-gradient">
            {{ price.name.toLowerCase() }} : {{ price.prix }} €
          </h4>
          <div v-if="getIsLogin === false" class="ms-2 mt-0 text-info font-weight-500">
            Vous devez être connecter pour accéder à ce produit.
          </div>
          <div v-else>
            <button class="btn btn-primary mb-0" type="button"
                      style="border-top-right-radius: 30px; border-bottom-right-radius: 30px;"
            @click="toggleActivationProductMembership(price.adhesion_obligatoire)">
                <span>adhérez à "{{ getDataAdhesion(price.adhesion_obligatoire).name }}" pour accéder à ce produit</span>
              </button>
          </div>
        </section>

      </div>
    </fieldset>
    /-- produits "A" --
    <fieldset v-if="product.categorie_article === 'A' && getProductIsActivated(product.uuid) === true" class="shadow-sm p-3 mb-5 bg-body rounded test-card-billet">
      <legend>
        <img v-if="image === true" :src="product.img" class="image-product" :alt="product.name" :style="stImage">
        <h3 v-else class="font-weight-bolder text-info text-gradient align-self-start">{{ product.name }}</h3>
        <h6 v-if="product.short_description !== null" class="text-info">{{ product.short_description }}</h6>
      </legend>
    </fieldset>
-->
  </div>
</template>

<script setup>
console.log('-> CardBillet.vue')

// store
import { useSessionStore } from '@/stores/session'

// attributs/props
const emit = defineEmits(['update:products'])
const props = defineProps({
  image: Boolean,
  styleImage: Object,
  products: Object
})

let stImage = ''
// valeurs par défaut
if (props.styleImage === undefined) {
  stImage = {
    height: '20px',
    width: 'auto'
  }
} else {
  stImage = props.styleImage
}
/*
// state
const { getBilletsFromEvent, getDataAdhesion, getProductIsActivated, toggleActivationProductMembership } = useSessionStore()
const { getIsLogin, getUserHasThisMembership } = useLocalStore()
*/
console.log('form =', props.form)
</script>

<style scoped>
</style>