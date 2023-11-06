<template>
  <CreationStep title="Créer votre espace" sub-title="Sélectionner, éditer un type d'espace."
    validation-creation-msg="validerCreationPlace">
    <div id="espace" class="creation-tab-content">
      <div class="espace-content d-flex flex-column justify-content-around">
        <div class="d-flex flex-wrap justify-content-around">
          <InputRadioImg v-for="(espace, index) in espacesType" :key="index" :label="espace.name" name="type-espace"
            :value="espace.categorie" :info="espace.description" :svg="espace.svg" :icons="espace.icons"
            :v-model="formCreatePlace.categorie" @update:model-value="newValue => formCreatePlace.categorie = newValue"
            style="margin: auto 0;" :style="espace.disable ? 'pointer-events:none;' : 'pointer-events: all;'"
             :espaceNumber="espacesType.length"/>
        </div>
        <InputMd id="login-email" label="Email" msg-error="Merci de renseigner une adresse email valide." type="email"
          :validation="true" class="w-50 ms-auto me-auto" v-model="formCreatePlace.email" />
      </div>
    </div>

    <div id="informations" class="creation-tab-content">
      <div class="espace-content d-flex flex-column">
        <!-- TODO: Importer vos données de communecté -->
        <button class="btn bg-gradient-info mt-4 mb-0 h-44px w-50 p-4" type="button">
          <div class="d-flex flex-row justify-content-center align-items-center h-100 w-100">
            Importez vos données de <img :src="communecterLogo" class="ms-1" alt="logo communecter">
          </div>
        </button>



        <InputMd id="creation-organisation" label="Organisation" height="22.4" color="red"
          v-model="formCreatePlace.organisation" class="mt-3" />

        <InputMd id="creation-short-description" label="Courte description" v-model="formCreatePlace.short_description" />

        <TextareaMd id="creation-long-description" label="Votre longue description"
          v-model="formCreatePlace.long_description" />

        <InputFileMd type="file" id="creation-img-url" label="Url image" v-model="formCreatePlace.img" class="mt-2" />

        <InputFileMd type="file" id="creation-logo-url" label="Url logo" v-model="formCreatePlace.logo" class="mt-2" />

      </div>
    </div>

    <div id="résumé" class="creation-tab-content">
      <div class="espace-content d-flex flex-column">
        <div class="d-flex flex-row">
          <div class="d-flex align-items-start w-25">Catégorie</div>
          <div v-if="formCreatePlace.categorie !== ''" class="resume-valeur">{{
            getCategorieName(formCreatePlace.categorie) }}</div>
        </div>

        <div class="d-flex flex-row">
          <div class="d-flex align-items-start w-25">Email</div>
          <div class="resume-valeur">{{ formCreatePlace.email }}</div>
        </div>

        <div class="d-flex flex-row">
          <div class="d-flex align-items-start w-25">Organisation</div>
          <div class="resume-valeur">{{ formCreatePlace.organisation }}</div>
        </div>

        <div class="d-flex flex-row">
          <div class="d-flex align-items-start w-25">Coute description</div>
          <div class="resume-valeur">{{ formCreatePlace.short_description }}</div>
        </div>
        <div class="d-flex flex-row">
          <div class="d-flex align-items-start w-25">Longue description</div>
          <div class="resume-valeur">{{ formCreatePlace.long_description }}</div>
        </div>
        <div class="d-flex flex-row">
          <div class="d-flex align-items-start w-25">Url de l'image</div>
          <div v-if="formCreatePlace.img_url !== undefined && formCreatePlace.img !== null" class="resume-valeur">{{
            formCreatePlace.img.name }}</div>
        </div>
        <div class="d-flex flex-row">
          <div class="d-flex align-items-start w-25">Url du logo</div>
          <div v-if="formCreatePlace.logo !== undefined && formCreatePlace.logo !== null" class="resume-valeur">{{
            formCreatePlace.logo.name }}</div>
        </div>
      </div>
    </div>

  </CreationStep>
</template>

<script setup>
console.log("-> Tenants.vue");

// machine
import { CreateMachine} from "../communs/CreateMachine.js"
import { machineCreateEvent } from "../communs/machineCreateEvent.js"

import { ref, onMounted } from "vue"

import { useSessionStore } from "../stores/session";
import { setLocalStateKey, getLocalStateKey } from '../communs/storeLocal.js'
import { useRouter } from 'vue-router'

