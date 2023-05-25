<template>
  <div class="modal fade" id="conteneur-message-modal" tabindex="-1" role="dialog"
       aria-labelledby="Exemple de message sous forme d'un modal."
       aria-hidden="true">
    <div id="conteneur-message-modal-body" class="modal-dialog modal-dialog-centered"
         :init-scroll-properties="initScrollProperties()"
         role="document">
      <div class="modal-content">
        <div class="modal-header" :class="message.typeMsg">
          <h2 class="modal-title" id="exampleModalLabel">{{ message.titre }}</h2>
        </div>
        <!-- contenu  -->
        <div class="modal-body">
          <span v-if="message.dynamic === true" v-html="message.contenu"></span>
          <span v-else>{{ message.contenu }}</span>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn bg-gradient-secondary modal-footer-bt-fermer" data-bs-dismiss="modal">Fermer</button>
      </div>
    </div>
  </div>
  </div>
</template>

<script setup>
import {ref} from 'vue'

const dataModal = ref({})
const message = ref(false)

function initScrollProperties() {
  if (document.querySelector('#conteneur-message-modal-body') !== null) {
    const elementModalBody = document.querySelector('#conteneur-message-modal-body')
    if (message.value.scrollable === true) {
      elementModalBody.classList.add('modal-dialog-scrollable')
    } else {
      elementModalBody.classList.remove('modal-dialog-scrollable')
    }
    if (message.value.size !== undefined) {
      // xl, lg, sm
      const size = 'modal-' + message.value.size
      elementModalBody.classList.add(size)
    }

  }
  return 'init'
}

// en attente de suppression
emitter.on('modalMessage', (data) => {
  if (data.dynamic === null) {
    data.dynamic = false
  }

  if (data.typeMsg) {
    if (data.typeMsg === "warning") {
      data.typeMsg = "bg-warning text-dark"
    }
    if (data.typeMsg === "primary") {
      data.typeMsg = "bg-primary text-white"
    }
    if (data.typeMsg === "secondary") {
      data.typeMsg = "bg-secondary text-white"
    }
    if (data.typeMsg === "success") {
      data.typeMsg = "bg-success text-white"
    }
    if (data.typeMsg === "danger") {
      data.typeMsg = "bg-danger text-white"
    }
  } else {
    data.typeMsg = "bg-white text-dark"
  }
  message.value = data

  const elementModal = document.querySelector('#conteneur-message-modal')
  const modalMessage = bootstrap.Modal.getOrCreateInstance(elementModal)
  modalMessage.show()
})
</script>

<style scoped>
</style>