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
      <!-- <div class="d-flex justify-content-between d-block ms-auto"> -->
      <ul class="navbar-nav d-flex flex-row-reverse ms-auto d-block">
        <!-- bouton user -->
        <li v-if="adhesion.status === 'membership' || refreshToken !== ''" class="nav-item dropdown">
          <a class="nav-link d-flex justify-content-between align-items-center dropdown-toggle" href="#" id="menuUser"
             role="button" data-bs-toggle="dropdown" aria-expanded="false">
            <i class="fas fa-user me-1" aria-hidden="true"></i>
            <h6 class="m-0 text-white">User</h6>
          </a>
          <!-- menu user -->
          <ul class="dropdown-menu" aria-labelledby="menuUser">
            <!-- déconnexion -->
            <li>
              <a class="dropdown-item py-2 ps-3 border-radius-md d-flex justify-content-star align-items-center"
                 role="button" @click="disconnect()">
                <i class="fa fa-sign-out text-dark" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Deconnexion</h6>
              </a>
            </li>
            <!-- assets -->
            <li v-if="me.cashless.cards !== undefined">
              <a class="dropdown-item py-2 ps-3 border-radius-md d-flex justify-content-star align-items-center"
                 role="button" @click="showAssets()">
                <i class="fas fa-address-card fa-fw me-1 text-dark" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Carte</h6>
              </a>
            </li>
            <!-- infos adhésion -->
            <li v-if="adhesion.status === 'membership'">
              <a class="dropdown-item py-2 ps-3 border-radius-md d-flex justify-content-star align-items-center"
                 role="button" @click="showAdhesion()">
                <i class="fas fa-address-card fa-fw me-1 text-dark" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Adhésion</h6>
              </a>
            </li>

          </ul>
        </li>

        <!-- pas de connexion -->
        <li class="nav-item">
          <a v-if="refreshToken === ''" class="nav-link ps-1 d-flex justify-content-between align-items-center"
             role="button"
             data-bs-toggle="modal" data-bs-target="#modal-form-login">
            <i class="fa fa-user-circle-o me-1 text-white" aria-hidden="true"></i>
            <h6 class="m-0 text-white">Se connecter</h6>
          </a>
        </li>

        <!-- pas d'adhésion -->
        <li class="nav-item">
          <a v-if="adhesion.status === ''" class="nav-link ps-1 d-flex justify-content-between align-items-center"
             :title="`Adhérez à l'association '${ place.organisation }'`"
             role="button" data-bs-toggle="modal" data-bs-target="#modal-form-adhesion">
            <i class="fa fa-address-card me-1 text-white" aria-hidden="true"></i>
            <h6 class="m-0 text-white">Adhérez</h6>
          </a>
        </li>

      </ul>


    </div>
  </nav>
  <!-- modal login -->
  <Modallogin/>
</template>

<script setup>
// console.log(' -> Navbar.vue !')

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
import Modallogin from '@/components/Modallogin.vue'

// store
import {storeToRefs} from 'pinia'
import {useAllStore} from '@/stores/all'
import {useLocalStore} from '@/stores/local'

const {place, loading, error} = storeToRefs(useAllStore())
const {getPlace} = useAllStore()
const {refreshToken, me, adhesion} = storeToRefs(useLocalStore())

// load place
getPlace()

function disconnect() {
  refreshToken.value = ''
  me.value = {}
  adhesion.value = {
    email: '',
    first_name: '',
    last_name: '',
    phone: null,
    postal_code: null,
    adhesion: '',
    status: ''
  }
}

function showAdhesion() {
  emitter.emit('modalMessage', {
    titre: 'Adhesion',
    dynamique: true,
    contenu: `
      <h3>Email : ${adhesion.value.email}</h3>
      <h3>Nom : ${adhesion.value.lastName}</h3>
      <h3>Prenom : ${adhesion.value.firstName}</h3>
      <h3>Inscription : ${adhesion.value.inscription}</h3>
      <h3>Echéance : ${adhesion.value.echeance}</h3>
    `
  })
}


function showAssets() {
  let contenu = `<h3>En travaux !</h3>`
 /*
  const monnaies = profil.value.assets
  let contenu = `<h3>Numéro de carte : ${profil.value.numberCahslessCard}</h3>`
  for (let i = 0; i < monnaies.length; i++) {
    const monnaie = monnaies[i]
    console.log('monnaie =', monnaie)
    // <i class="fas fa-gift"></i>
    if (monnaie.monnaie_name.toLowerCase().indexOf('cadeau') !== -1) {
      contenu += `<h3>${monnaie.monnaie_name.split(' ')[0]}<i class="fas fa-gift ms-1"></i> = ${monnaie.qty}</h3>`
    } else {
      contenu += `<h3>${monnaie.monnaie_name} = ${monnaie.qty}</h3>`
    }
  }

  */
  emitter.emit('modalMessage', {
    titre: 'Monnaies',
    dynamique: true,
    contenu: contenu
  })

}

// menu transparant / non transparant
window.addEventListener("scroll", (event) => {
  if (scrollY === 0) {
    document.querySelector('#navbar').style.backgroundColor = ''
  } else {
    document.querySelector('#navbar').style.backgroundColor = '#384663'
  }
})

</script>

<style>
</style>