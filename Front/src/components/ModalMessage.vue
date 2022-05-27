<template>
  <div class="modal fade" id="conteneur-message-modal" tabindex="-1" role="dialog"
       aria-labelledby="Exemple de message sous forme d'un modal."
       aria-hidden="true">
    <div id="conteneur-message-modal-body" class="modal-dialog modal-dialog-centered" :init-scroll="isScrollable()"
         role="document">
      <div class="modal-content">
        <div class="modal-header">
          <h2 class="modal-title" id="exampleModalLabel">{{ message.titre }}</h2>
          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close">
            <span aria-hidden="true">&times;</span>
          </button>
        </div>
        <!-- contenu  -->
        <div class="modal-body">
          <span v-if="message.dynamic === true" v-html="message.contenu"></span>
          <span v-else>{{ message.contenu }}</span>
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
const message = ref(false)

function isScrollable() {
  if (document.querySelector('#conteneur-message-modal-body') !== null) {
    const elementModalBody = document.querySelector('#conteneur-message-modal-body')
    if (message.value.scrollable === true) {
      elementModalBody.classList.add('modal-dialog-scrollable')
      return true
    } else {
      elementModalBody.classList.remove('modal-dialog-scrollable')
      return false
    }
  }
}

emitter.on('modalMessage', (data) => {
  message.value = data
  /*
  // console.log('-> Ecoute modalMessage, data =', JSON.stringify(data, null, 2))
  dataModal.value = {
    titre: data.titre,
    contenu: data.contenu
  }
  dynamic.value = false
  if (data.dynamic === true) {
    dynamic.value = true
  }
  // modal-dialog-scrollable

  const elementModalBody =document.querySelector('#conteneur-message-modal-body')
  if (data.scrollable === true) {
    elementModalBody.classList.add('modal-dialog-scrollable')
  } else {
    elementModalBody.classList.remove('modal-dialog-scrollable')
  }
*/
  const elementModal = document.querySelector('#conteneur-message-modal')
  const modalMessage = bootstrap.Modal.getOrCreateInstance(elementModal)
  modalMessage.show()
})
</script>

<style scoped>
</style>