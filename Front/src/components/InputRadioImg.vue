<template>
  <label :for="'input-radio-image-' + uuidComponent" :disabled="disable"
    :style="disable ? '' : 'cursor:pointer;'" role="fake-input-radio" :aria-labelledby="label"
    class="d-flex flex-column">
    <div class="input-radio-image-content" :class="classPlus()">
      <input :id="'input-radio-image-' + uuidComponent" type="radio" :name="name" :value="value" class="input-hidden" @click="sendInput($event)"
        :disabled="disable" :required="validation">
      <font-awesome-icon v-if="icons.length > 0" v-for="(icon, index) in icons" :key="index" :icon="['fas', icon.name]"
        :style="styleIcons(icon.name)" />
      <div v-if="svg !== null" class="w-100 h-100 d-flex flex-column justify-content-center align-items-center">
        <img :src="svg.src" alt="image" :style="`width:${svg.size};height:${svg.size};`" />
      </div>
    </div>
    <h6 class="m-0">{{ label }}</h6>
    <div class="invalid-feedback m-0" role="heading" :aria-label="msgError">{{ msgError }}</div>
  </label>
</template>

<script setup>
import { v4 as uuidv4 } from 'uuid'

const emit = defineEmits(['update:modelValue'])


const props = defineProps({
  positionIcons: Array,
  info: String,
  name: String,
  value: String,
  label: String,
  icons: Array,
  svg: Object,
  disable: Boolean,
  modelValue: String,
  validation: Boolean,
  espaceNumber: Number,
  msgError: String
})

const uuidComponent = uuidv4()

function classPlus() {
  let ctClass = ''
  if (props.disable === true) {
    ctClass = 'espace-disabled'
  }
  if (props.modelValue === props.value) {
    ctClass += ' input-radio-image-active'
  }
  return ctClass
}


function styleIcons(name) {
  const icon = props.icons.find(item => item.name === name)
  return {
    position: "absolute",
    left: icon.left,
    top: icon.top
  }
}

function sendInput(evt) {
  const input = evt.target
  emit("update:modelValue", props.value);

  // activation "visuelle" du "input radio image"
  const radios = document.querySelectorAll(`[name="${props.name}"]`)
  radios.forEach(radio => {
    radio.parentNode.classList.remove('input-radio-image-active')
  })
  input.parentNode.classList.add('input-radio-image-active')
}

</script>

<style scoped>
.input-radio-image-content {
  position: relative;
  text-align: center;
  vertical-align: middle;
  height: 116px;
  width: 116px;
  border-radius: 50%;
  color: #999;
  margin: 0 auto 20px;
  border: 4px solid #ccc;
  transition: all .2s;
  -webkit-transition: all .2s;
}

.input-radio-image-active {
  border-color: var(--app-color-primary) !important;
  color: var(--app-color-primary) !important;
}

.input-radio-image-content:hover {
  border-color: var(--app-color-primary) !important;
  color: var(--app-color-primary) !important;
}

.input-hidden {
  /*
  position: absolute;
  left: -10000px;
  z-index: -1;
  */
  display: none;
}

.espace-disabled {
  opacity: 0.4;
}
</style>