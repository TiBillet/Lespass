<template>
  <WizardCreation title="Créer votre espace">
    <template #wizard-subtitle>
      Sélectionner, éditer un type d'espace.
    </template>
    <template #wizard-tabs-content>
      <div id="espace" class="wizard-tab-content">
        <div class="espace-content d-flex flex-wrap justify-content-around">
          <div v-for="(espace, index) in espacesType" :key="index" class="espace-card" :title="espace.description"
               :style="cursorOff(espace.disable)"
               @click="changeTenantCategorie(espace.categorie);callWizardNext($event)">
            <img :src="espace.urlImage" class="espace-card-sub espace-type-img"
                 :alt="'image - ' + espace.name" loading="lazy">
            <div class="espace-card-sub d-flex flex-column justify-content-center align-content-center">
              <h5 class="card-title" :style="{color: espace.colorText}">{{ espace.name }}</h5>
            </div>
            <div v-if="espace.disable" class="espace-card-sub bg-dark opacity-5"></div>
          </div>
        </div>
      </div>
      <div id="informations" class="wizard-tab-content">
        <div class="espace-content d-flex flex-column">
          <div class="wizard-group">
            <input type="text" id="wizard-organisation" class="wizard-input" v-model="formCreatePlace.organisation">
            <label class="wizard-group-label" for="wizard-organisation">Organisation</label>
          </div>
          <div class="wizard-group">
            <input type="text" id="wizard-short-description" class="wizard-input"
                   v-model="formCreatePlace.short_description">
            <label class="wizard-group-label" for="wizard-short-description">Courte description</label>
          </div>
          <div class="wizard-group">
            <textarea id="wizard-long-description" class="wizard-input" placeholder="Votre longue description"
                      v-model="formCreatePlace.long_description" rows="3"></textarea>
            <label class="wizard-group-label" for="wizard-long-description">Longue description</label>
          </div>
          <div class="wizard-group">
            <input type="file" id="wizard-img-url" class="wizard-input" @change="fileChange($event, 'image')">
            <label class="wizard-group-label" for="wizard-img-url">Url image</label>
          </div>
          <div class="wizard-group">
            <input type="file" id="wizard-logo-url" class="wizard-input" @change="fileChange($event, 'logo')">
            <label class="wizard-group-label" for="wizard-logo-url">Url logo</label>
          </div>
        </div>
      </div>
      <div id="validation" class="wizard-tab-content">
        <div class="espace-content d-flex flex-column">
          <h3>Résumé</h3>
          <div class="d-flex flex-row">
            <div class="d-flex align-items-start w-25">organisation</div>
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
            <div v-if="formCreatePlace.logo_url !== null" class="resume-valeur">{{ formCreatePlace.logo_url.name }}
            </div>
          </div>
          <h3 class="mt-4" style="white-space: pre-line">Aurez vous besoin de récolter de l'argent ?
            (adhésion, billetterie, crowdfundind, caisse enregistreuse, cashless)
          </h3>

          <div class="d-flex flex-row justify-content-center">

            <div class="d-flex flex-row">
              <input type="radio" id="money" name="coin" value="true">
              <label for="money">Oui</label>
            </div>
            <div class="d-flex flex-row ms-4">
              <input type="radio" id="no-money" name="coin" value="false" checked>
              <label for="no-money">Non</label>
            </div>
          </div>
        </div>
      </div>
    </template>
  </WizardCreation>
</template>

<script setup>
console.log('-> Tenants.vue')
import { useSessionStore } from "../stores/session"
import { emitEvent } from '../communs/EmitEvent'
import WizardCreation from '../components/WizardCreation.vue'


const sessionStore = useSessionStore()
const { setLoadingValue } = sessionStore
let formCreatePlace = {
  organisation: '',
  short_description: '',
  long_description: '',
  img_url: null,
  logo_url: null,
  categorie: ''
}
const espacesType = [
  {
    name: 'Artistique',
    description: 'Pour tous projet artistique ...',
    urlImage: 'https://picsum.photos/300/300',
    colorText: 'white',
    disable: false,
    categorie: 'A'
  },
  {
    name: 'Lieu / association',
    description: 'Pour tous lieu ou association ...',
    urlImage: 'https://picsum.photos/300/300',
    colorText: 'white',
    disable: false,
    categorie: 'S'
  },
  {
    name: 'Festival',
    description: 'Le Lorem Ipsum est simplement du faux texte employé dans la composition et la mise en page avant impression. Le Lorem Ipsum.',
    urlImage: 'https://picsum.photos/300/300',
    colorText: 'white',
    disable: true,
    categorie: 'C'
  },
  {
    name: 'Producteur',
    description: 'On sait depuis longtemps que travailler avec du texte lisible et contenant du sens est source de distractions, et empêche de se concentrer sur la mise en page elle-même.',
    urlImage: 'https://picsum.photos/300/300',
    colorText: 'white',
    disable: true,
    categorie: 'P'
  }
]

