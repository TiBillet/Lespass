<template>
  <div class="container-fluid vw-100 vh-100 d-flex justify-content-center align-items-center"
       :style="`background-image: url('${wizardBackground}');background-repeat:no-repeat;background-size:100% 100%;`">
    <div class="container">
      <div class="card wizard-card" data-color="red">
        <form action="" method="">
          <div class="wizard-header">
            <h3 class="wizard-title">{{ title }}</h3>
            <h5>
              <slot name="subtitle"></slot>
            </h5>
          </div>
          <!-- navigation -->
          <div class="wizard-navigation">
            <ul class="nav nav-pills">
              <li v-for="item in navigation" :key="item.id" @click="moveBt($event)"
                  class="tab-nav-item" :data-cible="item.name" :data-index="item.id"
                  :style="{width: itemNavWidth + '%'}">
                {{ item.name.toUpperCase() }}
              </li>
            </ul>
            <div class="bt-tab btn-wizard btn-primary" :style="styleBtMobile"></div>
          </div>
          <div class="tab-content ps-3 pe-3">
            <slot name="wizard-tabs-content"></slot>
          </div>

          <div class="d-flex wizard-footer">
            <div class="w-50 d-flex flex-column">
              <button v-if="etape > 0" class="btn btn-wizard btn-previous align-self-start" @click="wizardPrev($event)">
                Précédant
              </button>
            </div>
            <div class="w-50  d-flex flex-column">
              <button v-if="etape <= 1" type="button" class="btn btn-wizard btn-primary align-self-end"
                      @click="wizardNext($event)">Suivant
              </button>
              <button v-if="etape === (getNbItemNav() - 1)" type="button"
                      class="btn btn-wizard btn-primary align-self-end" @click="emitEvent('validerCreationPlace', {})">
                Valider
              </button>
            </div>

          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
console.log('-> WizardCreation.vue')

import { onMounted, onBeforeUnmount, ref } from 'vue'
import { emitEvent } from '../communs/EmitEvent'
import { useSessionStore } from '@/stores/session'

// material-bootstrap-wizard
import wizardBackground from '../assets/img/wizard-profile.jpg'

const props = defineProps({
  title: String
})

// session store
const sessionStore = useSessionStore()
const { updateHeader } = sessionStore

let styleBtMobile = ref({
  width: '10%',
  transform: 'translate3d(-8px, 0px, 0px)',
  transition: 'all 0.5s cubic-bezier(0.29, 1.42, 0.79, 1) 0s'
})

let navigation = ref([])
let itemNavWidth = ref(0)
let etape = ref(0)

updateHeader(null)

function init () {
  navigation.value = []
  const contents = document.querySelectorAll('.wizard-tab-content')
  // construire la navigation à partir des "tabs-content"
  const itemsNav = contents.length
  itemNavWidth.value = (100 / itemsNav).toFixed(3)
  styleBtMobile.value.width = itemNavWidth.value + '%'
  for (let i = 0; i < contents.length; i++) {
    const element = contents[i]
    const nameRaw = element.getAttribute('id')
    const name = nameRaw !== undefined ? nameRaw : 'inconnu'
    navigation.value.push({ id: i, name })
    // met à jour le bouton mobile avec le nom du premier item
    if (i === 0) {
      // text du bouton mobile
      document.querySelector('div[class~="bt-tab"]').innerText = name.toUpperCase()
      element.style.display = 'block'
    } else {
      element.style.display = 'none'
    }
  }
}

function getNbItemNav () {
  return document.querySelectorAll('ul[class="nav nav-pills"] li').length
}

function wizardNext (evt) {
  console.log('-> wizardNext :')
  console.log('evt =', evt)
  console.log('etape.value =', etape.value)

  evt.preventDefault()
  const index = etape.value + 1
  document.querySelector(`ul[class="nav nav-pills"] li[data-index="${index}"]`).click()
}

function wizardPrev (evt) {
  evt.preventDefault()
  const index = etape.value - 1
  document.querySelector(`ul[class="nav nav-pills"] li[data-index="${index}"]`).click()
}

function moveBt (event) {
  const ele = event.target
  // text du bouton mobile
  document.querySelector('div[class~="bt-tab"]').innerText = ele.innerText
  // animation
  const index = parseInt(ele.getAttribute('data-index'))
  etape.value = index
  const nbItem = document.querySelectorAll('.wizard-tab-content').length
  const navWidth = (document.querySelector('ul[class="nav nav-pills"]').offsetWidth / nbItem)
  // const itemNavs = document.querySelectorAll('ul[class="nav nav-pills"] li')
  let decX = 0
  if (index === 0) {
    decX = -8
  }
  if (index + 1 === nbItem) {
    decX = 8
  }
  styleBtMobile.value.transform = `translate3d(${decX + (index * navWidth)}px, 0px, 0px)`
  // désactivation / activation des onglets
  document.querySelectorAll('.wizard-tab-content').forEach(tab => {
    tab.style.display = 'none'
  })
  document.querySelector('#' + ele.getAttribute('data-cible')).style.display = 'block'
}

function callWizardNext () {
  const index = etape.value + 1
  document.querySelector(`ul[class="nav nav-pills"] li[data-index="${index}"]`).click()
}

document.addEventListener('wizardNext', callWizardNext)

document.addEventListener('resize', init)
onMounted(() => init())

onBeforeUnmount(() => {
  document.removeEventListener('resize', init)
  document.removeEventListener('wizardNext', callWizardNext)
})

</script>

<style scoped>
.wizard-card {
  min-height: 410px;
  box-shadow: 0 16px 24px 2px rgba(0, 0, 0, .14), 0 6px 30px 5px rgba(0, 0, 0, .12), 0 8px 10px -5px rgba(0, 0, 0, .2);
}

.wizard-card, .wizard-header {
  text-align: center;
  padding: 25px 0 35px;
}

.wizard-title {
  font-weight: 700;
}

.wizard-navigation {
  position: relative;
}

.tab-content {
  min-height: 340px;
  padding: 20px 15px;
}

.bt-tab {
  position: absolute;
  left: 0;
  top: -2px;
  text-align: center;
  padding: 14px 12px;
}

.tab-nav-item {
  border: 0 !important;
  border-radius: 0;
  line-height: 18px;
  text-transform: uppercase;
  font-size: 12px;
  font-weight: 500;
  min-width: 100px;
  text-align: center;
  color: #555 !important;
  padding: 12px !important;
  cursor: pointer;
}

.btn-wizard {
  font-size: 12px;
  text-transform: uppercase;
  -webkit-font-smoothing: subpixel-antialiased;
  left: 0;
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
  font-weight: bold;
  box-shadow: 0 16px 26px -10px rgba(244, 67, 54, .56), 0 4px 25px 0 rgba(0, 0, 0, .12), 0 8px 10px -5px rgba(244, 67, 54, .2);
  min-width: 140px;
}

.wizard-footer {
  padding: 0 15px;
}

.btn-previous {
  background-color: #999;
  color: #fff;
}
</style>