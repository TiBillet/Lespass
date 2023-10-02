<template>
  <div class="input-md-group" :style="`height:${height}px;`">
    <label :for="id">{{ label }}</label>
    <input :id="id" type="text" :value="modelValue" @input="sendInput($event)" @focus="focus($event)" @blur="blur($event)" :style="`background-image: linear-gradient(${color}, ${color});`" />
  </div>
</template>

<script setup>
const props = defineProps({
  id: String,
  modelValue: String,
  label: String,
  height: Number,
  color: String
});

const emit = defineEmits(["update:modelValue"]);

function sendInput(evt) {
  emit("update:modelValue", evt.target.value);
}

function focus(evt) {
  console.log("-> focus..");
  const input = evt.target;
  const label = input.parentNode.querySelector("label");
  label.style.top = "-18px";
  label.style.fontSize = "11px";
  label.style.lineHeight = "1.07143";
  input.style.backgroundSize = "100% 2px,100% 1px";
  input.style.border = 0;
}

function blur(evt) {
  console.log("-> focus..");
  const input = evt.target;
  if (input.value.length === 0) {
    const label = input.parentNode.querySelector("label");
    label.style.top = 0;
    label.style.fontSize = "14px";
    label.style.lineHeight = 1.42857;
    input.style.backgroundSize = "0 2px,100% 1px";
    input.style.borderBottom = "1px solid #1d1c1c";
  }
}
</script>

<style scoped>
.input-md-group {
  position: relative;
  margin: 18px 0;
  padding: 0;
}

.input-md-group label {
  position: absolute;
  top: 0px;
  left: 0;
  transition: 0.3s ease all;
  margin: 0;
  padding: 0;
}

.input-md-group input {
  position: absolute;
  left: 0;
  border: 0;
  outline: 0;
  border-radius: 0;
  border-bottom: 1px solid #1d1c1c;

  background-size: 0 2px, 100% 1px;
  background-repeat: no-repeat;
  background-position: center bottom, center calc(100% - 1px);
  background-color: transparent;
  transition: background 0.3s ease-out;
  margin: 0;
  padding: 0;
}

.input-md-group input:focus {
  border: 0;
  outline: 0;
}
</style>
