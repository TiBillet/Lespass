<template>
  <CreationStep title="Créer votre espace" sub-title="Sélectionner, éditer un type d'espace."
    validation-creation-msg="validerCreationPlace">
    <div id="espace" class="creation-tab-content">
      <div class="espace-content d-flex flex-column justify-content-around"
        :style="stripeStep?.action === 'expect_payment_stripe_createTenant' ? 'pointer-events:none;' : 'pointer-events: all;'">
        <div class="d-flex flex-wrap justify-content-around">
          <InputRadioImg v-for="(espace, index) in espacesType" :key="index" :label="espace.name" name="type-espace"
            :value="espace.categorie" :info="espace.description" :svg="espace.svg" :icons="espace.icons"
            :v-model="formCreatePlace.categorie" @update:model-value="newValue => formCreatePlace.categorie = newValue"
            style="margin: auto 0;" :style="espace.disable ? 'pointer-events:none;' : 'pointer-events: all;'" />
        </div>
        <InputMd id="login-email" label="Email" msg-error="Merci de renseigner une adresse email valide." type="email"
          :validation="true" class="w-50 ms-auto me-auto" v-model="formCreatePlace.email"/>

      </div>
    </div>

    <div id="informations" class="creation-tab-content"
      :style="stripeStep?.action === 'expect_payment_stripe_createTenant' ? 'pointer-events:none;' : 'pointer-events: all;'">
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

        <InputFileMd type="file" id="creation-img-url" label="Url image" v-model="formCreatePlace.img_url" class="mt-2" />

        <InputFileMd type="file" id="creation-logo-url" label="Url logo" v-model="formCreatePlace.logo_url"
          class="mt-2" />

      </div>
    </div>

    <div id="résumé" class="creation-tab-content"
      :style="stripeStep?.action === 'expect_payment_stripe_createTenant' ? 'pointer-events:none;' : 'pointer-events: all;'">
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
          <div v-if="formCreatePlace.img_url !== undefined && formCreatePlace.img_url !== null" class="resume-valeur">{{
            formCreatePlace.img_url.name }}</div>
        </div>
        <div class="d-flex flex-row">
          <div class="d-flex align-items-start w-25">Url du logo</div>
          <div v-if="formCreatePlace.logo_url !== undefined && formCreatePlace.logo_url !== null" class="resume-valeur">{{
            formCreatePlace.logo_url.name }}</div>
        </div>
        <h3 class="mt-4" style="white-space: pre-line">Aurez vous besoin de récolter de l'argent ? (adhésion,
          billetterie, crowdfundind, caisse enregistreuse, cashless)</h3>

        <div class="d-flex flex-row justify-content-center">
          <div class="d-flex flex-row">
            <input type="radio" id="money" name="coin" :value="true" v-model="coin"
              :checked="coin === true ? true : false" />
            <label for="money">Oui</label>
          </div>
          <div class="d-flex flex-row ms-4">
            <input type="radio" id="no-money" name="coin" :value="false" v-model="coin"
              :checked="coin === false ? true : false" />
            <label for="no-money">Non</label>
          </div>
        </div>
      </div>
    </div>

    <div id="Validation" class="creation-tab-content">
      <!-- <div>coin = {{ coin }} -- etapeValidation = {{ etapeValidation }} </div> stripeStep = {{ stripeStep }} -->
      <div class="espace-content d-flex flex-column justify-content-center align-items-center">
        <button v-if="etapeValidation === 'creationEspace' && (stripeStep === undefined || stripeStep.action === null)"
          type="button" class="btn btn-creation tibillet-bg-primary align-self-center text-white"
          @click="validerCreationPlace()">
          Valider la création de son espace
        </button>

        <button
          v-if="coin === true && (etapeValidation === 'creationCompteStripe' || stripeStep?.action === 'expect_payment_stripe_createTenant')"
          type="button" class="btn btn-creation tibillet-bg-primary align-self-center text-white"
          @click="CreationComteStripe()">
          Créer votre compte stripe
        </button>

        <button v-if="etapeValidation === 'creationCompteStripe'" type="button"
          class="btn btn-creation tibillet-bg-secondary align-self-center text-white" @click="resetState()">
          Annuler opération
        </button>
      </div>
    </div>

  </CreationStep>
</template>

<script setup>
console.log("-> Tenants.vue");

import { ref } from "vue"

import { useSessionStore } from "../stores/session";
import { setLocalStateKey, getLocalStateKey } from '../communs/storeLocal.js'
import { useRouter } from 'vue-router'

import CreationStep from "../components/CreationStep.vue";
import InputMd from "../components/InputMd.vue";
import InputFileMd from "../components/InputFileMd.vue";
import TextareaMd from "../components/TextareaMd.vue";
import InputRadioImg from "../components/InputRadioImg.vue";

// svg et image
import artistSvg from "../assets/img/artist.svg";
import homeSvg from "../assets/img/home.svg";
import communecterLogo from "../assets/img/communecterLogo_31x28.png"


let coin = ref(false)
let etapeValidation = ref('creationEspace')

const sessionStore = useSessionStore();
const { setLoadingValue, updateHeader, getAccessToken } = sessionStore;

const router = useRouter()

const iconsEspaceArtistique = [
  { name: "paint-brush", left: "20px", top: "20px" },
  { name: "music", left: "66px", top: "20px" },
  { name: "wheat-awn", left: "40px", top: "50px" },
  { name: "camera", left: "56px", top: "50px" },
  { name: "image", left: "20px", top: "76px" },
  { name: "film", left: "76px", top: "76px" }
]

