<template>
  <div class="input-group mb-2 has-validation">
    <span class="input-group-text" @click="inputFocus('profil-email')">{{ label }}}</span>
    <input v-if="typeField === 'email" :id="id" :value="modelValue" :type="typeField"
           @input="$emit('update:modelValue', $event.target.value)"
           pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$"
           class="form-control" :class="classValue" required>
    <input v-else :id="id" :value="modelValue" :type="typeField"
           @input="$emit('update:modelValue', $event.target.value)"
           class="form-control" :class="classValue" required>
    <div class="invalid-feedback">
      {{ feedback }}
    </div>
  </div>

</template>

<script setup>
defineEmits(['update:modelValue'])

defineProps({
  id: String,
  label: String,
  feedback: String,
  modelValue: String,
  classvalue: String,
  typefield: String
})

function inputFocus (id) {
  document.querySelector(`#${id}`).focus()
}

</script>

<style scoped>

</style>