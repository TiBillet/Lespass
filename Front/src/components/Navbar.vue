<template>
  <!-- pour load place -->
  <p v-if="error !== null" class="text-dark">{{ error }}</p>
  <Loading v-if="loading === true" test="accueil"/>
  <!-- Navbar router.currentRoute.value.name -->
  <nav id="navbar" v-else class="navbar navbar-expand-lg z-index-3 w-100 navbar-transparent position-fixed">
    <div class="container">
      <!-- lieu -->
      <div class="navbar-brand">
        <router-link to="/" class="navbar-brand d-flex justify-content-between align-items-center">
          <h6 class="m-0 text-white">{{ place.organisation }}</h6>
        </router-link>
      </div>

      <!-- partie droite -->
      <div class="d-flex justify-content-between d-block ms-auto">
        <!-- pas d'adhésion -->
        <a v-if="adhesion.status === ''" class="nav-link ps-1 cursor-pointer"
           :title="`Adhérez à l'association '${ place.organisation }'`"
           role="button" data-bs-toggle="modal" data-bs-target="#modal-form-adhesion">
          <div class="d-flex justify-content-between align-items-center">
            <i class="fa fa-address-card me-1 text-white" aria-hidden="true"></i>
            <h6 class="m-0 text-white">Adhérez</h6>
          </div>
        </a>

        <!-- pas de connexion -->
        <a v-if="refreshToken === ''" class="nav-link ps-1  cursor-pointer">
          <div class="d-flex justify-content-between align-items-center">
            <i class="fa fa-user-circle-o me-1 text-white" aria-hidden="true"></i>
            <h6 class="m-0 text-white">Se connecter</h6>
          </div>
        </a>
      </div>

    </div>
  </nav>
</template>

<script setup>
console.log(' -> Navbar.vue !')

import '../assets/css/google_fonts_family_montserrat_400.700.200.css'

// Nucleo Icons (ui)
import '../assets/css/nucleo-icons.css'

// Font Awesome Free 5.15.4 MIT License
import '../assets/js/kit-fontawesome-42d5adcbca.js'

// bootstrap (ui)
import '../assets/css/bootstrap-5.0.2/bootstrap.min.css'
import '../assets/js/bootstrap-5.0.2/bootstrap.bundle.min.js'

// perfect-scrollbar
import '../assets/css/perfect-scrollbar.css'
import '../assets/js/perfect-scrollbar/perfect-scrollbar.min.js'

// css (ui)
import '../assets/css/now-design-system-pro.min.css'
import '../assets/js/now-design-system-pro.js'

// composants
import Loading from '@/components/Loading.vue'

// store
import {storeToRefs} from 'pinia'
import {useAllStore} from '@/stores/all'
import {useLocalStore} from '@/stores/local'

const {place, loading, error} = storeToRefs(useAllStore())
const {getPlace} = useAllStore()
const {email, refreshToken, adhesion} = storeToRefs(useLocalStore())

// load place
getPlace()

window.addEventListener("scroll", (event) => {
  if (scrollY === 0) {
    document.querySelector('#navbar').style.backgroundColor = ''
  } else {
    document.querySelector('#navbar').style.backgroundColor = '#384663'
  }
    console.log('scrollY =', scrollY)
})

</script>

<style>
</style>