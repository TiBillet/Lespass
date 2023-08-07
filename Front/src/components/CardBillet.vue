<template>
  <div v-for="product in products" :key="product.uuid">
    <!-- produits "F" et "B" -->
    <fieldset v-if="['F','B'].includes(product.categorie_article)"
              class="shadow-sm p-3 mb-5 bg-body rounded test-card-billet">
      <legend>
        <img v-if="image === true" :src="product.img" class="image-product" :alt="product.name" :style="stImage">
        <h3 v-else class="font-weight-bolder text-info text-gradient align-self-start">{{ product.name }}</h3>
        <h6 v-if="product.short_description !== null" class="text-info">{{ product.short_description }}</h6>
      </legend>
      <!-- prix -->
      <div v-for="price in product.prices" :key="price.uuid" class="mt-5">
        <section
            v-if="price.adhesion_obligatoire === null ||  ((getIsMemberShip(price.adhesion_obligatoire) || getRelatedProductIsActivated(price.adhesion_obligatoire) === true )&& getIsLogin)">
          <div class="d-flex justify-content-between">
            <!-- nom tarif -->
            <h4 v-if="price.prix > 0" class="font-weight-bolder text-info text-gradient align-self-start">
              {{ price.name.toLowerCase() }} :
              {{ price.prix }} €</h4>
            <h4 v-else class="font-weight-bolder text-info text-gradient align-self-start">{{
                price.name.toLowerCase()
              }}</h4>
            <button v-if="getBtnAddCustomerCanBeSeen(product.uuid, price.uuid)"
                    class="btn btn-primary ms-3 test-card-billet-bt-add"
                    type="button" @click.stop="addCustomer(product.uuid, price.uuid)">
              <i class="fas fa-plus"></i>
            </button>
          </div>

          <!-- clients -->
          <CardCustomers v-model:customers="price.customers" :price-uuid="price.uuid"/>
        </section>

        <!-- adhesion_obligatoire === true -->
        <section v-else>
          <!-- nom tarif -->
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
              <span>adhérez à "{{
                  getMembershipData(price.adhesion_obligatoire).name
                }}" pour accéder à ce produit</span>
            </button>
          </div>
        </section>
      </div>
    </fieldset>
    <!-- produits "A" -->
    <fieldset v-if="product.categorie_article === 'A' && getRelatedProductIsActivated(product.uuid) === true"
              class="shadow-sm p-3 mb-5 bg-body rounded test-card-billet">
      <legend>
        <img v-if="image === true" :src="product.img" class="image-product" :alt="product.name" :style="stImage">
        <h3 v-else class="font-weight-bolder text-info text-gradient align-self-start">{{ product.name }}</h3>
        <h6 v-if="product.short_description !== null" class="text-info">{{ product.short_description }}</h6>
      </legend>
    </fieldset>
  </div>
</template>

<script setup>
console.log('-> CardBillet.vue')

// store
import { useSessionStore } from '@/stores/session'

// component
import CardCustomers from './CardCustomers.vue'

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

// state
const {
  getIsLogin, getIsMemberShip, getMembershipData, toggleActivationProductMembership, getRelatedProductIsActivated,
  addCustomer, getBtnAddCustomerCanBeSeen
} = useSessionStore()
</script>

<style scoped>
</style>