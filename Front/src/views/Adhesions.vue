<template>
  <section class="pt-7 pb-5">
    <div class="container">
      <div class="" row>
        <h2 class="font-weight-bolder text-info text-gradient align-self-start w-85">Adhésions</h2>
      </div>

      <div class="card-body d-flex justify-content-around">

        <!-- liste -->
        <div class="col-sm-6 col-lg-4 mt-lg-0 mt-4" v-for="(product, index) in getListAdhesions()" :key="index">
          <img class="width-48-px mb-3" :src="product.img" alt="image product" loading="lazy">
          <h5>{{ product.name }}</h5>
          <p class="text-sm">{{ product.long_description }}</p>
          <button class="btn btn-outline-secondary btn-sm" @click="showFormAdhesion(product.uuid)">Adhérez
          </button>
        </div>

      </div>
    </div>
    <ModalMembershipForm :product-uuid="selectedProductUuid"/>
  </section>
</template>

<script setup>
// vue
import {ref} from 'vue'

// components
import ModalMembershipForm from '@/components/ModalMembershipForm.vue'

// store
import {useAllStore} from '@/stores/all'
import {useLocalStore} from '@/stores/local'

// obtenir data adhesion
const {getListAdhesions, getHeaderPlace} = useAllStore()
// const {me} = storeToRefs(useLocalStore())

let selectedProductUuid = ref('')

function showFormAdhesion(productUuid) {
  // update selcetd product uuid
  selectedProductUuid.value = productUuid

  // afficher modal formulaire adhésion
  const elementModal = document.querySelector('#modal-form-adhesion')
  const modal = new bootstrap.Modal(elementModal) // Returns a Bootstrap modal instance
  modal.show()
}

</script>

<style scoped>

</style>