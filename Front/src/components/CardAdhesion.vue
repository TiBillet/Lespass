<template>
      <!-- adhésion -->
    <fieldset v-if="dataProduct.categorie_article === 'A' && dataProduct.publish === true" class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
      <legend>Adhésion</legend>
      <div class="form-check form-switch">
        <input v-model="adhesion" class="form-check-input" type="checkbox" id="etat-adhesion"
               @change="majFormulaireBillet($event, 'adhesion')">
        <label class="form-check-label text-dark" for="etat-adhesion">Prendre une adhésion
          associative.</label>
      </div>
      <div v-if="adhesion">
        <!-- nom -->
        <div class="input-group mb-2 has-validation">
          <input v-model="nom" type="text"
                 class="form-control"
                 placeholder="Nom" aria-label="Nom pour l'adhésion" required
                 @keyup="majFormulaireBillet($event, 'adhesionInfos.nom')">
          <div class="invalid-feedback">Un nom svp !</div>
        </div>
        <!-- prénom -->
        <div class="input-group mb-2 has-validation">
          <input :value="store.state.formulaireBillet[uuidEvent].adhesionInfos.prenom" type="text"
                 id="adhesion-prenom" class="form-control"
                 placeholder="Prénom" aria-label="Prénom pour l'adhésion" required
                 @keyup="majFormulaireBillet($event, 'adhesionInfos.prenom')">
          <div class="invalid-feedback">Un prénom svp !</div>
        </div>
        <!-- adresse -->
        <div class="input-group mb-2 has-validation">
          <input :value="store.state.formulaireBillet[uuidEvent].adhesionInfos.adresse" id="adhesion-adresse"
                 type="text"
                 class="form-control" placeholder="Adresse" aria-label="Adresse pour l'adhésion" required
                 @keyup="majFormulaireBillet($event, 'adhesionInfos.adresse')">
          <div class="invalid-feedback">Une adresse svp !</div>
        </div>
        <!-- téléphone -->
        <div class="input-group mb-2 has-validation">
          <input :value="store.state.formulaireBillet[uuidEvent].adhesionInfos.tel" type="tel"
                 class="form-control"
                 placeholder="Fixe ou Mobile" pattern="^[0-9-+\s()]*$"
                 aria-label="Adresse pour l'adhésion" required
                 @keyup="majFormulaireBillet($event, 'adhesionInfos.tel')">
          <div class="invalid-feedback">Un numéro de téléphone svp !</div>
        </div>

      </div>
    </fieldset>
</template>

<script setup>
console.log('-> CardAdhesion.vue !')
// vue
import {useStore} from 'vuex'
import {ref} from 'vue'

const store = useStore()
// attributs/props
const props = defineProps({
  dataProduct: Object,
  uuidEvent: String,
})


// etat adhésion est égal au choix de l'utilisateur
let adhesion = ref(store.state.formulaireBillet[props.uuidEvent].adhesion)
// etat adhésion du lieu qui prime sur le choix de l'utilisateur
if (store.state.place.adhesion_obligatoire === true) {
  adhesion.value = store.state.place.adhesion_obligatoire
}

console.log('adhesion =', adhesion.value)
</script>

<style scoped>

</style>