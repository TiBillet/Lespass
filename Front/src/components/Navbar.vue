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
          <li v-if="store.place.button_adhesion === true && router.currentRoute.value.name === 'Accueil'"
              class="nav-item px-3">
            <button class="btn bg-gradient-info mb-0" data-bs-toggle="modal" data-bs-target="#modal-form-adhesion">
              <span class="btn-inner--icon"><i class="fa fa-ticket" aria-hidden="true"></i></span>
              <span class="btn-inner--text">Adhésion</span>
            </button>
          </li>
          <!-- déconnexion -->
          <li v-if="connection === true" class="nav-item text-success d-flex flex-row align-items-center">
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
</template>

<script setup>
console.log('-> Navbar.vue')
// composants
import Modallogin from './Modallogin.vue'

// vue
import {ref} from 'vue'
import {useRouter} from 'vue-router'
// commun
import {refreshAccessToken} from '@/api'
// store
import {useStore} from '@/store'
// myStore
import {StoreLocal} from '@/divers'

const router = useRouter()
const store = useStore()
let storeLocal = StoreLocal.use('localStorage', 'Tibilet-identite')
const props = defineProps({
  place: Object
})
const domain = `${location.protocol}//${location.host}`

let connection = ref(false)
if (storeLocal.refreshToken !== '') {
  connection.value = true
}

// actualiser le accessToken
if (storeLocal.refreshToken !== '' && window.accessToken === '') {
  refreshAccessToken(storeLocal.refreshToken)
}

// si pas d'image
const getLogo = () => {
  if (props.place.logo_variations === undefined) {
    return `${domain}/media/images/image_non_disponible.svg`
  } else {
    if (props.place.logo_variations.med === undefined) {
      return `${domain}/media/images/image_non_disponible.svg`
    }
  }
  return `${domain + props.place.logo_variations.med}`
}

emitter.on('statusConnection', (data) => {
  // console.log('réception de "statusConnection", data =', data)
  connection.value = data
})

</script>

<style scoped>
.taille-navbar {
  height: 72px;
}
</style>