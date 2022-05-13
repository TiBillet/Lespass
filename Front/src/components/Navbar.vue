<template>
  <!-- pour load place -->
  <p v-if="error !== null" class="text-dark">{{ error }}</p>
  <Loading v-if="loading === true"/>
  <!-- Navbar -->
  <nav v-else class="navbar navbar-expand-lg z-index-3 w-100 navbar-transparent blur blur-light fixed-top">
    <div class="container">
      <div class="navbar-brand">
        <router-link to="/" class="navbar-brand font-weight-bolder text-white">{{ place.organisation }}</router-link>
      </div>

      <button class="navbar-toggler shadow-none ms-2" type="button" data-bs-toggle="collapse"
              data-bs-target="#navigation" aria-controls="navigation" aria-expanded="true"
              aria-label="Toggle navigation">
        <span class="navbar-toggler-icon mt-2">
          <span class="navbar-toggler-bar bar1"></span>
          <span class="navbar-toggler-bar bar2"></span>
          <span class="navbar-toggler-bar bar3"></span>
        </span>
      </button>

      <div class="navbar-collapse w-100 pt-3 pb-2 py-lg-0 collapse show" id="navigation" style="">
        <ul class="navbar-nav navbar-nav-hover mx-auto">

          <!-- adhésion -->
          <li v-if="place.button_adhesion === true && router.currentRoute.value.name === 'Accueil' && membership === false"
              class="nav-item mx-2">
            <a class="btn bg-gradient-primary btn-icon me-2" role="button"
               data-bs-toggle="modal" data-bs-target="#modal-form-adhesion">
              <i class="fas fa-address-card me-1" aria-hidden="true"></i>
              Adhérez à l'association '{{ place.organisation }}'
            </a>
          </li>


        </ul>
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

// routes
import {useRouter} from 'vue-router'

const {place, loading, error} = storeToRefs(useAllStore())
const {getPlace} = useAllStore()
const {email, refreshToken, membership} = storeToRefs(useLocalStore())
const router = useRouter()

// load place
getPlace()

</script>

<style scoped>
</style>