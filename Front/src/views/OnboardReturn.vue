<template>
  <ModalOnboardReturn :accStripe="accStripe"/>
</template>

<script setup>
// store
import {storeToRefs} from 'pinia'
import {useAllStore} from '@/stores/all'
import {onMounted, onUnmounted} from 'vue'
import {useRoute} from 'vue-router'
import ModalOnboardReturn from '@/components/ModalOnboardReturn.vue'

const {loading, error} = storeToRefs(useAllStore())
const route = useRoute()

const accStripe = route.params.accstripe

// bloque le scroll
onMounted(() => {
  if (accStripe !== undefined) {
    console.log("On Mounted accStripe : ", accStripe)
    // ferme le modal
    const elementModal = document.querySelector('#modal-onboard-return')
    console.log("  elementModal ", elementModal)
    const modal = new bootstrap.Modal(elementModal) // Returns a Bootstrap modal instance

    modal.show()

  }
})


</script>

<style scoped>

</style>