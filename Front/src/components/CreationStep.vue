<template>
  {{ etape }}
  <div class="container-fluid vw-100 vh-100 d-flex justify-content-center align-items-center"
    :style="`background-image: url('${wizardBackground}');background-position:50% 50%;background-size:cover`">
    <div class="container">
      <div class="card creation-card">
        <div class="creation-header">
          <h3 class="creation-title">{{ title }}</h3>
          <h5 class="creation-sub-title">{{ subTitle }}</h5>
        </div>

        <!-- navigation -->
        <div class="creation-navigation" @vue:updated="updateNav()">
          <ul class="nav nav-pills">
            <li v-for="item in navigation" :key="item.id" @click="moveBt($event)" class="nav-item-creation"
              :data-cible="item.name" :data-index="item.id" :style="{ width: itemNavWidth + '%' }">
              {{ item.name.toUpperCase() }}
            </li>
          </ul>
          <!-- bouton mobile -->
          <div class="bt-nav-creation boutik-bg-primary" :style="styleBtMobile"></div>
        </div>

        <!-- content -->
        <div class="creation-tabs-content ps-3 pe-3">
          <slot></slot>
        </div>

        <div class="d-flex creation-footer">
          <div class="w-50 d-flex flex-column">
            <button v-if="etape > 0" class="btn btn-creation btn-previous align-self-start"
              @click="navCreationPrev($event)">Précédent</button>
          </div>
          <div class="w-50 d-flex flex-column">
            <button v-if="etape < getNbItemNav() - 1" type="button"
              class="btn btn-creation boutik-bg-primary align-self-end" @click="navCreationNext($event)">Suivant</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
console.log("-> CreationStep.vue");
import { onMounted, onBeforeUnmount, ref } from "vue";
import { emitEvent } from "../communs/EmitEvent";

// material-bootstrap-wizard
import wizardBackground from "../assets/img/wizard-profile.jpg";

const props = defineProps({
  title: String,
  subTitle: String,
  validationCreationMsg: String
});

const initStyleBtMobile = {
  width: "10%",
  transform: "translate3d(-8px, 0px, 0px)",
  transition: "all 0.5s cubic-bezier(0.29, 1.42, 0.79, 1) 0s"
}
let navigation = ref([]);
let itemNavWidth = ref(0);
let etape = ref(0);
let styleBtMobile = ref(initStyleBtMobile);


function init() {
  navigation.value = [];
  itemNavWidth.value = 0
  etape.value = 0
  styleBtMobile.value = initStyleBtMobile
  const contents = document.querySelectorAll(".creation-tab-content");
  // construire la navigation à partir des ".creation-tab-content" pour le template (v-for)
  const itemsNav = contents.length;
  itemNavWidth.value = (100 / itemsNav).toFixed(3);
  styleBtMobile.value.width = itemNavWidth.value + "%";
  for (let i = 0; i < contents.length; i++) {
    const element = contents[i];
    const nameRaw = element.getAttribute("id");
    const name = nameRaw !== undefined ? nameRaw : "inconnu";
    navigation.value.push({ id: i, name });
  }
}

function updateNav() {
  const indexBt = etape.value

  // text du bouton mobile
  const currentItem = document.querySelector(`li[data-index="${indexBt}"]`)
  const textBt = currentItem.innerText
  document.querySelector('div[class~="bt-nav-creation"]').innerText = textBt;
  // pour l'animation du bouton
  const nbItem = document.querySelectorAll(".creation-tab-content").length;
  const menuWidth = document.querySelector('ul[class="nav nav-pills"]').offsetWidth
  const navWidth = menuWidth / nbItem;
  let decX = 0;
  if (indexBt === 0) {
    decX = -8;
  }
  if (indexBt + 1 === nbItem) {
    decX = 8;
  }
  // actualise la position du bouton
  styleBtMobile.value.transform = `translate3d(${decX + indexBt * navWidth}px, 0px, 0px)`;
  // désactivation / activation des onglets
  document.querySelectorAll(".creation-tab-content").forEach((tab) => {
    tab.style.display = "none";
  });
  // active le contenu adequate
  const currentIdContent = "#" + currentItem.getAttribute("data-cible")
  document.querySelector(currentIdContent).style.display = "block";
}

function moveBt(event) {
  const itemMenu = event.target;
  const index = parseInt(itemMenu.getAttribute("data-index"));
  etape.value = index;
  updateNav()
}

function getNbItemNav() {
  return document.querySelectorAll('ul[class="nav nav-pills"] li').length;
}

function navCreationNext(evt) {
  evt.preventDefault();
  const index = etape.value + 1;
  document.querySelector(`ul[class="nav nav-pills"] li[data-index="${index}"]`).click();
}

function navCreationPrev(evt) {
  evt.preventDefault();
  const index = etape.value - 1;
  document.querySelector(`ul[class="nav nav-pills"] li[data-index="${index}"]`).click();
}

function callNavCreationNext() {
  const index = etape.value + 1;
  document.querySelector(`ul[class="nav nav-pills"] li[data-index="${index}"]`).click();
}


window.addEventListener("resize", updateNav, false);
document.addEventListener("navCreationNext", callNavCreationNext);

// initialise le menu de navigation du composant
onMounted(() => {
  init()
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", updateNav);
  document.removeEventListener("navCreationNext", callNavCreationNext);
});
</script>

<style scoped>
.creation-card {
  min-height: 410px;
  box-shadow: 0 16px 24px 2px rgba(0, 0, 0, 0.14), 0 6px 30px 5px rgba(0, 0, 0, 0.12), 0 8px 10px -5px rgba(0, 0, 0, 0.2);
}

.creation-card,
.creation-header {
  text-align: center;
  padding: 25px 0 35px;
}

.creation-title {
  font-weight: 700;
}

.creation-sub-title {
  font-size: 1.2em;
  font-weight: 200;
}

.creation-navigation {
  position: relative;
}

.creation-tabs-content {
  min-height: 340px;
  padding: 20px 15px;
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
  cursor: pointer;
  font-weight: bold;
  box-shadow: 0 16px 26px -10px rgba(244, 67, 54, 0.56), 0 4px 25px 0 rgba(0, 0, 0, 0.12), 0 8px 10px -5px rgba(244, 67, 54, 0.2);
  min-width: 140px;
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

.btn-creation {
  font-size: 12px;
  text-transform: uppercase;
  /* left: 0; */
  border-radius: 4px;
  color: #ffffff;
  cursor: pointer;
  font-weight: bold;
  box-shadow: 0 16px 26px -10px rgba(244, 67, 54, 0.56), 0 4px 25px 0 rgba(0, 0, 0, 0.12), 0 8px 10px -5px rgba(244, 67, 54, 0.2);
  min-width: 140px;
}

.creation-footer {
  padding: 0 15px;
}

.btn-previous {
  background-color: #999;
  color: #fff;
}</style>
