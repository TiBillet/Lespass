<template>
    <div class="textarea-md-group">
        <label :for="id">{{ label }}</label>
        <textarea :id="id" :cols="cols" :rows="rows" @input="sendInput($event)" @focus="stateFocus($event.target)"
            @blur="stateBlur($event.target)">{{ content }}</textarea>
    </div>
</template>
  
<script setup>
import { ref, onMounted, watch } from "vue";

const props = defineProps({
    id: String,
    content: String,
    label: String,
    cols: {
        type: Number,
        default: 32
    },
    rows: {
        type: Number,
        default: 5
    },
    color: String
});

const emit = defineEmits(["update:content"])
let contentSize = ref(0)


onMounted(() => {
    const id = JSON.parse(JSON.stringify(props)).id
    console.log('id =', id);
    const test = document.querySelector('#' + id).value
    console.log('test =', test);
})

function stateFocus(element) {
    const label = element.parentNode.querySelector("label")
    label.style.top = "-18px"
    label.style.fontSize = "11px"
    label.style.lineHeight = "1.07143"
}

function stateBlur(element) {
    if (element.value.length === 0) {
        const label = element.parentNode.querySelector("label")
        label.style.top = 0
        label.style.fontSize = "14px"
        label.style.lineHeight = 1.42857
        element.style.backgroundSize = "0 2px,100% 1px"
        element.style.borderBottom = "1px solid #1d1c1c"
    }
}

watch(contentSize, (newValue, oldValue) => {
    if (newValue !== oldValue) {
        const textarea = document.querySelector('#' + props.id)
        if (newValue === 0) {
            stateBlur(textarea)
        } else {
            stateFocus(textarea)
        }
    }
})

function sendInput(evt) {
    contentSize.value = evt.target.value.length
    emit("update:content", evt.target.value)
}

</script>
  
<style scoped>
.textarea-md-group {
    position: relative;
    margin: 18px 0;
    padding: 0;
}

.textarea-md-group label {
    position: absolute;
    top: 0;
    left: 0;
    transition: 0.3s ease all;
    margin: 0;
    padding: 0;
}

.textarea-md-group textarea {
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
</style>
  