// les données du formulaire
const initStateForm = {
  organisation: "",
  short_description: "",
  long_description: "",
  img_url: null,
  logo_url: null,
  categorie: "",
  email: ""
}

let formCreatePlace = ref(initStateForm)
const stripeStep = getLocalStateKey("stripeStep");
console.log('stripeStep.formCreatePlace =', stripeStep?.formCreatePlace);
if (stripeStep && stripeStep.action === 'expect_payment_stripe_createTenant') {
  formCreatePlace.value = stripeStep.formCreatePlace
  etapeValidation.value = "creationCompteStripe"
  coin.value = true
}

// les différents types d'espace à créer
const espacesType = [
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
    name: "Lieu / association",
    description: "Pour tous lieu ou association ...",
    icons: [],
    svg: { src: homeSvg, size: '4rem' },
    colorText: "white",
    disable: false,
    categorie: "S"
  }/*,
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

updateHeader(null);

function resetState() {
  setLocalStateKey("stripeStep", { action: null });
  formCreatePlace.value = initStateForm
  coin.value = false
  etapeValidation.value = 'creationEspace'
}

function getCategorieName(categorie) {
  console.log('-> getCategorieName =', categorie);
  if (categorie !== undefined) {
    return espacesType.find(espace => espace.categorie === categorie).name
  } else {
    return ''
  }
}
function cursorOff(state) {
  if (state === true) {
    return "";
  } else {
    return "cursor: pointer;";
  }
}

async function CreationComteStripe() {
  // enregistre l'email dans le storeUser
  console.log("-> goStripe Onboard");

  const api = `/api/onboard/`;
  try {
    setLoadingValue(true);

    // init étape creation stripe enregistrement en local(long durée)

    const updateFormCreatePlace = {
      organisation: formCreatePlace.value.organisation,
      short_description: formCreatePlace.value.short_description,
      long_description: formCreatePlace.value.long_description,
      img_url: { name: formCreatePlace.value.img_url.name },
      logo_url: { name: formCreatePlace.value.logo_url.name },
      categorie: formCreatePlace.value.categorie
    }
    // const creationStepData = JSON.parse(JSON.stringify(formCreatePlace.value))
    setLocalStateKey('stripeStep', { action: 'expect_payment_stripe_createTenant', formCreatePlace: updateFormCreatePlace, nextPath: '/' })

    const response = await fetch(api, {
      method: "GET",
      cache: "no-cache",
      headers: {
        "Content-Type": "application/json"
      }
    });
    const retour = await response.json();
    console.log("retour =", retour);
    if (response.status === 202) {
      location.href = retour;
    } else {
      throw new Error(`Erreur goStripe Onboard'`);
    }
  } catch (erreur) {
    console.log("-> validerLogin, erreur :", erreur);
    emitter.emit("toastSend", {
      title: "validerLogin, erreur :",
      contenu: erreur,
      typeMsg: "danger",
      delay: 8000
    });
  } finally {
    setLoadingValue(false);
  }
}


// validation
async function validerCreationPlace() {
  let erreurs = [];

  if (formCreatePlace.value.categorie === "") {
    erreurs.push("Aucun type d'espace n'a été Selectionné !");
  }

  if (formCreatePlace.value.organisation === "") {
    erreurs.push(`Votre "organistation" n'a pas été renseignée !`);
  }

  if (formCreatePlace.value.short_description === "") {
    erreurs.push(`La courte description doit être renseignée !`);
  }

  if (formCreatePlace.value.img_url === null) {
    erreurs.push(`Veuillez sélectionner une image !`);
  }

  if (formCreatePlace.value.logo_url === null) {
    erreurs.push(`Veuillez sélectionner un logo !`);
  }

  console.log("formCreatePlace.value =", formCreatePlace.value);

  if (erreurs.length > 0) {
    erreurs.forEach((erreur) => {
      emitter.emit("toastSend", {
        title: "Attention",
        contenu: erreur,
        typeMsg: "warning",
        delay: 6000
      });
    });
  }

  if (erreurs.length === 0) {
    try {
      // lieu / association
      let urlApi = "/api/place/";

      // artiste
      if (formCreatePlace.value.categorie === "A") {
        urlApi = "/api/artist/";
      }

      setLoadingValue(true)
      // proxy to object
      const formCreatePlaceObject = JSON.parse(JSON.stringify(formCreatePlace.value))
      const response = await fetch(urlApi, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + getAccessToken
        },
        body: JSON.stringify(formCreatePlaceObject)
      });
      console.log("response =", response);
      const retour = await response.json();
      // le tenant existe déjà
      if (response.status === 409) {
        throw new Error(retour.join(' - '));
      }
      if (response.status === 201) {
        // message de succès , non monétaire
        const typeEspace = espacesType.find(espace => espace.categorie === retour.categorie).name
        setLoadingValue(false)

        console.log('coin =', typeof (coin.value));
        if (coin.value === false) {
          router.push({ path: '/' })
        }
        const msg = `
            <div>Votre espace "${retour.organisation}" de type "${typeEspace}" a été créé.</div>
            <div>Lien: ${retour.domain}</div>`
        emitter.emit('modalMessage', {
          titre: 'Validation',
          typeMsg: 'success',
          contenu: msg,
          dynamic: true // pour insérer du html
        })
        if (coin.value === true) {
          // monétaire
          etapeValidation.value = "creationCompteStripe"
        }
      }
      console.log("retour =", retour);
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
}
</script>

<style scoped>
.creation-tab-content {
  --creation-content-height: 412px;
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
