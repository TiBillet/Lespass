<template>

  <fieldset class="shadow-sm p-3 mb-5 bg-body rounded"
            v-for="product in event.products.filter(prod => prod.categorie_article === 'F' || prod.categorie_article === 'B')"
            :key="product.uuid">
    <legend>
      <img v-if="image === true" :src="product.img" class="image-product" alt="Image du billet !" :style="stImage">
      <h3 v-else class="font-weight-bolder text-info text-gradient align-self-start">{{ product.name }}</h3>
    </legend>
    <div v-for="price in product.prices" :key="price.uuid" class="mt-5">
      <!-- prix -->
      <div class="d-flex justify-content-between">
        <!-- nom tarif -->
        <h4 class="font-weight-bolder text-info text-gradient align-self-start">{{ price.name.toLowerCase() }} :
          {{ price.prix }} €</h4>
        <button
            v-if="stop(price.uuid, price.stock, price.max_per_user) === false"
            class="btn btn-primary ms-3" type="button"
            @click.stop="addCustomer(price.uuid)">
          <i class="fas fa-plus"></i>
        </button>
      </div>
      <!-- clients -->

      <div class="input-group mb-1"
           v-for="(customer, index) in getCustomersByUuidPrix(price.uuid)" :key="index">
        <input type="text" :value="customer.last_name" placeholder="Nom" aria-label="Nom" class="form-control"
               @keyup="updateCustomer(price.uuid, customer.uuid, $event.target.value,'last_name')" required>
        <input type="text" :value="customer.first_name" placeholder="Prénom" aria-label="Prénom" class="form-control"
               @keyup="updateCustomer(price.uuid, customer.uuid, $event.target.value,'first_name')" required>
        <button class="btn btn-primary mb-0" type="button" @click="deleteCustomer(price.uuid, customer.uuid)"
                style="border-top-right-radius: 30px; border-bottom-right-radius: 30px;">
          <i class="fas fa-times"></i>
        </button>
        <div class="invalid-feedback">Donnée(s) manquante(s) !</div>
      </div>
    </div>
  </fieldset>


  <!--
    <div v-if="price.users.length > 0 " class="d-flex justify-content-end mb-3">
      <h6>
        SOUS-TOTAL : {{ (price.users.length * price.prix) }}€
      </h6>
    </div>
  -->
</template>

<script setup>
// console.log('-> CardBillet.vue')

// store
import {storeToRefs} from 'pinia'
import {useEventStore} from '@/stores/event'

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

// state event
const {event} = storeToRefs(useEventStore())
// action(s) du state event
const {getCustomersByUuidPrix, addCustomer, updateCustomer, deleteCustomer, stop} = useEventStore()
</script>

<style scoped>
</style>