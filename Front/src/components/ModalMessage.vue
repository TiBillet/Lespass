<template>
  <div class="modal fade" id="conteneur-message-modal" tabindex="-1" role="dialog"
       aria-labelledby="Exemple de message sous forme d'un modal."
       aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered" role="document">
      <div class="modal-content">
        <div class="modal-header">
          <h2 class="modal-title" id="exampleModalLabel">{{ dataModal.titre }}</h2>
          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close">
            <span aria-hidden="true">&times;</span>
          </button>
        </div>
        <!-- que du texte ou numérique -->
        <div v-if="dynamic === false" class="modal-body">
          {{ dataModal.contenu }}
        </div>
        <!-- contenu html provenant d'un string -->
        <div v-else class="modal-body">
          <span v-html="dataModal.contenu"></span>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn bg-gradient-secondary" data-bs-dismiss="modal">Close</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import {ref, onMounted} from 'vue'

const dataModal = ref({})
const dynamic = ref(false)

emitter.on('modalMessage', (data) => {
  console.log('-> Ecoute modalMessage, data =', JSON.stringify(data, null, 2))
  dataModal.value = {
    titre: data.titre,
    contenu: data.contenu
  }
  if (data.dynamique === true) {
    dynamic.value = true
  } else {
    dynamic.value = false
  }
  const elementModal = document.querySelector('#conteneur-message-modal')
  const modalMessage = bootstrap.Modal.getOrCreateInstance(elementModal)
  modalMessage.show()
})

</script>

<style scoped>
</style>