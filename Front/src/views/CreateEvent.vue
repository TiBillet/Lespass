<template>
  <BodyWizard background="wizard-profile.jpg">
    <!-- nom et date -->
    <div v-if="['event'].includes(currentStep.id)" class="creation-tab-content">
      <div class="espace-content d-flex flex-column">
        <input type="datetime">

        <InputMd id="nom-evenement" label="Intitulé" msg-error="Renseigner le nom de l'évènement." :validation="true"
          v-model="stateForm.name" class="mt-3" msg-role="nom de l'évènement" />

      </div>
      <!-- footer -->
      <div class="d-flex flex-row-reverse w-100 creation-footer">
        <button type="button" @click="service.send('evtValidateEvent')" class="btn btn-creation tibillet-bg-primary"
          role="button" aria-label="go-informations">
          Suivant
        </button>
      </div>
    </div>

    <!-- informations -->
    <div v-if="['informations'].includes(currentStep.id)" class="creation-tab-content">
      <div class="espace-content d-flex flex-column">
        <InputMd id="creation-short-description" label="Courte description" v-model="stateForm.short_description"
          msg-error="Renseigner la courte description" msg-role="courte description" :validation="true" />

        <TextareaMd id="creation-long-description" label="Votre longue description"
          v-model="stateForm.long_description" />

        <InputFileMd type="file" id="creation-img" label="Url image" v-model="stateForm.img" class="mt-2"
          msg-error="Sélectionner une image." msg-role="Sélectionner une image" :validation="true" />

      </div>
      <!-- footer -->
      <div class="creation-footer d-flex justify-content-between">
        <button class="btn btn-creation btn-previous" @click="service.send('evtReturnEvent')">
          Précédent
        </button>
        <button class="btn btn-creation tibillet-bg-primary" role="button" aria-label="go-prices"
          @click.prevent="service.send('evtValidateInformations')">
          Suivant
        </button>
      </div>
    </div>

    <!-- tarifs -->
    <div v-if="['prices'].includes(currentStep.id)" class="creation-tab-content">
      <div class="espace-content d-flex flex-column">
        <h1>Tarifs</h1>
      </div>
      <!-- footer -->
      <div class="creation-footer d-flex justify-content-between">
              <button class="btn btn-creation btn-previous" @click="service.send('evtReturnInformations')">
                Précédent
              </button>
              <button class="btn btn-creation tibillet-bg-primary" role="button" aria-label="go-resume"
                @click="createEvent()">
                Validation
              </button>
            </div>
    </div>

  </BodyWizard>
</template>

<script setup>
import { provide, ref } from 'vue'

import { emitEvent } from '../communs/EmitEvent.js'
// store
import { useSessionStore } from "../stores/session";
import { setLocalStateKey } from '../communs/storeLocal.js'

// composants
import BodyWizard from "../components/BodyWizard.vue";
import InputMd from "../components/InputMd.vue";
import TextareaMd from "../components/TextareaMd.vue";
import InputFileMd from "../components/InputFileMd.vue";

// machine
import { createMachine, interpret } from 'robot3';
import { machineCreateEvent } from "../machines/machineCreateEvent.js"

const sessionStore = useSessionStore();
const { updateHeader, setLoadingValue } = sessionStore;

// les données du wizard
let stateForm = {
  dateEvenement: null,
  name: "",
  short_description: "",
  long_description: "",
  img: null,
  stripe: true,
  prices: []
}

const contextMachine = () => (stateForm);

const steps = ref([
  { id: 'event', name: 'évènement' },
  { id: 'informations', name: 'informations' },
  { id: 'prices', name: 'tarifs' }
])
provide('steps', steps)

let currentStep = ref(steps.value[0])
provide('currentStep', currentStep)


const machine = createMachine(machineCreateEvent, contextMachine)
const service = interpret(machine, () => {
  const ctx = service.machine.context()
  currentStep.value = steps.value.find(step => step.id === service.machine.current)
  emitEvent('wizardStepChange', {})
  // console.log('-> Etape :', etape.value);
  // console.log('-> ctx :', ctx);
});

function createEvent() {
console.log('-> createEvent, stateForm =', stateForm);
}
</script>

<style scoped>
.creation-tab-content {
  --creation-content-height: 530px;
  width: 100%;
  height: var(--creation-content-height);
  margin: 0;
  padding: 0;
}

.espace-content {
  width: 100%;
  height: calc(var(--creation-content-height) - 10%);
  overflow-x: hidden;
  overflow-y: scroll;
  padding: 0 0 6px 0;
}

.creation-footer {
  width: 100%;
  height: calc(var(--creation-content-height) - 90%);
}

.btn-creation {
  font-size: 12px;
  text-transform: uppercase;
  border-radius: 4px;
  color: #ffffff;
  cursor: pointer;
  font-weight: bold;
  box-shadow: 0 16px 26px -10px rgba(244, 67, 54, 0.56), 0 4px 25px 0 rgba(0, 0, 0, 0.12), 0 8px 10px -5px rgba(244, 67, 54, 0.2);
  min-width: 140px;
}

.btn-previous {
  background-color: #999;
  color: #fff;
}
</style>