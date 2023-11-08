<template>
  <div class="container-fluid vw-100 vh-100 d-flex justify-content-center align-items-center"
    :style="`background-image: url('${wizardBackground}');background-position:50% 50%;background-size:cover`">
    <div class="container">
      <div class="card creation-card">
        <div class="creation-header">
          etape = {{ etape }}
          <h3 class="creation-title">Créer votre espace</h3>
          <h5 class="creation-sub-title">Sélectionner, éditer un type d'espace.</h5>
        </div>

        <!-- navigation -->
        <div class="creation-navigation position-relative">
          <ul class="nav nav-pills">
            <li class="nav-item-creation tibillet-no-clickable" data-cible="espace" data-index="0"
              :style="{ width: itemNavWidth + '%' }">
              espace
            </li>
            <li class="nav-item-creation tibillet-no-clickable" data-cible="informations" data-index="1"
              :style="{ width: itemNavWidth + '%' }">
              informations</li>
            <li class="nav-item-creation tibillet-no-clickable" data-cible="résumé" data-index="2"
              :style="{ width: itemNavWidth + '%' }">
              résumé
            </li>
          </ul>
          <!-- bouton mobile -->
          <div class="bt-nav-creation tibillet-bg-primary" :style="styleBtMobile">Espaces</div>
        </div> <!-- fin navigation -->

        <!-- contenu -->
        <div class="creation-tabs-content ps-3 pe-3">

          <!-- type d'espace -->
          <div v-if="['espace', 'espaceFullData', 'showBtNextForGoInformations'].includes(etape)" id="espace"
            class="creation-tab-content">
            <div class="espace-content d-flex flex-column justify-content-around">
              <div class="d-flex flex-wrap justify-content-around">
                <InputRadioImg v-for="(espace, index) in espacesType" :key="index" :label="espace.name" name="type-espace"
                  :value="espace.categorie" :info="espace.description" :svg="espace.svg" :icons="espace.icons"
                  v-model="stateForm.categorie" @update:model-value="newValue => stateForm.categorie = newValue"
                  style="margin: auto 0;" :espaceNumber="espacesType.length" @click="service.send('evtInputsEspace')" />

              </div>
              <InputMd id="login-email" label="Email" msg-error="Merci de renseigner une adresse email valide."
                type="email" :validation="true" class="w-50 ms-auto me-auto" v-model="stateForm.email"
                @change="service.send('evtInputsEspace')" @blur="service.send('evtInputsEspace')" />

            </div>
            <!-- footer -->
            <div class="d-flex flex-row-reverse w-100 creation-footer">
              <button v-if="['showBtNextForGoInformations'].includes(etape)" type="button"
                @click="service.send('evtShowTabInformtions')" class="btn btn-creation tibillet-bg-primary" role="button"
                aria-label="go-informatisons">
                Suivant
              </button>
            </div>
          </div>

          <!-- informations -->
          <div v-if="['showTabInformtions', 'showBtNextForGoSummary'].includes(etape)"
            id="informations" class="creation-tab-content">
            <div class="espace-content d-flex flex-column">
              <!-- TODO: Importer vos données de communecté -->
              <button class="btn bg-gradient-info mt-4 mb-0 h-44px w-50 p-4" type="button">
                <div class="d-flex flex-row justify-content-center align-items-center h-100 w-100">
                  Importez vos données de <img :src="communecterLogo" class="ms-1" alt="logo communecter">
                </div>
              </button>

              <InputMd id="creation-organisation" label="Organisation" height="22.4" color="red"
                v-model="stateForm.organisation" class="mt-3" @change="service.send('evtInputsInformations')" />

              <InputMd id="creation-short-description" label="Courte description" v-model="stateForm.short_description"
                @change="service.send('evtInputsInformations')" />

              <TextareaMd id="creation-long-description" label="Votre longue description"
                v-model="stateForm.long_description" @change="service.send('evtInputsInformations')" />

              <InputFileMd type="file" id="creation-img-url" label="Url image" v-model="stateForm.img" class="mt-2"
                @change="service.send('evtInputsInformations')" />

              <InputFileMd type="file" id="creation-logo-url" label="Url logo" v-model="stateForm.logo" class="mt-2"
                @change="service.send('evtInputsInformations')" />
            </div>
            <!-- footer -->
            <div class="creation-footer d-flex justify-content-between">
              <button class="btn btn-creation btn-previous" @click="service.send('evtReturnEspace')">
                Précédent
              </button>
              <button v-if="['showBtNextForGoSummary'].includes(etape)"
                class="btn btn-creation tibillet-bg-primary" role="button" aria-label="go-resume"
                @click="service.send('evtShowTabSummary')">
                Suivant
              </button>
            </div>
          </div>

          <!-- Résumé / Summary -->
          <div v-if="['showTabSummary'].includes(etape)" id="résumé" class="creation-tab-content">
            <div class="espace-content d-flex flex-column">
              <div class="d-flex flex-row">
                <div class="d-flex align-items-start w-25">Catégorie</div>
                <div class="resume-valeur">
                  {{ espacesType.find(espace => espace.categorie === stateForm.categorie).name }}
                </div>
              </div>

              <div class="d-flex flex-row">
                <div class="d-flex align-items-start w-25">Email</div>
                <div class="resume-valeur">{{ stateForm.email }}</div>
              </div>

              <div class="d-flex flex-row">
                <div class="d-flex align-items-start w-25">Organisation</div>
                <div class="resume-valeur">{{ stateForm.organisation }}</div>
              </div>

              <div class="d-flex flex-row">
                <div class="d-flex align-items-start w-25">Coute description</div>
                <div class="resume-valeur">{{ stateForm.short_description }}</div>
              </div>
              <div class="d-flex flex-row">
                <div class="d-flex align-items-start w-25">Longue description</div>
                <div class="resume-valeur">{{ stateForm.long_description }}</div>
              </div>

              <div class="d-flex flex-row">
                <div class="d-flex align-items-start w-25">Url de l'image</div>
                <div class="resume-valeur">
                  {{ stateForm.img.name }}
                </div>
              </div>

              <div class="d-flex flex-row">
                <div class="d-flex align-items-start w-25">Url du logo</div>
                <div class="resume-valeur">
                  {{ stateForm.logo.name }}
                </div>
              </div>
            </div>
            <!-- footer -->
            <div class="creation-footer d-flex justify-content-between">
              <button class="btn btn-creation btn-previous" @click="service.send('evtReturnInformations')">
                Précédent
              </button>
              <button class="btn btn-creation tibillet-bg-primary" role="button" aria-label="go-resume"
                @click="createTenant()">
                Validation
              </button>
            </div>
          </div>

        </div> <!-- fin du contenu -->
      </div>
    </div>
  </div>
