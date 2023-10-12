<template>
  <CreationStep title="Créer votre espace" sub-title="Sélectionner, éditer un type d'espace." validation-creation-msg="validerCreationPlace">
    <div id="espace" class="creation-tab-content">
      <div class="espace-content d-flex flex-wrap justify-content-around">

        <InputRadioImg v-for="(espace, index) in espacesType" :key="index" :label="espace.name" name="type-espace"
          :value="espace.categorie" :info="espace.description" :icons="espace.icons" :disable="espace.disable"
          :v-model="formCreatePlace.categorie" @update:model-value="newValue => formCreatePlace.categorie = newValue"
          style="margin: auto 0;"/>

      </div>
    </div>

    <div id="informations" class="creation-tab-content">
      <div class="espace-content d-flex flex-column">
        <InputMd id="creation-organisation" label="Organisation" height="22.4" color="red"
          v-model="formCreatePlace.organisation" class="mt-3" />

        <InputMd id="creation-short-description" label="Courte description" v-model="formCreatePlace.short_description" />

        <TextareaMd id="creation-long-description" label="Votre longue description"
          v-model="formCreatePlace.long_description" />

        <InputFileMd type="file" id="creation-img-url" label="Url image" v-model="formCreatePlace.img_url" class="mt-2" />

        <InputFileMd type="file" id="creation-logo-url" label="Url logo" v-model="formCreatePlace.logo_url" class="mt-2" />

      </div>
    </div>

    <div id="validation" class="creation-tab-content">
      <div class="espace-content d-flex flex-column">
        <h3>Résumé</h3>

        <div class="d-flex flex-row">
          <div class="d-flex align-items-start w-25">Catégorie</div>
          <div v-if="formCreatePlace.categorie !== ''" class="resume-valeur">{{ espacesType.find(espace => espace.categorie === formCreatePlace.categorie).name }}</div>
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
          <div v-if="formCreatePlace.img_url !== null" class="resume-valeur">{{ formCreatePlace.img_url.name }}</div>
        </div>
        <div class="d-flex flex-row">
          <div class="d-flex align-items-start w-25">Url du logo</div>
          <div v-if="formCreatePlace.logo_url !== null" class="resume-valeur">{{ formCreatePlace.logo_url.name }}</div>
        </div>
        <h3 class="mt-4" style="white-space: pre-line">Aurez vous besoin de récolter de l'argent ? (adhésion,
          billetterie, crowdfundind, caisse enregistreuse, cashless)</h3>

        <div class="d-flex flex-row justify-content-center">
          <div class="d-flex flex-row">
            <input type="radio" id="money" name="coin" value="true" />
            <label for="money">Oui</label>
          </div>
          <div class="d-flex flex-row ms-4">
            <input type="radio" id="no-money" name="coin" value="false" checked />
            <label for="no-money">Non</label>
          </div>
        </div>
      </div>
    </div>
  </CreationStep>
</template>

<script setup>
console.log("-> Tenants.vue");
import { useSessionStore } from "../stores/session";
import { emitEvent } from "../communs/EmitEvent";

import CreationStep from "../components/CreationStep.vue";
import InputMd from "../components/InputMd.vue";
import InputFileMd from "../components/InputFileMd.vue";
import TextareaMd from "../components/TextareaMd.vue";
import InputRadioImg from "../components/InputRadioImg.vue";


const sessionStore = useSessionStore();
const { setLoadingValue, updateHeader, getAccessToken } = sessionStore;

const iconsEspaceArtistique = [
  { name: "paint-brush", left: "20px", top: "20px" },
  { name: "music", left: "66px", top: "20px" },
  { name: "wheat-awn", left: "40px", top: "50px" },
  { name: "camera", left: "56px", top: "50px" },
  { name: "image", left: "20px", top: "76px" },
  { name: "film", left: "76px", top: "76px" }
]

// les données du formulaire
let formCreatePlace = {
  organisation: "",
  short_description: "",
  long_description: "",
  img_url: null,
  logo_url: null,
  categorie: "",
};

// les différents types d'espace à créer
const espacesType = [
  {
    name: "Artistique",
    description: "Pour tous projet artistique ...",
    icons: iconsEspaceArtistique,
    colorText: "white",
    disable: false,
    categorie: "A",
  },
  {
    name: "Lieu / association",
    description: "Pour tous lieu ou association ...",
    icons: [{ name: "house-flag", left: "40px", top: "40px" }, { name: "people-group", left: "56px", top: "50px" }],
    colorText: "white",
    disable: false,
    categorie: "S"
  },
  {
    name: "Festival",
    description: "Le Lorem Ipsum est simplement du faux texte employé dans la composition et la mise en page avant impression. Le Lorem Ipsum.",
    icons: [{ name: "music", left: "40px", top: "40px" }, { name: "people-group", left: "56px", top: "50px" }],
    colorText: "white",
    disable: true,
    categorie: "C"
  },
  {
    name: "Producteur",
    description: "On sait depuis longtemps que travailler avec du texte lisible et contenant du sens est source de distractions, et empêche de se concentrer sur la mise en page elle-même.",
    icons: [{ name: "building", left: "46px", top: "46px" }],
    colorText: "white",
    disable: true,
    categorie: "P"
  }
];

updateHeader(null);

function cursorOff(state) {
  if (state === true) {
    return "";
  } else {
    return "cursor: pointer;";
  }
}

// validation
document.addEventListener("validerCreationPlace", () => {
  // coin est de type string
  const coin = document.querySelector('input[name="coin"]:checked').value;

  let erreurs = [];

  if (formCreatePlace.categorie === "") {
    erreurs.push("Aucun type d'espace n'a été Selectionné !");
  }

  if (formCreatePlace.organisation === "") {
    erreurs.push(`Votre "organistation" n'a pas été renseignée !`);
  }

  if (formCreatePlace.short_description === "") {
    erreurs.push(`La courte description doit être renseignée !`);
  }

  if (formCreatePlace.img_url === null) {
    erreurs.push(`Veuillez sélectionner une image !`);
  }

  if (formCreatePlace.logo_url === null) {
    erreurs.push(`Veuillez sélectionner un logo !`);
  }

  console.log("formCreatePlace =", formCreatePlace);

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
})
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
</style>
