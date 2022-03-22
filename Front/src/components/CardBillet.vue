<template>
  <fieldset class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded" v-for="price in product.prices"
            :key="price.uuid">
    <legend>
      <div class="d-flex flex-row">
        <div>{{ obtenirNombreBilletParTarif(price.uuid, price.stock) }}</div>
        <div class="ms-3"> {{ product.name }} - {{ price.name }} {{ price.prix }}€ - Total
          {{ obtenirPrixParNombreBilletParTarif(price.uuid, price.prix) }}€ - Stock
          {{ reste(price.uuid) }}
        </div>


        <button v-if="stockOk(price.uuid)" class="btn btn-primary ms-3" type="button"
                @click.stop="ajouterIdentiant(price.uuid)">
          <i class="fas fa-plus"></i>
        </button>
      </div>
    </legend>
    <div class="d-flex flex-row"
         v-for="(identifiant, index) in store.formulaireBillet[store.currentUuidEvent].identifiants[price.uuid].users"
         :key="index">
      <div class="input-group mb-2">
        <input type="text" :value="identifiant.nom" placeholder="Nom" aria-label="Nom" class="form-control"
               @keyup="majIdentifiant(price.uuid, $event,'nom', identifiant.id)" required>
        <input type="text" :value="identifiant.prenom" placeholder="Prénom" aria-label="Prénom" class="form-control"
               @keyup="majIdentifiant(price.uuid, $event,'prenom', identifiant.id)" required>
        <div class="invalid-tooltip me-4">Erreur, il manque une information svp</div>
        <button class="btn btn-primary mb-0" type="button" @click="supprimerIdentifiant(price.uuid, identifiant.id)">
          <i class="fas fa-times"></i>
        </button>
        <div class="invalid-feedback">Donnée(s) manquante(s) !</div>
      </div>
    </div>
  </fieldset>

</template>

<script setup>
console.log('-> CardBillet.vue')

// vue
import {computed} from 'vue'

// store
import {useStore} from '@/store'

const store = useStore()
// attributs/props
const props = defineProps({
  product: Object
})
// console.log('props =', props)
// console.log('store.currentUuidEvent =', store.currentUuidEvent)

// init identifiants et tarifs
if (store.formulaireBillet[store.currentUuidEvent].identifiants === undefined) {
  store.formulaireBillet[store.currentUuidEvent]['identifiants'] = {}
}

for (const key in props.product.prices) {
  const uuid = props.product.prices[key].uuid
  const stock = props.product.prices[key].stock
  if (store.formulaireBillet[store.currentUuidEvent].identifiants[uuid] === undefined) {
    store.formulaireBillet[store.currentUuidEvent].identifiants[uuid] = {
      index: 0,
      users: [],
      stock: stock
    }
  }
}


function stockOk(uuidTarif) {
  const nbBillet = store.formulaireBillet[store.currentUuidEvent].identifiants[uuidTarif].users.length
  const stock = store.formulaireBillet[store.currentUuidEvent].identifiants[uuidTarif].stock
  if (nbBillet + 1 <= stock) {
    return true
  }
  return false
}

function reste(uuidTarif) {
  const nbBillet = store.formulaireBillet[store.currentUuidEvent].identifiants[uuidTarif].users.length
  const stock = store.formulaireBillet[store.currentUuidEvent].identifiants[uuidTarif].stock
  // TODO: if((stock - nbBillet) === 0) afficher message "rupture de stock !" en modal
  return (stock - nbBillet)
}


function obtenirNombreBilletParTarif(uuidTarif, stock) {
  return store.formulaireBillet[store.currentUuidEvent].identifiants[uuidTarif].users.length
}

function obtenirPrixParNombreBilletParTarif(uuidTarif, prix) {
  const nbBillet = store.formulaireBillet[store.currentUuidEvent].identifiants[uuidTarif].users.length
  return nbBillet * prix

}

// créer les champs nom/prénom dans identifiants
function ajouterIdentiant(uuidTarif, max) {
  emitter.emit('gererCardBillet', {action: 'ajouter', uuidTarif: uuidTarif, max: max})
}

function majIdentifiant(uuidTarif, event, champ, id) {
  let valeur = event.target.value
  emitter.emit('gererCardBillet', {action: 'modifier', uuidTarif: uuidTarif, valeur: valeur, champ: champ, id: id})
}

function supprimerIdentifiant(uuidTarif, id) {
  console.log('id =', id)
  emitter.emit('gererCardBillet', {action: 'supprimer', uuidTarif: uuidTarif, id: id})
}

</script>

<style scoped>

</style>