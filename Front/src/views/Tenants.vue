<template>
  <div class="container-fluid vw-100 vh-100 d-flex justify-content-center align-items-center"
       :style="`background-image: url('${wizardBackground}');background-repeat:no-repeat;background-size:100% 100%;`">
    <div class="container">
      <div class="card wizard-card" data-color="red">
        {{ etape}}
        <form action="" method="">
          <div class="wizard-header">
            <h3 class="wizard-title">
              Créer votre espace
            </h3>
            <h5>Sélectionner, éditer un type d'espace.</h5>
          </div>
          <!-- navigation -->
          <div class="wizard-navigation">
            <ul class="nav nav-pills">
              <li :style="{width: itemNavWidth + '%'}" data-cible="espace" class="tab-nav-item">
                Espace
              </li>
              <li :style="{width: itemNavWidth + '%'}" data-cible="informations" class="tab-nav-item">
                Informations
              </li>
              <li :style="{width: itemNavWidth + '%'}" data-cible="validation" class="tab-nav-item">
                Validation
              </li>
            </ul>
            <div class="bt-tab btn-wizard" :style="styleBtMobile">
              Espace
            </div>
          </div>
          <div class="tab-content ps-3 pe-3">
            <div id="espace" class="tab-pane" style="display:block;">
              contenu espace
            </div>
            <div id="informations" class="tab-pane">
              contenu informations
            </div>
            <div id="validation" class="tab-pane">
              contenu validation
            </div>
          </div>

          <div class="d-flex wizard-footer">
            <div class="w-50 d-flex flex-column">
             <button v-if="etape > 0" class="btn btn-wizard btn-previous align-self-start">Previous</button>
            </div>
           <div class="w-50  d-flex flex-column">
            <button v-if="etape <= 1" type="button" class="btn btn-wizard btn-danger align-self-end">Next</button>
            <button v-if="etape === 2" type="button" class="btn btn-wizard btn-danger align-self-end">Finish</button>
           </div>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
console.log('-> Tenants.vue')
import { onMounted, onBeforeUnmount, ref, reactive } from 'vue'
import { useSessionStore } from '@/stores/session'

// material-bootstrap-wizard
import wizardBackground from '../assets/img/wizard-profile.jpg'

// session store
const sessionStore = useSessionStore()
const { updateHeader } = sessionStore

let itemNavWidth = ref(0)
let etape = ref(0)
let styleBtMobile = ref({
  width: '10%',
  transform: 'translate3d(-8px, 0px, 0px)',
  transition: 'all 0.5s cubic-bezier(0.29, 1.42, 0.79, 1) 0s'
})

updateHeader(null)

function moveBt (event) {
  const ele = event.target
  // text du bouton mobile
  document.querySelector('div[class~="bt-tab"]').innerText = ele.innerText
  // animation
  const index = parseInt(ele.getAttribute('index'))
  etape.value = index
  const nbItem = document.querySelectorAll('ul[class="nav nav-pills"] li').length
  const navWidth = (document.querySelector('ul[class="nav nav-pills"]').offsetWidth / nbItem)
  const itemNavs = document.querySelectorAll('ul[class="nav nav-pills"] li')
  let decX = 0
  if (index === 0) {
    decX = -8
  }
  if (index + 1 === nbItem) {
    decX = 8
  }
  styleBtMobile.value.transform = `translate3d(${decX + (index * navWidth)}px, 0px, 0px)`
  // désactivation / activation des onglets
  document.querySelectorAll('div[class="tab-pane"]').forEach(tab => {
    tab.style.display = "none"
  })
  document.querySelector('#' + ele.getAttribute('data-cible')).style.display = "block"
}

function init () {
  const itemNavs = document.querySelectorAll('ul[class="nav nav-pills"] li')
  itemNavWidth.value = (100 / itemNavs.length).toFixed(3)
  styleBtMobile.value.width = itemNavWidth.value + '%'

  // console.log('itemNavWidth.value =', itemNavWidth.value)
  // console.log('styleBtMobile.value =', styleBtMobile)
  for (let i = 0; i < itemNavs.length; i++) {
    const item = itemNavs[i]
    item.setAttribute('index', i)
    item.addEventListener('click', moveBt)
  }
}

addEventListener('resize', init)

onMounted(() => init())

// ne pas laisser trainer des "eventListener"
onBeforeUnmount(() => {
  const itemNavs = document.querySelectorAll('ul[class="nav nav-pills"] li')
  for (let i = 0; i < itemNavs.length; i++) {
    const item = itemNavs[i]
    item.removeEventListener('click', moveBt)
  }
  removeEventListener('resize', init)
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
  background-color: #f44336;
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