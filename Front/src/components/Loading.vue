<template>
  <div id="spinner-contener" class="position-absolute au-dessus bg-dark transparent">
    <div id="spinner-content" class="position-relative">
      <!--  <div class="position-absolute d-flex justify-content-center align-items-center vw-100 vh-100"> -->
      <div id="spinner-element" class="spinner-border text-info" role="status" :style="styleObject"></div>
      <!-- </div> -->
    </div>
  </div>

</template>

<script setup>
// vue
import {onMounted, ref} from 'vue'

const styleObject = ref({
  width: '20rem',
  height: '20rem',
  borderWidth: '0.5em',
  position: 'fixed',
  top: 0,
  left: 0
})

// update spinner position on show
onMounted(() => {
  const element = document.querySelector('#app')
  const height = element.clientHeight + 'px'
  const width = element.clientWidth + 'px'
  const elementCible = document.querySelector('#spinner-contener')
  const elementCible2 = document.querySelector('#spinner-content')
  elementCible.style.height = height
  elementCible.style.width = width
  elementCible2.style.height = height
  elementCible2.style.width = width
  const size = document.querySelector('#spinner-element').clientWidth
  const py = ((window.innerHeight || document.documentElement.clientHeight) / 2) - (size / 2)
  const px = (element.clientWidth / 2) - (size / 2)
  styleObject.value.left = px + 'px'
  styleObject.value.top = py + 'px'
})
</script> getHeight()

<style scoped>
.au-dessus {
  z-index: 99;
}

.transparent {
  background-color: #cc33ff;
  opacity: 0.4;
}
</style>