import CreationStep from "../components/CreationStep.vue";
import InputMd from "../components/InputMd.vue";
import InputFileMd from "../components/InputFileMd.vue";
import TextareaMd from "../components/TextareaMd.vue";
import InputRadioImg from "../components/InputRadioImg.vue";

// svg et image
// import artistSvg from "../assets/img/artist.svg";
import homeSvg from "../assets/img/home.svg";
import communecterLogo from "../assets/img/communecterLogo_31x28.png"


let coin = ref(false)
let etapeValidation = ref('creationEspace')

const sessionStore = useSessionStore();
const { setLoadingValue, updateHeader, getAccessToken } = sessionStore;

const router = useRouter()

// les différents types d'espace à créer
const espacesType = [
  {
    name: "Lieu / association",
    description: "Pour tous lieu ou association ...",
    icons: [],
    svg: { src: homeSvg, size: '4rem' },
    colorText: "white",
    disable: false,
    categorie: "S"
  }/*,
    {
    name: "Artistique",
    description: "Pour tous projet artistique ...",
    icons: [],
    svg: { src: artistSvg, size: '4rem' },
    colorText: "white",
    disable: false,
    categorie: "A",
  },
  {
    name: "Festival",
    description: "Le Lorem Ipsum est simplement du faux texte employé dans la composition et la mise en page avant impression. Le Lorem Ipsum.",
    icons: [{ name: "music", left: "40px", top: "40px" }, { name: "people-group", left: "56px", top: "50px" }],
    svg: null,
    colorText: "white",
    disable: true,
    categorie: "C"
  },
  {
    name: "Producteur",
    description: "On sait depuis longtemps que travailler avec du texte lisible et contenant du sens est source de distractions, et empêche de se concentrer sur la mise en page elle-même.",
    icons: [{ name: "building", left: "46px", top: "46px" }],
    svg: null,
    colorText: "white",
    disable: true,
    categorie: "P"
  }
  */
];

// les données du formulaire
const initStateForm = {
  organisation: "",
  short_description: "",
  long_description: "",
  img: null,
  logo: null,
  categorie: "",
  email: "",
  stripe: false,
  espacesType
}

let formCreatePlace = ref(initStateForm)

const machine = new CreateMachine(initStateForm, machineCreateEvent)

const iconsEspaceArtistique = [
  { name: "paint-brush", left: "20px", top: "20px" },
  { name: "music", left: "66px", top: "20px" },
  { name: "wheat-awn", left: "40px", top: "50px" },
  { name: "camera", left: "56px", top: "50px" },
  { name: "image", left: "20px", top: "76px" },
  { name: "film", left: "76px", top: "76px" }
]

updateHeader(null);

function getCategorieName(categorie) {
  console.log('-> getCategorieName =', categorie);
  if (categorie !== undefined) {
    return espacesType.find(espace => espace.categorie === categorie).name
  } else {
    return ''
  }
}

onMounted(() => {  
  machine.init('selectEspace')
  //console.log('machine.state =', JSON.stringify(machine.state, null, 2));
})



</script>

<style scoped>
.creation-tab-content {
  --creation-content-height: 452px;
  min-height: var(--creation-content-height);
  max-height: var(--creation-content-height);
  display: none;
}


.espace-card,
.espace-card-sub {
  width: 200px;
  height: 200px;
}

.espace-card {
  border-radius: 4px;
  box-shadow: 0 16px 26px -10px rgba(244, 67, 54, 0.56), 0 4px 25px 0 rgba(0, 0, 0, 0.12), 0 8px 10px -5px rgba(244, 67, 54, 0.2);
  margin-bottom: 6px;
  overflow: hidden;
  margin-top: 6px;
  position: relative;
}

.espace-card-sub {
  position: absolute;
  top: 0;
  left: 0;
}

.espace-content {
  width: 100%;
  min-height: var(--creation-content-height);
  max-height: var(--creation-content-height);
  overflow-x: hidden;
  overflow-y: auto;
}

.btn-creation {
  font-size: 12px;
  line-height: 12px;
  text-transform: uppercase;
  border-radius: 4px;
  color: #ffffff;
  cursor: pointer;
  font-weight: bold;
  box-shadow: 0 16px 26px -10px rgba(244, 67, 54, 0.56), 0 4px 25px 0 rgba(0, 0, 0, 0.12), 0 8px 10px -5px rgba(244, 67, 54, 0.2);
  min-width: 140px;
  padding: 1.3rem;
}
</style>
