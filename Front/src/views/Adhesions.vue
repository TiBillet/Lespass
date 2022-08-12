<template>
  <section class="pt-7 pb-5">
    <div class="container">
      <div class="row justify-space-between py-2" v-for="(product, index) in getListAdhesions()" :key="index">
        <div class="card card-plain card-blog mt-5">
          <div class="row">
            <div class="col-md-4">
              <div class="card-image position-relative border-radius-lg">
                <img class="img border-radius-lg" :src="product.img" alt="image product" loading="lazy">
              </div>
            </div>
            <div class="col-md-7 my-auto ms-md-3 mt-md-auto mt-4">
              <h3>{{ product.name }}
              </h3>
              <p>
                {{ product.short_description }}
              </p>
              <p>
                {{ product.long_description }}
              </p>

              <button class="btn btn-outline-secondary btn-sm" @click="showFormAdhesion(product.uuid)">Adhérez</button>

            </div>
          </div>
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
const {iamMembershipOwned} = useLocalStore()

let selectedProductUuid = ref('')

function showFormAdhesion(productUuid) {
  console.log('-> fonc showFormAdhesion, productUuid =', productUuid)

  if (iamMembershipOwned(productUuid) === false) {
    // update selected product uuid
    selectedProductUuid.value = productUuid

    // afficher modal formulaire adhésion
    const elementModal = document.querySelector('#modal-form-adhesion')
    const modal = new bootstrap.Modal(elementModal) // Returns a Bootstrap modal instance
    modal.show()
  } else {
    emitter.emit('modalMessage', {
      titre: 'Adhésion à jour',
      contenu: 'Vous êtes à jour de cette cotisation. Vous pouvez aller vérifier votre prochaine échéance dans votre compte'
    })
  }
}

</script>

<style scoped>

</style>