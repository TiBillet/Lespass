<template>
  <WizardCreation title="Créer votre espace">
    <template #wizard-subtitle>
      Sélectionner, éditer un type d'espace.
    </template>
    <template #wizard-tabs-content>
      <div id="espace" class="wizard-tab-content">
        <div class="espace-content d-flex flex-wrap justify-content-around">
          <div v-for="(espace, index) in espacesType" class="espace-card" :title="espace.description"
            :style="cursorOff(espace.disable)" @click="changeTenantCategorie(espace.categorie)">
            <img :src="espace.urlImage" class="espace-card-sub espace-type-img" :alt="'image - ' + espace.name">
            <div class="espace-card-sub d-flex flex-column justify-content-center align-content-center">
              <h5 class="card-title" :style="{color: espace.colorText}">{{ espace.name }}</h5>
            </div>
            <div v-if="espace.disable" class="espace-card-sub bg-dark opacity-5"></div>
          </div>
        </div>
        <input type="hidden" id="tenant-categorie" value="">
      </div>
      <div id="informations" class="wizard-tab-content">
        contenu informations
      </div>
      <div id="validation" class="wizard-tab-content">
        contenu validation
      </div>
    </template>
  </WizardCreation>
</template>

<script setup>

console.log('-> Tenants.vue')
import WizardCreation from '../components/WizardCreation.vue'

const espacesType = [
  {
    name: 'Artistique',
    description: 'Pour tous projet artistique ...',
    urlImage: 'https://picsum.photos/300/300',
    colorText: 'white',
    disable: false,
    categorie: "A"
  },
  {
    name: 'Lieu / association',
    description: 'Pour tous lieu ou association ...',
    urlImage: 'https://picsum.photos/300/300',
    colorText: 'white',
    disable: false,
    categorie: "B"
  },
  {
    name: 'Festival',
    description: 'Le Lorem Ipsum est simplement du faux texte employé dans la composition et la mise en page avant impression. Le Lorem Ipsum.',
    urlImage: 'https://picsum.photos/300/300',
    colorText: 'white',
    disable: true,
    categorie: "C"
  },
  {
    name: 'Producteur',
    description: 'On sait depuis longtemps que travailler avec du texte lisible et contenant du sens est source de distractions, et empêche de se concentrer sur la mise en page elle-même.',
    urlImage: 'https://picsum.photos/300/300',
    colorText: 'white',
    disable: true,
    categorie: "D"
  }
]
function changeTenantCategorie(categorie) {
  document.querySelector('#tenant-categorie').value = categorie
}

function cursorOff(state) {
  if (state === true) {
    return ''
  } else {
    return 'cursor: pointer;'

  }
}
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
  overflow-y: scroll;
}

</style>