<template>
  <!-- Navbar -->
  <nav class="taille-navbar navbar navbar-expand-lg navbar-dark bg-gradient-dark z-index-3 py-3 fixed-top">
    <div class="container">
      <img :src="getLogo()" class="me-2"
           style="width: auto; height: 26px;">
      <router-link to="/" class="navbar-brand text-white">{{ store.place.titre }}</router-link>
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
          <li v-if="store.place.button_adhesion && router.currentRoute.value.name === 'Accueil'" class="nav-item px-3">
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
  <Adhesion v-if="store.place.button_adhesion === true" :adhesion="adhesion"/>

</template>

<script setup>
// console.log('-> Navbar.vue')
// composants
import Modallogin from './Modallogin.vue'
import Adhesion from './Adhesion.vue'

// vue
import {ref,computed} from 'vue'
import {useRouter} from 'vue-router'
// commun
import {refreshAccessToken} from '@/common'
// store
import {useStore} from '@/store'

const router = useRouter()
const store = useStore()
const props = defineProps({
  place: Object
})

console.log('place =', props.place)

// actualiser le accessToken
if (store.user.refreshToken !== '' && window.accessToken === '') {
  refreshAccessToken(store.user.refreshToken)
}

// l'adhésion
const adhesion = {
  form: false,
  nom: store.user.nom,
  prenom: store.user.prenom,
  adresse: store.user.adresse,
  tel: store.user.tel,
  uuidEvent: 'dummy',
  adhesion: store.user.adhesion,
  uuidPrice: store.user.uuidPrice,
}

// si pas d'image
const getLogo = () => {
  // console.log('-> getLogo, props.dataHeader.logo =', props.dataHeader.logo)
  if (props.place.logo !== undefined) {
    return `${props.place.domain + props.place.logo}`
  }
  return `${props.place.domain}/media/images/image_non_disponible.svg`
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