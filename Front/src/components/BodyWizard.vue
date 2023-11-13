<template>
  <div class="container-fluid vw-100 min-vh-100 d-flex flex-column  align-items-center tibillet-page-tenant"
    :style="`background-image: url('${background}');background-position:50% 50%;background-size:cover`">
    <div class="container mt-7">
      <div class="card creation-card">
        <div class="creation-header">
          <h3 class="creation-title">Créer votre évènement</h3>
        </div>
        currentStep = {{ currentStep.id }} / {{ currentStep.name }}
        <!-- navigation -->
        <div class="creation-navigation position-relative">
          <ul class="nav nav-pills">

            <li v-for="(step, index) in steps" :key="index" class="nav-item-creation tibillet-no-clickable"
              :data-cible="step.name" :data-index="index" :style="`width: ${itemMenuWidth}%;`">
              {{ step.name }}
            </li>
          </ul>
          <!-- bouton mobile -->
          <div class="bt-nav-creation tibillet-bg-primary" :style="styleBtMobile">{{ currentStep.name }}</div>
        </div> <!-- fin navigation -->

        <!-- contenu -->
        <div class="creation-tabs-content ps-3 pe-3">
          <slot></slot>
        </div> <!-- fin du contenu -->

      </div>
    </div>
  </div>
</template>
  
<script setup>
import { inject, ref, onMounted, onBeforeUnmount, watch } from 'vue'

// store
import { useSessionStore } from "../stores/session";
import { setLocalStateKey } from '../communs/storeLocal.js'

const props = defineProps({
  background: {
    default: 'createEvent.jpg',
    type: String
  }
});

const background = new URL('../assets/img/' + props.background, import.meta.url).href
const sessionStore = useSessionStore();
const { updateHeader } = sessionStore;

// injection
const steps = inject('steps')
let currentStep = inject('currentStep')

let itemStepWidth = ref(0);

const itemMenuWidth = (100 / steps.value.length).toFixed(3);
console.log('itemMenuWidth =', itemMenuWidth);

let styleBtMobile = ref({
  width: itemMenuWidth + "%",
  transform: "translate3d(-8px, 0px, 0px)",
  transition: "all 0.5s cubic-bezier(0.29, 1.42, 0.79, 1) 0s"
})



function init() {
  styleBtMobile.width = itemMenuWidth + "%";
}

function updateTitle() {
  console.log('step =', currentStep.value.name);
  const indexTitle = parseInt(document.querySelector(`li[data-cible="${currentStep.value.name}"]`).getAttribute('data-index'))
  const nbItem = steps.value.length
  const menuWidth = document.querySelector('ul[class="nav nav-pills"]').offsetWidth
  const itemMenuWidth = menuWidth / nbItem;
  let decX = 0;
  if (indexTitle === 0) {
    decX = -8;
  }
  if (indexTitle + 1 === nbItem) {
    decX = 8;
  }
  // actualise la position du bouton
  styleBtMobile.value.transform = `translate3d(${decX + indexTitle * itemMenuWidth}px, 0px, 0px)`;
}


// initialise le menu de navigation du composant
onMounted(() => {
  init()
  window.addEventListener('wizardStepChange', updateTitle, false)
  window.addEventListener("resize", updateTitle, false);
});

onBeforeUnmount(() => {
  window.removeEventListener('wizardStepChange', updateTitle, false)
  window.removeEventListener("resize", updateTitle, false);
});

updateHeader(null);

</script>
  
<style scoped>
.creation-card {
  min-height: 410px;
  box-shadow: 0 16px 24px 2px rgba(0, 0, 0, 0.14), 0 6px 30px 5px rgba(0, 0, 0, 0.12), 0 8px 10px -5px rgba(0, 0, 0, 0.2);
}

.creation-card,
.creation-header {
  text-align: center;
  padding: 25px 0 35px 0;
}

.creation-title {
  font-weight: 700;
}

.nav-item-creation {
  border: 0;
  line-height: 18px;
  text-transform: uppercase;
  font-size: 12px;
  font-weight: 500;
  min-width: 100px;
  text-align: center;
  color: #555;
  padding: 12px;
  cursor: pointer;
}

.tibillet-no-clickable {
  -webkit-user-select: none;
  /* Safari, Chrome */
  -khtml-user-select: none;
  /* Konqueror */
  -moz-user-select: none;
  /* Firefox */
  user-select: none;
  /* CSS3 */
  pointer-events: none
}

.bt-nav-creation {
  position: absolute;
  left: 0;
  top: -2px;
  text-align: center;
  padding: 14px 12px;
  font-size: 12px;
  text-transform: uppercase;
  border-radius: 4px;
  color: #ffffff;
  font-weight: bold;
  box-shadow: 0 16px 26px -10px rgba(244, 67, 54, 0.56), 0 4px 25px 0 rgba(0, 0, 0, 0.12), 0 8px 10px -5px rgba(244, 67, 54, 0.2);
  min-width: 140px;
}

.creation-tabs-content {
  --creation-content-height: 530px;
  height: var(--creation-content-height);
  padding: 0 6px;
}
</style>