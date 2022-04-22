<template>
  <Navbar :place="store.place"/>
  <router-view/>
  <Footer :place="store.place"/>
  <Message/>
  <ModalMessage/>
  <!-- adhésion -->
  <ModalAdhesion v-if="store.place.button_adhesion === true" :prices="prices" required/>

  <!-- loading -->
  <div v-if="loading === true" class="position-relative d-flex justify-content-center align-items-center vw-100 vh-100">
    <h1>Chargement des données !</h1>
    <div class="position-absolute d-flex justify-content-center align-items-center vw-100 vh-100">
      <div class="spinner-border text-success" role="status" style="width: 10rem; height: 10rem;"></div>
    </div>
  </div>
</template>

<script setup>
console.log(' -> App.vue !')
// vue
import {ref} from 'vue'

// composants
import Navbar from './components/Navbar.vue'
import Footer from './components/Footer.vue'
import Message from './components/Message.vue'
import ModalMessage from './components/ModalMessage.vue'
import ModalAdhesion from './components/ModalAdhesion.vue'

// store
import {useStore} from '@/store'

// myStore
import {StoreLocal} from '@/divers'

const store = useStore()
// init store local
const storeLocal = new StoreLocal('localStorage', 'Tibilet-identite', {
  email: '',
  refreshToken: '',
  storeBeforeUseExternalUrl: {}
})

let prices = []
console.log('store.place =', store.place)

// console.log('store =., storeplace.membership_products =', store.place.membership_products)
if (store.place.button_adhesion === true) {
  try {
    prices = store.place.membership_products.filter(adh => adh.categorie_article === 'A')[0].prices
    // console.log('prices =', prices)
  } catch (erreur) {
    emitter.emit('message', {
      tmp: 6,
      typeMsg: 'warning',
      contenu: `Avez-vous renseigné les prix pour l'adhésion ?`
    })
  }
}

const loading = ref(false)

// console.log('-> App.vue, storeLocal.state =', storeLocal.state())
// console.log('-> App.vue, storeLocal =', storeLocal.state)

// aller à la page évènement (lien défini si-dessous et dans le store) => /views/Event.vue
emitter.on('statusLoading', (status) => {
  // console.log('-> Emmiter, réception "statusLoading"; status')
  loading.value = status
})

</script>
<style>
</style>