</template>

<script setup>
console.log("-> Tenants.vue");
import { ref, onMounted } from "vue"
import { useSessionStore } from "../stores/session";
// fond du wizard
import wizardBackground from "../assets/img/wizard-profile.jpg";
// communecte
import communecterLogo from "../assets/img/communecterLogo_31x28.png"
// svg et image
import homeSvg from "../assets/img/home.svg";
// composants
import InputMd from "../components/InputMd.vue";
import InputRadioImg from "../components/InputRadioImg.vue";
import TextareaMd from "../components/TextareaMd.vue";
import InputFileMd from "../components/InputFileMd.vue";
// machine
import { createMachine, interpret } from 'robot3';
import { machineCreateEvent } from "../communs/machineCreateEvent.js"

const sessionStore = useSessionStore();
const { updateHeader, setLoadingValue } = sessionStore;

// les différents types d'espace à créer
const espacesType = [{
  name: "Lieu / association",
  description: "Pour tous lieu ou association ...",
  icons: [],
  svg: { src: homeSvg, size: '4rem' },
  colorText: "white",
  disable: false,
  categorie: "S"
}];

// les données du formulaire
const initStateForm = {
  organisation: "",
  short_description: "",
  long_description: "",
  img: null,
  logo: null,
  categorie: "",
  email: "",
  stripe: true,
  espacesType
}
let stateForm = initStateForm

