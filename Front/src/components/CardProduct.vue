<template>
  <div class="card card-blog card-plain">

    <div class="position-relative">
      <img v-if="product.img !== null" :src="product.img" alt="img-blur-shadow"
           class="img-fluid shadow border-radius-lg">
      <img v-else src="../assets/img/image_non_disponible.svg" alt="img-blur-shadow"
           class="img-fluid shadow border-radius-lg">
    </div>
    <div class="card-body px-1 pt-3">
      <h5>{{ product.name }}</h5>
      <div v-for="(price, index) in product.prices" :key="index" class="ext-xs font-weight-bold mb-0">
        {{ price.name }} - {{ price.prix }}
      </div>
      <button type="button" class="btn btn-outline-primary btn-sm" @click="acheter(uuidEvent, product.uuid)">Acheter
      </button>
    </div>

  </div>
</template>

<script setup>
console.log('-> CardProduct.vue')
import { useStore } from 'vuex'
import { useRouter } from 'vue-router'

// attributs/props
const props = defineProps({
  product: Object,
  uuidEvent: String
})

const router = useRouter()
const store = useStore()

// const product = props.event.products.find(prod => prod.uuid === props.uuidProduct)

// obtenir le contexte
// const ctx = getCurrentInstance().appContext.config.globalProperties

function acheter(uuidEvent, productUuid) {
  console.log('acheter uuidEvent =', uuidEvent, ' --  productUuid =', productUuid)

  // initialisation du formulaire d'achat (reste en mémoire tant que le cache n'est pas effacé !
  if (store.state.formulaire[uuidEvent] === undefined) {
    store.commit('initFormulaire', uuidEvent)
  }

  router.push({name: 'Buy', params: {uuidEvent: uuidEvent, productUuid: productUuid}})
}
</script>

<style>

</style>