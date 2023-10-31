<template>
  <input class="form-check-input" type="checkbox" :id="`tibillet-switch-${uuid}`" :true-value="trueValue"
    :false-value="falseValue" role="checkbox" :aria-label="msgRole" @click="updateInputRadio($event)">
  <label class="form-check-label text-dark ms-0" :for="`tibillet-switch-${uuid}`">
    {{ label }}
  </label>
</template>

<script setup>
import { v4 as uuidv4 } from 'uuid'

const props = defineProps({
  modelValue: Boolean,
  msgRole: {
    default: 'Pas de aria-label défini - ',
    type: String
  },
  label: String,
  trueValue: Boolean,
  falseValue: Boolean
});
const emit = defineEmits(["update:modelValue"]);
const uuid = uuidv4()

// update value
function updateInputRadio(evt) {
  const input = evt.target 
  if (input.checked === true) {
    input.classList.add('bg-success')
  } else {
    input.classList.remove('bg-success')
  }
  emit("update:modelValue", evt.target.checked);
}
</script>

<style scoped></style>