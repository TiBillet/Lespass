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
          <button type=" button
        " class="btn bg-gradient-secondary" data-bs-dismiss="modal">Fermer</button>
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

emitter.on('modalMessage', (data) => {
  message.value = data
  if (message.value.dynamic === null) {
    message.value.dynamic = false
  }

  if (message.value.typeMsg) {
    if (message.value.typeMsg === "warning") {
      message.value.typeMsg = "bg-warning text-dark"
    }
    if (message.value.typeMsg === "primary") {
      message.value.typeMsg = "bg-primary text-white"
    }
    if (message.value.typeMsg === "secondary") {
      message.value.typeMsg = "bg-secondary text-white"
    }
    if (message.value.typeMsg === "success") {
      message.value.typeMsg = "bg-success text-white"
    }
    if (message.value.typeMsg === "danger") {
      message.value.typeMsg = "bg-danger text-white"
    }
  } else {
    message.value.typeMsg = "bg-white text-dark"
  }

  const elementModal = document.querySelector('#conteneur-message-modal')
  const modalMessage = bootstrap.Modal.getOrCreateInstance(elementModal)
  modalMessage.show()
})
</script>

<style scoped>
</style>