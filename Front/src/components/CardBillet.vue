<template>
  <fieldset class="shadow-sm p-3 mb-5 bg-body rounded" v-for="price in prix"
            :key="price.uuid">
    <legend>
      <div class="d-flex justify-content-between mb-3">
        <h3 class="font-weight-bolder text-info text-gradient align-self-start">{{ product.name }} {{ price.name.toLowerCase() }} : {{ price.prix }}€</h3>
        <button v-if="(price.stock - price.users.length) >= 1" class="btn btn-primary ms-3" type="button"
                @click.stop="addUser(price.uuid)">
          <i class="fas fa-plus"></i>
        </button>
      </div>
    </legend>

    <!-- <div class="d-flex flex-row" v-for="(user, index) in price.users" :key="index"> -->
    <div class="input-group mb-2" v-for="(user, index) in price.users" :key="index">
      <input type="text" :value="user.last_name" placeholder="Nom" aria-label="Nom" class="form-control"
             @keyup="updateUser(price.uuid, user.uuid, $event.target.value,'last_name')" required>
      <input type="text" :value="user.first_name" placeholder="Prénom" aria-label="Prénom" class="form-control"
             @keyup="updateUser(price.uuid, user.uuid, $event.target.value,'first_name')" required>
      <!-- <div class="invalid-tooltip me-4">Erreur, il manque une information svp</div> -->
        <button class="btn btn-primary mb-0" type="button" @click="deleteUser(price.uuid, user.uuid)" style="border-top-right-radius: 30px; border-bottom-right-radius: 30px;">
          <i class="fas fa-times"></i>
        </button>
      <div class="invalid-feedback">Donnée(s) manquante(s) !</div>
    </div>
    <!-- </div> -->

    <div v-if="price.users.length > 0 " class="d-flex justify-content-end mb-3">
      <h6>
        SOUS-TOTAL : {{ (price.users.length * price.prix) }}€
      </h6>
    </div>
  </fieldset>

</template>

<script setup>
console.log('-> CardBillet.vue')

// store
import {useStore} from '@/store'

// attributs/props
const props = defineProps({
  product: Object,
  indexMemo: String
})

let store = useStore()
// console.log('store.currentUuidEvent =', store.currentUuidEvent)

// mémorise par défaut
let record = true

let prix = {}

// mémorise le composant dans le store ou la variable globale window
try {
  if (props.indexMemo === '' || props.indexMemo === undefined) {
    throw new Error(`Erreur index memo vide !`)
  }
  if (props.indexMemo !== '') {
    // init de base pour la persistance de tous les composants "CardAdhesion" dans le store
    if (store.memoComposants['CardBillet'] === undefined) {
      store.memoComposants['CardBillet'] = {}
    }
    // init de l'instance de clef "props.indexMemo" = uuid évènement en cours
    if (store.memoComposants.CardBillet[props.indexMemo] === undefined) {
      // console.log('Mémorisation initiale')
      prix = initData(props.product.prices)
      store.memoComposants.CardBillet[props.indexMemo] = prix
      store.memoComposants.CardBillet[props.indexMemo]['initDate'] = new Date().toLocaleString()
    } else {
      // instance existante
      prix = store.memoComposants.CardBillet[props.indexMemo]
      // console.log('Mémorisation existante')
    }
  }
} catch (erreur) {
  record = false
  console.log('Mémorisation du composant impossible')
}

function createUuid() {
  let u = Date.now().toString(16) + Math.random().toString(16) + '0'.repeat(16);
  return [u.substr(0, 8), u.substr(8, 4), '4000-8' + u.substr(13, 3), u.substr(16, 12)].join('-');
}

function initData(data) {
  for (let i = 0; i < data.length; i++) {
    const tarif = data[i]
    tarif['users'] = []
  }
  // console.log('data =', JSON.stringify(data, null, 2))
  return data
}

function addUser(uuidTarif) {
  // console.log('-> fonc addUser, uuidTarif =', uuidTarif)
  const tarifs = prix.find(prod => prod.uuid === uuidTarif)
  console.log('tarifs =', JSON.stringify(tarifs, null, 2))

  // max products by user
  if (tarifs.users.length < tarifs.max_per_user) {
    tarifs.users.push({
      "first_name": "",
      "last_name": "",
      "uuid": createUuid()
    })
  } else {
    emitter.emit('modalMessage', {
      titre: 'Attention',
      contenu: `Nombre max de produits par client atteint !`
    })
  }

  // stock empty
  if (tarifs.users.length === tarifs.stock) {
    emitter.emit('modalMessage', {
      titre: 'Attention',
      contenu: `Produits arrivé en rupture de stock !`
    })
  }
}

function updateUser(uuidTarif, uuidUser, value, key) {
  // console.log('-> fonc updateUser, uuidTarif =', uuidTarif, '  --  uuidUser =', uuidUser)
  const tarif = prix.find(tarif => tarif.uuid === uuidTarif)
  const user = tarif.users.find(user => user.uuid === uuidUser)
  user[key] = value
}

function deleteUser(uuidTarif, uuidUser) {
  // console.log('-> fonc deleteUser, uuidTarif =', uuidTarif, '  --  uuidUser =', uuidUser)
  const tarif = prix.find(tarif => tarif.uuid === uuidTarif)
  const newUsers = tarif.users.filter(user => user.uuid !== uuidUser)
  tarif.users = newUsers
}
</script>

<style scoped>
</style>