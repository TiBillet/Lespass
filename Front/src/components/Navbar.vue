<template>
  <!-- Navbar Dark -->
  <nav class="navbar navbar-expand-lg navbar-dark bg-gradient-dark z-index-3 py-3 fixed-top">
    <div class="container">
      <img :src="getLogo()" class="me-2"
           style="width: auto; height: 26px;">
      <router-link to="/" class="navbar-brand text-white">{{ dataHeader.titre }}</router-link>
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
        <!-- déconnexion -->
        <ul v-if="etatConnexion !== ''" class="navbar-nav ms-auto">
          <li class="nav-item text-success d-flex flex-row align-items-center">
            <i class="ni ni-world-2 m"></i>
            <span class="ms-1">Connecté</span>
          </li>
        </ul>
        <!-- connexion -->
        <ul  v-if="etatConnexion === ''" class="navbar-nav ms-auto">
          <li>
            <button class="btn bg-gradient-info mb-0" data-bs-toggle="modal" data-bs-target="#modal-form-login">
              Connexion
            </button>
          </li>
        </ul>

      </div>
    </div>
  </nav>
  <!-- End Navbar -->

  <Modallogin/>
</template>

<script setup>
console.log('-> Navbar.vue')
// composants
import Modallogin from './Modallogin.vue'

// vue
import {ref} from 'vue'
import {useRouter} from 'vue-router'
import {useStore} from 'vuex'

const router = useRouter()
const store = useStore()
const props = defineProps({
  dataHeader: Object
})

const etatConnexion = ref(store.state.refreshToken)

// si pas d'image
const getLogo = () => {
  // console.log('-> getLogo, props.dataHeader.logo =', props.dataHeader.logo)
  if (props.dataHeader.logo !== undefined) {
    return `${props.dataHeader.domain + props.dataHeader.logo}`
  }
  return `${props.dataHeader.domain}/media/images/image_non_disponible.svg`
}

emitter.on('majNavBar', () => {
  console.log('-> emitter écoute "majNavBar" !')
  etatConnexion.value = store.state.refreshToken
})

</script>
