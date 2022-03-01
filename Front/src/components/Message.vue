<template>
  <div v-if="messages.length > 0" id="conteneur-message">
    <div :id="`message-${ msg.id }`" v-for="msg in messages" :key="msg.id" v-bind="initEffacerMessage(msg.id, msg.tmp)"
         :class="`alert alert-${ msg.typeMsg} alert-dismissible fade show mt-2`" role="alert">
      <span class="alert-text text-white fw-bold text-wrap">{{ msg.contenu }}</span>
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close">
        <span aria-hidden="true">&times;</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import {ref, onUnmounted} from 'vue'

let messages = ref([])
let repMessages = []
let indexMessage = 0

emitter.on('message', (data) => {
  indexMessage++
  data.id = indexMessage
  messages.value.push(data)
})


// si messages existent, les effacer
onUnmounted(() => {
  for (let i = 0; i < repMessages.length; i++) {
    const message = repMessages[i]
    window.clearTimeout(repMessages[message.id])
  }
})

function effacerMessage(id) {
  window.clearTimeout(repMessages[id])
  // enlève le message éffacer du tabbleau contenant les messages
  messages.value = messages.value.filter(msg => msg.id !== id)
}

function initEffacerMessage(id, tmp) {
  repMessages[id] = window.setTimeout(effacerMessage, tmp * 1000, id)
}
</script>

<style>
#conteneur-message {
  position: fixed;
  left: 0;
  top: 72px;
  width: 100%;
  z-index: 1000;
}
</style>