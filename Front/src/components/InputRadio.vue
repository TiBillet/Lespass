<template>
  <div :id="`tibillet-parent-radio-${uuidComponent}`" class="input-group mb-2  has-validations">
    <div class="d-flex flex-row justify-content-start align-items-start mb-2 me-2"
      v-for="(option, index) in dataRadio.options" :key="index" style="position:relative">
      <div class="tibillet-custum-radio" :data-uuid="option.value" @click="clickInput($event)" role="fake-radio" :aria-labelledby="msgRole + ' - ' + index"></div>
      <label class="flex flex-column flex-wrap text-dark mb-0" style="width: 118px;" :for="getUuid(index)">
        {{ option.label }}
      </label>
      <input :name="dataRadio.name" :id="getUuid(index)" type="radio"
        @click="updateInputRadio($event)" :value="option.value"
        :checked="option.value === modelValue" :required="validation === true"/>
      <div v-if="index === 0 && validation === true" class="tibillet-msg-error-position invalid-feedback w-100" role="heading" :aria-label="msgError">{{ msgError }}</div>
    </div>
  </div>
</template>

<script setup>
import { v4 as uuidv4 } from 'uuid'
import { onMounted, onUpdated } from 'vue';

// dataRadio = [{label: string, value: string}, ...]
const props = defineProps({
  modelValue: String,
  msgRole: {
    default: 'Pas de aria-labelledby défini - ',
    type: String
  },
  msgError: {
    default: "Pas de message d'erreur.",
    type: String
  },
  dataRadio: Object,
  validation: Boolean
});
const emit = defineEmits(["update:modelValue"]);
const uuidComponent = uuidv4()
let uuid = { value: uuidv4(), index: -1 }

function getUuid(index) {
  if (uuid.index !== index) {
    uuid = { value: 'radio-' + uuidv4(), index }
  }
  return uuid.value
}

function updateVisual() {
  document.querySelectorAll(`#tibillet-parent-radio-${uuidComponent} .tibillet-custum-radio`).forEach(ele => {
    const eleUuid = ele.getAttribute('data-uuid')
    if (eleUuid === props.modelValue) {
      ele.style.setProperty("--tibillet-input-radio", "#198754")
    } else {
      ele.style.setProperty("--tibillet-input-radio", "transparent")
    }
  })
}

function clickInput(evt) {
  const input = evt.target.parentNode.querySelector('input')
  input.click()
  updateVisual()
}

// update value
function updateInputRadio(evt) {
  emit("update:modelValue", evt.target.value);
  const name = evt.target.getAttribute('name')
}


function radioIsValid() {
  // tibillet-parent-radio-${uuidComponent
  // document.querySelector('input[name="rate"]:checked').value;
  const name = document.querySelector(`#tibillet-parent-radio-${uuidComponent} input`).getAttribute('name')
  const value = document.querySelector(`input[name="${name}"]:checked`).value;
  console.log('name =', name, '  --  value=', value);
}

onMounted(updateVisual)
onUpdated(updateVisual)

</script>

<style scoped>
input[type="radio"] {
  display: none;
}

.tibillet-custum-radio {
  display: flex;
  flex-direction: row;
  justify-content: space-around;
  align-items: center;
  min-width: 18px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1px solid var(--bs-gray);
  margin: 0;
  padding: 0;
}

.tibillet-custum-radio::after {
  content: '';
  display: flex;
  border-radius: 50%;
  width: 58%;
  height: 60%;
  background-color: var(--tibillet-input-radio, transparent);
  cursor: pointer;
  margin: 0;
  padding: 0;
}

.tibillet-msg-error-position {
  position: absolute;
  left: 0;
  bottom: -18px;
}
</style>