<template>
  <div :id="`tibillet-parent-radio-${uuidComponent}`" class="input-group mb-2 has-validation">
    <div class="d-flex flex-row justify-content-start align-items-start mb-2 me-2"
      v-for="(option, index) in dataRadio.options" :key="index">
      <input v-if="index === 0" :name="dataRadio.name" :id="getUuid(index)" type="radio" @click="updateInputRadio($event)"
        :value="option.value" required role="radio" :aria-labelledby="msgRole + index" :checked="option.value" />
      <input v-else :name="dataRadio.name" :id="getUuid(index)" type="radio" @click="updateInputRadio($event)"
        :value="option.value" role="radio" :aria-labelledby="msgRole + index" :checked="option.value" />
      <div class="tibillet-custum-radio" :data-uuid="option.value" @click="clickInput($event)"></div>
      <label class="flex flex-column flex-wrap text-dark mb-0" style="width: 118px;" :for="getUuid(index)">{{ option.label
      }}</label>
      <div v-if="index === 0" class="invalid-feedback w-100" role="heading" :aria-label="msgError">{{ msgError }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { v4 as uuidv4 } from 'uuid'
import { onMounted, onUpdated } from 'vue';

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
  validation: String
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
  width: 60%;
  height: 60%;
  background-color: var(--tibillet-input-radio, transparent);
  cursor: pointer;
  margin: 0;
  padding: 0;
}
</style>