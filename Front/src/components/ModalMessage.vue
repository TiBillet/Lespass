<template>
  <div class="modal fade" id="conteneur-message-modal" tabindex="-1" role="dialog"
       aria-labelledby="Exemple de message sous forme d'un modal."
       aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered" role="document">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title" id="exampleModalLabel">{{ dataModal.titre }}</h5>
          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close">
            <span aria-hidden="true">&times;</span>
          </button>
        </div>
        <div class="modal-body">
          {{ dataModal.contenu }}
        </div>
        <div class="modal-footer">
          <button type="button" class="btn bg-gradient-secondary" data-bs-dismiss="modal">Close</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import {ref} from 'vue'

const dataModal = ref({})

emitter.on('modalMessage', (data) => {
  console.log('-> Ecoute modalMessage, data =', JSON.stringify(data, null, 2))
  dataModal.value = {
    titre: data.titre,
    contenu: data.contenu
  }
  const elementModal = document.querySelector('#conteneur-message-modal')
  const modalMessage = bootstrap.Modal.getOrCreateInstance(elementModal)
  modalMessage.show()
})


</script>

<style scoped>

</style>