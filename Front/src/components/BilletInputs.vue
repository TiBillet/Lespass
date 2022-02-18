<template>
  <fieldset class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded" v-for="price in dataProduct.prices" :key="price.uuid">
    <legend>
      <div class="d-flex flex-row">
        <div>{{ obtenirNombreBilletParTarif(price.uuid) }}</div>
        <div class="ms-3"> {{ dataProduct.name }} - {{ price.name }} {{ price.prix }}€ - Total
          {{ obtenirPrixParNombreBilletParTarif(price.uuid, price.prix)  }}€
        </div>
        <button class="btn btn-primary ms-3" type="button"
                @click="ajouterIdentiant(uuidEvent, price.uuid, price.stock)">
          <i class="fas fa-plus"></i>
        </button>
      </div>
    </legend>
    <div class="d-flex flex-row" v-for="(identifiant, index) in store.state.formulaireBillet[uuidEvent].identifiants" :key="index">
      <div v-if="identifiant.uuidTarif === price.uuid" class="input-group mb-2">
        <input type="text" :value="identifiant.nom" placeholder="Nom" aria-label="Nom" class="form-control"
               @keyup="majIdentifiant(uuidEvent,$event,'nom', identifiant.id)" required>
        <input type="text" :value="identifiant.prenom" placeholder="Prénom" aria-label="Prénom" class="form-control"
               @keyup="majIdentifiant(uuidEvent,$event,'prenom', identifiant.id)" required>
        <div class="invalid-tooltip me-4">Erreur, il manque une information svp</div>
        <button class="btn btn-primary mb-0" type="button" @click="supprimerIdentifiant(uuidEvent,identifiant.id)">
          <i class="fas fa-times"></i>
        </button>
      </div>
    </div>
  </fieldset>

</template>

<script setup>
console.log('-> BilletInputs.vue')

// vue
import {useStore} from 'vuex'

const store = useStore()
// attributs/props
const props = defineProps({
  dataProduct: Object,
  uuidEvent: String
})
console.log('props =', props)

function obtenirNombreBilletParTarif(uuidTarif) {
  return store.state.formulaireBillet[props.uuidEvent].identifiants.filter(iden => iden.uuidTarif === uuidTarif).length
  return 0
}

function obtenirPrixParNombreBilletParTarif(uuidTarif, prix) {
  const nbBillet = store.state.formulaireBillet[props.uuidEvent].identifiants.filter(iden => iden.uuidTarif === uuidTarif).length
  return nbBillet * prix

}

// créer les champs nom/prénom dans identifiants
function ajouterIdentiant( uuidEvent, uuidTarif, max) {
  store.commit('ajouterIdentiant', { uuidEvent: uuidEvent, uuidTarif: uuidTarif, max: max })
  // nombreBillet = store.state.formulaire[data.uuidEvent].identifiants.filter(iden => iden.uuidTarif === uuidTarif).length
}

function majIdentifiant(uuidEvent, event, champ, id) {
  let valeur = event.target.value
  store.commit('majIdentifiant', { uuidEvent: uuidEvent, valeur: valeur, champ: champ, id: id })
}

function supprimerIdentifiant(uuidEvent, id) {
  store.commit('supprimerIdentifiant', { uuidEvent: uuidEvent, id: id })
}
</script>

<style scoped>

</style>