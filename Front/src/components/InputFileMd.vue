<template>
  <div class="input-group input-group-dynamic mb-4" :class="validation === true ? 'has-validation' : ''">
    <label class="form-label" :for="id">{{ label }}</label>
    <input type="file" class="form-control" :id="id" @change="sendInput($event)" @focusout="defocused($event)"
      :required="validation">

    <div class="invalid-feedback" role="heading" :aria-label="msgError">{{ msgError }}</div>
  </div>
</template>
  
<script setup>

const props = defineProps({
  id: String,
  modelValue: Object,
  label: String,
  msgError: String,
  type: {
    default: 'text',
    type: String
  },
  color: {
    default: '#495057',
    type: String
  },
  validation: Boolean
});

const emit = defineEmits(["update:modelValue"]);

function sendInput(evt) {
  const input = evt.target
  emit("update:modelValue", input.files[0]);
  input.parentNode.classList.add('is-focused')
  input.style.color = props.color
}

function defocused(evt) {
  const input = evt.target
  const parent = input.parentNode
  parent.classList.remove('is-focused')
  parent.classList.add('is-filled');
}
</script>

<style scoped>
input[type=file] {
  color: transparent;
}

input[type=file]::file-selector-button {
  display: none;
}
</style>  