<template>
  <div v-if="listToast.length > 0" class="position-relative">
    <div class="position-fixed top-10 end-0 p-3" style="z-index: 11 !important;max-height: 70%;overflow-y: auto;">
      <div v-for="(toast, index) in listToast" :key="index" :id="'toastMessage-' + toast.uuid" class="my-toast"
      role="alert" :aria-label="toast.contenu">
        <div class="toast-header">
          <div :class="'toast-type-size rounded me-2 ' + toast.typeMsg"></div>
          <strong class="me-auto">{{ toast.title }}</strong>
          <button class="btn-close" type="button" @click="deleteToast( toast.uuid)" :aria-label="'Fermer toast message -' + toast.uuid"></button>
        </div>
        <div class="toast-body">
          {{ toast.contenu }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { v4 as uuidv4 } from 'uuid'

let listToast = ref([])

// en attente de suppression
emitter.on('toastSend', (data) => {
  // console.log('-> réception "toastSend", data =', data)
  if (data.typeMsg) {
    if (data.typeMsg === 'warning') {
      data.typeMsg = 'bg-warning text-dark'
    }
    if (data.typeMsg === 'primary') {
      data.typeMsg = 'bg-primary-1 text-white'
    }
    if (data.typeMsg === 'secondary') {
      data.typeMsg = 'bg-secondary text-white'
    }
    if (data.typeMsg === 'success') {
      data.typeMsg = 'bg-success text-white'
    }
    if (data.typeMsg === 'danger') {
      data.typeMsg = 'bg-danger text-white'
    }
  } else {
    data.typeMsg = 'bg-white text-dark'
  }

  data['uuid'] = uuidv4()

  if (data.delay) {
     setTimeout(() => {
      deleteToast(data.uuid);
    }, data.delay);
  }

  listToast.value.push(data)
})

function deleteToast(uuid) {
  listToast.value = listToast.value.filter(toast => toast.uuid !== uuid)
  // console.log('listToast =', listToast.value)
}

</script>

<style scoped>
.my-toast {
  width: 350px;
  max-width: 100%;
  font-size: .875rem;
  pointer-events: auto;
  background-color: rgb(255, 255, 255);
  background-clip: padding-box;
  border: 1px solid rgba(0, 0, 0, .1);
  box-shadow: 0 .3125rem .625rem 0 rgba(0,0,0,.08) !important;
  border-radius: .25rem;
  margin-bottom: 6px;
}
.btn-close {
  box-sizing: content-box;
  width: 1em;
  height: 1em;
  padding: .25em .25em;
  color: #000;
  background: transparent url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='%23000'%3e%3cpath d='M.293.293a1 1 0 011.414 0L8 6.586 14.293.293a1 1 0 111.414 1.414L9.414 8l6.293 6.293a1 1 0 01-1.414 1.414L8 9.414l-6.293 6.293a1 1 0 01-1.414-1.414L6.586 8 .293 1.707a1 1 0 010-1.414z'/%3e%3c/svg%3e") center/1em auto no-repeat;
  border: 0;
  border-radius: .25rem;
  opacity: .5;
}

.toast-header {
  border-bottom: 1px solid rgba(0,0,0,.05) !important;
}

.bg-primary-1 {
  background-color: #2ca8ff !important;
}
.toast-type-size {
  width: 20px;
  height: 20px;
}
</style>