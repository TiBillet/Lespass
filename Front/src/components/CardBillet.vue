<template>
  <div v-for="(product, index) in products" :key="index">
    <!-- produits "F" et "B" -->
    <fieldset v-if="['F','B'].includes(product.categorie_article)"
              class="shadow-sm p-3 mb-5 bg-body rounded test-card-billet">
      <legend>
        <img v-if="image === true" :src="product.img" class="image-product" :alt="product.name" :style="stImage">
        <h3 v-else class="font-weight-bolder text-info text-gradient align-self-start"
            role="heading" :aria-label="`Carte ${index} : ${product.name}`">
          {{ product.name }}
        </h3>
        <h6 v-if="product.short_description !== null" class="text-info">{{ product.short_description }}</h6>
      </legend>
      <!-- prix -->
      <div v-for="(price, index) in product.prices" :key="index" class="mt-5">
        <section v-if="priceCanBeDisplayed(price.adhesion_obligatoire)">
          <div class="d-flex flex-row justify-content-between align-items-center" role="group" :aria-label="'groupe interaction tarif ' + price.name">
            <!-- nom tarif -->
            <h4 class="d-flex flex-row align-items-center mb-0 font-weight-bolder text-info text-gradient"
                role="heading" :aria-label="price.name">
              {{ price.prix > 0 ? `${price.name.toLowerCase()} : ${price.prix} €` : `${price.name.toLowerCase()}` }}
            </h4>
            <!-- ajouter une réservation nominative -->
            <button v-if="getBtnAddCustomerCanBeSeen(product.uuid, price.uuid) && product.nominative === true"
                    class="btn btn-primary mb-0 test-card-billet-bt-add"
                    type="button" @click.stop="addCustomer(product.uuid, price.uuid)"
                    role="button" :aria-label="'Ajouter une réservation - ' + price.name">
              <i class="fa fa-plus" aria-hidden="true"></i>
              <span class="ms-1">Ajouter une réservation</span>
            </button>
            <!-- ajouter une réservation non nominative -->
            <InputNumber v-if="product.nominative === false" v-model:price="product.prices[index]" :info-aria:="'nombre de produit du tarif ' + price.name" min="0" :max="product.prices[index].max_per_user"/>
          </div>

          <!-- clients / customers -->
          <!-- TODO:  un seule attribut, price. -->
          <CardCustomers v-if="product.nominative === true" v-model:customers="price.customers" :price="price"/>

        </section>

        <!-- adhesion_obligatoire === true -->
        <section v-else>
          <div class="d-flex flex-row justify-content-between align-items-center" role="group" :aria-label="'groupe interaction tarif, ' + price.name">
            <!-- nom tarif -->
            <h4 class="font-weight-bolder text-dark text-gradient" role="heading" :aria-label="price.name">
              {{ price.name.toLowerCase() }} : {{ price.prix }} €
            </h4>
            <div v-if="getIsLogin === true">
              <button class="btn btn-primary mb-0" type="button"
                      style="border-top-right-radius: 30px; border-bottom-right-radius: 30px;"
                      @click="activationProductMembership(price)" role="button"
                      :aria-label="`ajouter '${getMembershipData(price.adhesion_obligatoire).name}' pour ce produit`">
                <i class="fa fa-plus" aria-hidden="true"></i>
                <span class="ms-1">
                ajouter "{{ getMembershipData(price.adhesion_obligatoire).name }}" pour  ce produit
              </span>
              </button>
            </div>
          </div>
          <div v-if="getIsLogin === false" class="mt-0 text-info font-weight-500"
               role="heading" aria-label="Vous devez être connecter pour accéder à ce produit.">
            Vous devez être connecter pour accéder à ce produit.
          </div>
        </section>
      </div>
    </fieldset>

    <!-- produits "A" -->
    <CardMembership v-if="membershipCanBeDisplayed(product)" v-model:product="products[index]"/>
  </div>
</template>

<script setup>
console.log('-> CardBillet.vue')

// store
import { useSessionStore } from '@/stores/session'

// component
import CardCustomers from './CardCustomers.vue'
import CardMembership from './CardMembership.vue'
import InputNumber from './InputNumber.vue'


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
  getIsLogin, getIsMemberShip, getMembershipData, activationProductMembership, getRelatedProductIsActivated,
  addCustomer, getBtnAddCustomerCanBeSeen
} = useSessionStore()

function priceCanBeDisplayed (adhesionObligatoire) {
  if (adhesionObligatoire === null) {
    return true
  }
  if (adhesionObligatoire !== null && getIsLogin === true && getIsMemberShip(adhesionObligatoire) === true) {
    return true
  }

  if (adhesionObligatoire !== null && getIsLogin === true && getRelatedProductIsActivated(adhesionObligatoire) === true) {
    return true
  }
  return false
}

function membershipCanBeDisplayed (product) {
  if (product.categorie_article === 'A' && getIsLogin === true && getRelatedProductIsActivated(product.uuid) === true && getIsMemberShip(product.uuid) === false) {
    return true
  }
  return false
}
</script>

<style scoped>
</style>