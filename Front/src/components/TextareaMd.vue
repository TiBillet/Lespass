<template>
    <div class="input-group input-group-dynamic mb-4" :class="validation === true ? 'has-validation' : ''">
        <label class="form-label" :for="id">{{ label }}</label>
        <textarea :id="id" :rows="rowsMd" class="form-control" :value="modelValue" @input="sendInput($event)"
            aria-describedby="basic-addon3" @focusin="focused($event)" @focusout="defocused($event)"
            @keyup="isFilled($event)" :required="validation"></textarea>
        <div class="invalid-feedback" role="heading" :aria-label="msgError">{{ msgError }}</div>
    </div>
</template>
  
<script setup>
import { ref } from "vue";
const props = defineProps({
    id: String,
    modelValue: String,
    label: String,
    msgError: String,
    rows: {
        type: Number,
        default: 3
    },
    validation: Boolean
});

let rowsMd = ref(0)

const emit = defineEmits(["update:modelValue"]);

function sendInput(evt) {
    emit("update:modelValue", evt.target.value);
}

function focused(evt) {
    evt.target.parentNode.classList.add('is-focused')
    rowsMd.value = props.rows
}

function defocused(evt) {
    const input = evt.target
    const parent = input.parentNode
    parent.classList.remove('is-focused')
    if (input.value != "") {
        parent.classList.add('is-filled');
    } else {
        rowsMd.value = 0
    }
}

function isFilled(evt) {
    const input = evt.target
    const parent = input.parentNode
    if (input.value != "") {
        parent.classList.add('is-filled');
    } else {
        parent.classList.remove('is-filled');
        rowsMd.value = 0
    }
}
</script>
  
<style scoped>
</style>
  