<template>
  <fieldset class="shadow-sm p-3 mb-5 bg-body rounded test-card-billet"
            v-for="product in event.products.filter(prod => prod.categorie_article === 'F' || prod.categorie_article === 'B')"
            :key="product.uuid">
    <legend>
      <img v-if="image === true" :src="product.img" class="image-product" :alt="product.name" :style="stImage">
      <h3 v-else class="font-weight-bolder text-info text-gradient align-self-start">{{ product.name }}</h3>
      <h6 v-if="product.short_description !== null" class="text-info">{{ product.short_description }}</h6>
    </legend>
    <!-- tous les produits de type billet -->
    <div v-for="price in product.prices" :key="price.uuid" class="mt-5">
      <!-- produit ne nécessitant pas une adhésion ou déjà adhérant -->
      <section v-if="getProductEnable(price.adhesion_obligatoire) === true">
        <!-- prix -->
        <div class="d-flex justify-content-between">
          <!-- nom tarif -->
          <h4 v-if="price.prix > 0" class="font-weight-bolder text-info text-gradient align-self-start">
            {{ price.name.toLowerCase() }} :
            {{ price.prix }} €</h4>
          <h4 v-else class="font-weight-bolder text-info text-gradient align-self-start">{{
              price.name.toLowerCase()
            }}</h4>
          <button
              v-if="stop(price.uuid, price.stock, price.max_per_user) === false"
              class="btn btn-primary ms-3 test-card-billet-bt-add"
              type="button" @click.stop="addCustomer(price.uuid)">
            <i class="fas fa-plus"></i>
          </button>

        </div>
        <!-- clients -->
        <div class="input-group mb-1 test-card-billet-input-group"
             v-for="(customer, index) in getCustomersByUuidPrix(price.uuid)" :key="index">
          <input type="text" :value="customer.last_name" placeholder="Nom" aria-label="Nom"
                 class="form-control test-card-billet-input-group-nom"
                 @keyup="updateCustomer(price.uuid, customer.uuid, $event.target.value,'last_name')" required>
          <input type="text" :value="customer.first_name" placeholder="Prénom" aria-label="Prénom"
                 class="form-control test-card-billet-input-group-prenom"
                 @keyup="updateCustomer(price.uuid, customer.uuid, $event.target.value,'first_name')" required>
          <button class="btn btn-primary mb-0" type="button" @click="deleteCustomer(price.uuid, customer.uuid)"
                  style="border-top-right-radius: 30px; border-bottom-right-radius: 30px;">
            <i class="fas fa-times"></i>
          </button>
          <div class="invalid-feedback">Donnée(s) manquante(s) !</div>
        </div>
      </section>
      <!-- produit nécessitant une adhésion -->
      <section v-if="getProductEnable(price.adhesion_obligatoire) === false">
        <div class="">
          <!-- nom tarif -->
          <h4 class="font-weight-bolder text-dark text-gradient">{{ price.name.toLowerCase() }} :
            {{ price.prix }} €</h4>
          <div class="ms-2 mt-0">
            Produit accessible si adhérant à "<a href="/adhesions" class="text-info">{{getNameAdhesion(price.adhesion_obligatoire)}}</a>" .
          </div>
        </div>
      </section>
    </div>
  </fieldset>
</template>

<script setup>
console.log('-> CardBillet.vue')

// store
import { storeToRefs } from 'pinia'
import { useEventStore } from '@/stores/event'
import { useLocalStore } from '@/stores/local'
import { useAllStore } from '@/stores/all'

// attributs/props
const props = defineProps({
  image: Boolean,
  styleImage: Object,
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
const { event } = storeToRefs(useEventStore())
const { place, getNameAdhesion } = storeToRefs(useAllStore())
// action(s) du state
const { getCustomersByUuidPrix, addCustomer, updateCustomer, deleteCustomer, stop, getProductEnable } = useEventStore()
// action state
const { me } = useLocalStore()

</script>

<style scoped>
</style>