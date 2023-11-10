<template>
  <div class="input-group input-group-dynamic mb-4" :class="classPlus()">
    <label class="form-label" :for="id">{{ label }}</label>
    <input :type="type" class="form-control tibillet-input-md" :id="id" aria-describedby="basic-addon3" :value="modelValue"
      @input="sendInput($event)" @focusin="focused($event)" @focusout="defocused($event)" role="textbox"
      :aria-label="msgRole" @keyup="isFilled($event)" :required="validation">
    <div class="invalid-feedback" role="heading" :aria-label="msgError">{{ msgError }}</div>
  </div>
</template>

<script setup>
import { onUpdated } from "vue"

const props = defineProps({
  id: String,
  modelValue: String,
  label: String,
  msgRole: String,
  msgError: String,
  type: {
    default: 'text',
    type: String
  },
  validation: Boolean
});

const emit = defineEmits(["update:modelValue"]);


function classPlus() {
  let ctClass = ''
  if (props.validation === true) {
    ctClass = 'has-validation'
  }
  if (props.modelValue !== '') {
    ctClass += ' is-filled'
  }
  return ctClass
}

function sendInput(evt) {
  emit("update:modelValue", evt.target.value);
}

function focused(evt) {
  evt.target.parentNode.classList.add('is-focused')
}

function defocused(evt) {
  const input = evt.target
  const parent = input.parentNode
  parent.classList.remove('is-focused')
  if (input.value != "") {
    parent.classList.add('is-filled');
  }
}

function isFilled(evt) {
  const input = evt.target
  const parent = input.parentNode
  if (input.value != "") {
    parent.classList.add('is-filled');
  } else {
    parent.classList.remove('is-filled');
  }
}

onUpdated(() => {
  const input = document.querySelector('#' + props.id)
  const parent = input.parentNode
  if (input.value != "") {
    parent.classList.add('is-filled');
  } else {
    parent.classList.remove('is-filled');
  }
})
</script>

<style>
/* css de material-kit 2 et bootstrap 5.3.2 */
.tibillet-input-md {
  margin-left: 0 !important;
  padding-left: 2px !important;
}
</style>
