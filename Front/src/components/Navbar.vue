<template>
  <!-- Navbar -->
  <nav class="taille-navbar navbar navbar-expand-lg navbar-dark bg-gradient-dark z-index-3 py-3 fixed-top">
    <div class="container">
      <img :src="getLogo()" class="me-2"
           style="width: auto; height: 26px;">
      <router-link to="/" class="navbar-brand text-white">{{ place.organisation }}</router-link>
      <button class="navbar-toggler" type="button" data-toggle="collapse" data-target="#navigation"
              aria-controls="navigation" aria-expanded="false" aria-label="Toggle navigation">
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="navigation">
        <ul class="navbar-nav navbar-nav-hover mx-auto">
          <li v-if="router.currentRoute.value.name === 'Accueil'" class="nav-item px-3">
            <a href="#calendar" class="nav-link text-white opacity-8">
              Calendrier
            </a>
          </li>
        </ul>

        <ul class="navbar-nav ms-auto">
          <!-- adhésion -->
          <li v-if="store.place.button_adhesion === true && router.currentRoute.value.name === 'Accueil'" class="nav-item px-3">
            <button class="btn bg-gradient-info mb-0" data-bs-toggle="modal" data-bs-target="#modal-form-adhesion">
              <span class="btn-inner--icon"><i class="fa fa-ticket" aria-hidden="true"></i></span>
              <span class="btn-inner--text">Adhésion</span>
            </button>
          </li>
          <!-- déconnexion -->
          <li v-if="isConnected === true" class="nav-item text-success d-flex flex-row align-items-center">
            <i class="ni ni-world-2 m"></i>
            <span class="ms-1">Connecté</span>
          </li>
          <!-- connexion -->
          <li v-else>
            <button class="btn bg-gradient-info mb-0" data-bs-toggle="modal" data-bs-target="#modal-form-login">
              Connexion
            </button>
          </li>
        </ul>

      </div>
    </div>
  </nav>
  <!-- modal login -->
  <Modallogin/>
  <!-- adhésion -->
  <ModalAdhesion v-if="store.place.button_adhesion === true" :prices="prices" required/>

</template>

<script setup>
console.log('-> Navbar.vue')
// composants
import Modallogin from './Modallogin.vue'
import ModalAdhesion from './ModalAdhesion.vue'

// vue
import {ref, computed} from 'vue'
import {useRouter} from 'vue-router'
// commun
import {refreshAccessToken} from '@/api'
// store
import {useStore} from '@/store'

const router = useRouter()
const store = useStore()
const props = defineProps({
  place: Object
})
const domain = `${location.protocol}//${location.host}`


// actualiser le accessToken
if (store.user.refreshToken !== '' && window.accessToken === '') {
  refreshAccessToken(store.user.refreshToken)
}

let prices = []
if (store.place.button_adhesion === true) {
  try {
    prices = store.place.membership_products.filter(adh => adh.categorie_article === 'A')[0].prices
    console.log('prices =', prices)
  } catch (erreur) {
    emitter.emit('message', {
      tmp: 6,
      typeMsg: 'warning',
      contenu: `Avez-vous renseigné les prix pour l'adhésion ?`
    })
  }
}

// si pas d'image
const getLogo = () => {
  if (props.place.logo_variations.med === undefined) {
    return `${domain}/media/images/image_non_disponible.svg`
  }
  return `${domain + props.place.logo_variations.med}`
}

const isConnected = computed(() => {
  if (store.user.refreshToken !== '') {
    return true
  }
  return false
})
</script>

<style scoped>
.taille-navbar {
  height: 72px;
}
</style>