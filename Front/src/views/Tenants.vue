<template>
  <div class="container-fluid vw-100 vh-100" :style="`background-image: url('${wizardBackground}');background-repeat:no-repeat;background-size:cover;`">
    <div class="container">
      <!--      Wizard container        -->
      <div class="wizard-container">
        <div class="card wizard-card" data-color="red" id="wizard">
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
                <li :style="{width: itemNavWidth + '%'}">
                  <a href="#espace" class="nav-item-tab" style="font-size:12px !important;font-weight:500 !important;color: #555555 !important;padding:10px 15px !important;">
                    Espace
                  </a>
                </li>
                <li :style="{width: itemNavWidth + '%'}"><a href="#informations" class="h3">Informations</a></li>
                <li :style="{width: itemNavWidth + '%'}"><a href="#validation" class="nav-item-tab">Validation</a></li>
              </ul>
              <div class="moving-tab" :style="styleBtMobile">
                Espace
              </div>
            </div>
            <div class="tab-content ps-3 pe-3">
              <div id="espace" class="tab-pane active">
                contenu espace
              </div>
              <div id="information" class="tab-pane">
                contenu information
              </div>
              <div id="validation" class="tab-pane">
                contenu validation
              </div>
            </div>

            <div class="pull-right ps-3">
              <input type="button" class="btn btn-next btn-fill btn-danger btn-wd" name="next" value="Next" style="">
              <input type="button" class="btn btn-finish btn-fill btn-danger btn-wd" name="finish" value="Finish"
                     style="display: none;">
            </div>
            <div class="pull-left pe-3">
              <input type="button" class="btn btn-previous btn-fill btn-default btn-wd disabled" name="previous"
                     value="Previous">
            </div>

          </form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
console.log('-> Tenants.vue')
import { onMounted, ref, reactive } from 'vue'
import { useSessionStore } from '@/stores/session'
// import "../assets/js/material-bootstrap-wizard/material-bootstrap-wizard.js"

// material-bootstrap-wizard
import wizardBackground from '../assets/img/wizard-profile.jpg'
import '../assets/css/material-bootstrap-wizard/material-bootstrap-wizard.css'

// session store
const sessionStore = useSessionStore()
const { updateHeader } = sessionStore

let itemNavWidth = ref(0)
let styleBtMobile = ref({
  width: '10%',
  transform: 'translate3d(-8px, 0px, 0px)',
  transition: 'all 0.5s cubic-bezier(0.29, 1.42, 0.79, 1) 0s'
})

updateHeader(null)

function moveBt (event) {
  const ele = event.target
  // text du bouton mobile
  document.querySelector('div[class="moving-tab"]').innerText = ele.innerText
  // animation
  const index = parseInt(ele.getAttribute('index'))
  const nbItem = document.querySelectorAll('ul[class="nav nav-pills"] li').length
  const navWidth = (document.querySelector('ul[class="nav nav-pills"]').offsetWidth / nbItem)
  const itemNavs = document.querySelectorAll('ul[class="nav nav-pills"] li')
  let decX = 0
  if (index === 0) {
    decX = -8
  }
  if (index+1 === nbItem) {
    decX = 8
  }
  styleBtMobile.value.transform = `translate3d(${decX + (index * navWidth)}px, 0px, 0px)`
  // désactivation / activation des onglets
  document.querySelectorAll('div[class~="tab-pane"]').forEach(tab => {
    tab.classList.remove('active')
  })
  ele.classList.add('active')
}

function init() {
  const itemNavs = document.querySelectorAll('ul[class="nav nav-pills"] li')
  itemNavWidth.value = (100 / itemNavs.length).toFixed(3)
  styleBtMobile.value.width = itemNavWidth.value + '%'

  console.log('itemNavWidth.value =', itemNavWidth.value)
  console.log('styleBtMobile.value =', styleBtMobile)
  for (let i = 0; i < itemNavs.length; i++) {
    const item = itemNavs[i]
    item.querySelector('a').setAttribute('index', i)
    item.addEventListener('click', moveBt)
  }
}

addEventListener("resize", init);

onMounted(() => init())
</script>

<style scoped>
</style>