const contextMachine = () => (stateForm);

const initStyleBtMobile = {
  width: "10%",
  transform: "translate3d(-8px, 0px, 0px)",
  transition: "all 0.5s cubic-bezier(0.29, 1.42, 0.79, 1) 0s"
}
let styleBtMobile = ref(initStyleBtMobile);

let itemNavWidth = ref(0);
let etape = ref('espace')

function moveTitle(step) {
  // console.log('-> moveTitle, etape =', step);
  const convStepToIndex = {
    showTabInformtions: 1,
    showBtNextForGoSummary: 1,
    espace: 0,
    showBtNextForGoInformations: 0,
    showTabSummary: 2
  }
  const indexTitle = convStepToIndex[step]
  if (indexTitle !== undefined) {
    // get name
    const name = document.querySelector(`li[class~="nav-item-creation"][data-index="${indexTitle}"]`).innerText
    // replace name
    document.querySelector('div[class~="bt-nav-creation"]').innerText = name;
    // pour l'animation du bouton
    const nbItem = document.querySelectorAll(".creation-navigation li").length;
    const menuWidth = document.querySelector('ul[class="nav nav-pills"]').offsetWidth
    const navWidth = menuWidth / nbItem;
    let decX = 0;
    if (indexTitle === 0) {
      decX = -8;
    }
    if (indexTitle + 1 === nbItem) {
      decX = 8;
    }
    // actualise la position du bouton
    styleBtMobile.value.transform = `translate3d(${decX + indexTitle * navWidth}px, 0px, 0px)`;
  }
}


const machine = createMachine(machineCreateEvent, contextMachine)
const service = interpret(machine, () => {
  const ctx = service.machine.context()
  etape.value = service.machine.current
  console.log('-> Etape :', etape.value);
  console.log('-> ctx :', ctx);
  console.log('-----------------------------------------------------------')
  // position titre
  moveTitle(etape.value)

  // 
});

// dev
window.serice = service

updateHeader(null);

function test() {
  console.log('stateForm =', JSON.stringify(stateForm, null, 2));
}

function init() {
  const contents = document.querySelectorAll(".creation-navigation li");
  const itemsNav = contents.length;
  itemNavWidth.value = (100 / itemsNav).toFixed(3);
  styleBtMobile.value.width = itemNavWidth.value + "%";
}

// initialise le menu de navigation du composant
onMounted(() => {
  init()
});

function createTenant() {
  console.log('Création du tenant !');
  try {
    // lieu / association
    let urlApi = "/api/place/";

    // artiste
    if (stateForm.categorie === "A") {
      urlApi = "/api/artist/";
    }

    // spinner on
    setLoadingValue(true)

    const formData = new FormData();
    formData.append('organisation', stateForm.organisation);
    formData.append('short_description', stateForm.short_description);
    formData.append('long_description', stateForm.long_description);
    formData.append('email', stateForm.email);
    formData.append('stripe', stateForm.stripe);
    formData.append('logo', stateForm.logo);
    formData.append('img', stateForm.img);
    console.log('formData =', formData);

  } catch (error) {
    setLoadingValue(false)
    console.log(error);
    emitter.emit("toastSend", {
      title: "Erreur",
      contenu: error,
      typeMsg: "danger",
      delay: 8000
    });
  }
}
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

.creation-sub-title {
  font-size: 1.2em;
  font-weight: 200;
}

.creation-tabs-content {
  --creation-content-height: 530px;
  height: var(--creation-content-height);
  padding: 0 6px;
}

.creation-tab-content {
  width: 100%;
  height: var(--creation-content-height);
  margin: 0;
  padding: 0;
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

.tibillet-no-display {
  display: none;
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
</style>