function fileChange (evt, typeFile) {
  if (typeFile === 'image') {
    formCreatePlace.img_url = evt.target.files[0]
  }
  if (typeFile === 'logo') {
    formCreatePlace.logo_url = evt.target.files[0]
  }

}

function callWizardNext (evt) {
  evt.preventDefault()
  emitEvent('wizardNext', {})
}

function changeTenantCategorie (categorie) {
  formCreatePlace.categorie = categorie
}

function cursorOff (state) {
  if (state === true) {
    return ''
  } else {
    return 'cursor: pointer;'

  }
}
async function goStripe () {
  // enregistre l'email dans le storeUser
  console.log('-> goStripe Onboard')

  const api = `/api/onboard/`
  try {
    setLoadingValue(true)

    const response = await fetch( api, {
      method: 'GET',
      cache: 'no-cache',
      headers: {
        'Content-Type': 'application/json'
      },
    })
    const retour = await response.json()
    console.log('retour =', retour)
    if (response.status === 202) {
      location.href = retour
    } else {
      throw new Error(`Erreur goStripe Onboard'`)
    }
  } catch (erreur) {
    console.log('-> validerLogin, erreur :', erreur)
    setLoadingValue(false)
      emitter.emit('toastSend', {
          title: 'validerLogin, erreur :',
          contenu: erreur,
          typeMsg: 'danger',
          delay: 8000
        })
  }
}

async function validerCreationPlace () {
  const coin = document.querySelector('input[name="coin"]:checked').value

  let erreurs = []

  if (formCreatePlace.categorie === '') {
    erreurs.push('Aucun type d\'espace n\'a été Selectionné !')
  }

  if (formCreatePlace.organisation === '') {
    erreurs.push(`Votre "organistation" n'a pas été renseignée !`)
  }

  if (formCreatePlace.short_description === '') {
    erreurs.push(`La courte description doit être renseignée !`)
  }

  if (formCreatePlace.img_url === null) {
    erreurs.push(`Veuillez sélectionner une image !`)
  }

  if (formCreatePlace.logo_url === null) {
    erreurs.push(`Veuillez sélectionner un logo !`)
  }

  console.log('formCreatePlace =', formCreatePlace)
  if (erreurs.length > 0) {
    erreurs.forEach(erreur => {
      emitter.emit('toastSend', {
        title: 'Attention',
        contenu: erreur,
        typeMsg: 'warning',
        delay: 6000
      })
    })
  } else {
    // nom monétaire
    if (coin === false) {
      try {
        const response = await fetch('/api/place/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(formCreatePlace)
        })
        console.log('response =', response)
        const retour = await response.json()
        console.log('retour =', retour)
      } catch (error) {
        console.log(error)
        emitter.emit('toastSend', {
          title: 'Erreur',
          contenu: error,
          typeMsg: 'danger',
          delay: 8000
        })
      }
    } else {
      // monétaire
      goStripe()
    }
  }
}

document.addEventListener('validerCreationPlace', validerCreationPlace)
</script>
<style scoped>
.wizard-tab-content {
  --wizard-content-height: 412px;
  min-height: var(--wizard-content-height);
  max-height: var(--wizard-content-height);
}

.espace-card, .espace-card-sub {
  width: 200px;
  height: 200px;
}

.espace-card {
  border-radius: 4px;
  box-shadow: 0 16px 26px -10px rgba(244, 67, 54, .56), 0 4px 25px 0 rgba(0, 0, 0, .12), 0 8px 10px -5px rgba(244, 67, 54, .2);
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
  min-height: var(--wizard-content-height);
  max-height: var(--wizard-content-height);
  overflow-x: hidden;
  overflow-y: auto;
}

.wizard-group {
  position: relative;
  padding: 15px 0 0;
  margin-top: 6px;
}

.wizard-input {
  font-family: inherit;
  width: 100%;
  border: 0;
  border-bottom: 1px solid #d2d2d2;
  outline: 0;
  font-size: 16px;
  color: #212121;
  padding: 7px 0;
  background: transparent;
  transition: border-color 0.2s;
}

.wizard-group-label {
  position: absolute;
  top: 0;
  display: block;
  transition: 0.2s;
  font-size: 12px;
  color: #9b9b9b;
}
</style>