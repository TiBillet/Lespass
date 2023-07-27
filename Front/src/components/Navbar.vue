<template>
  <nav id="navbar" class="navbar navbar-expand-lg z-index-3 w-100 navbar-transparent position-fixed">
    <div class="container">
      <!-- lieu -->
      <div v-if="getHeader !== null" class="navbar-brand">
        <a href="/" class="navbar-brand d-flex justify-content-between align-items-center">
          <h6 v-if="getHeader.categorie !== 'M'" class="m-0 text-white" data-bs-toggle="tooltip"
              data-bs-placement="bottom"
              title="Actualise les données évènements et lieu !">{{ getHeader.titre }}</h6>
          <h6 v-else class="m-0 text-white" data-bs-toggle="tooltip" data-bs-placement="bottom"
              title="Actualise les données évènements et lieu !">Agenda TiBillet</h6>
        </a>
      </div>
      <!-- partie droite -->
      <ul class="navbar-nav d-flex flex-row-reverse ms-auto d-block">
        <!-- menu user -->
        <li v-if="getRefreshToken !== ''" class="nav-item dropdown">
          <a class="nav-link d-flex justify-content-between align-items-center dropdown-toggle me-1" href="#"
             id="menuUser"
             role="button" data-bs-toggle="dropdown" aria-expanded="false">
            <i class="fas fa-user me-1" aria-hidden="true"></i>
            <h6 class="m-0 text-white">Mon compte</h6>
          </a>
          <!-- sous menu user -->
          <ul class="dropdown-menu" aria-labelledby="menuUser">
            <li class="dropdown-item border-radius-md d-flex justify-content-star align-items-center"
                style="cursor: default">
              {{ getEmail }}
            </li>
          </ul>
        </li>

        <!-- pas de connexion -->
        <li class="nav-item">
          <a v-if="getRefreshToken === ''" class="nav-link ps-1 d-flex justify-content-between align-items-center"
             role="button"
             data-bs-toggle="modal" data-bs-target="#modal-form-login">
            <i class="fa fa-user-circle-o me-1 text-white" aria-hidden="true"></i>
            <h6 class="m-0 text-white" data-test-id="seConnecter">Se connecter</h6>
          </a>
        </li>

        <!-- adhésions -->
        <li class="nav-item">
          <a v-if="routeName !== 'Adhesions'" href="/adhesions"
             class="nav-link ps-1 d-flex justify-content-between align-items-center"
             :title="`Adhésions possibles à l'association '${ getHeader.titre }'`">
            <i class="fa fa-users me-1 text-white" aria-hidden="true"></i>
            <h6 class="m-0 text-white">Adhésions</h6>
          </a>
        </li>
      </ul>
      <!--
      //-- partie droite --
      <ul v-if="place.categorie !== 'M'" class="navbar-nav d-flex flex-row-reverse ms-auto d-block">
        //-- user --
        //-- <li v-if="adhesion.status === 'membership' || refreshToken !== ''" class="nav-item dropdown"> --
        <li v-if="refreshToken !== ''" class="nav-item dropdown">
          <a class="nav-link d-flex justify-content-between align-items-center dropdown-toggle me-1" href="#"
             id="menuUser"
             role="button" data-bs-toggle="dropdown" aria-expanded="false">
            <i class="fas fa-user me-1" aria-hidden="true"></i>
            <h6 class="m-0 text-white">Mon compte</h6>
          </a>
          //-- menu user --
          <ul class="dropdown-menu" aria-labelledby="menuUser">
            <li class="dropdown-item border-radius-md d-flex justify-content-star align-items-center"
                style="cursor: default">
              {{ email }}
            </li>
            //-- Cartes cashless --
            <li v-if="infosCardExist() === true">
              <a class="dropdown-item border-radius-md d-flex justify-content-star align-items-center"
                 role="button" data-bs-toggle="modal" data-bs-target="#cards-list-modal">
                <i class="fa fa-id-card-o fa-fw me-1 text-dark" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Carte</h6>
              </a>
            </li>
            //-- réservations --
            <li v-if="infosReservationExist() === true">
              <a class="dropdown-item border-radius-md d-flex justify-content-star align-items-center"
                 role="button" data-bs-toggle="modal" data-bs-target="#reservation-list-modal">
                <i class="fa fa-ticket fa-fw me-1 text-dark tourne-ticket" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Réservations</h6>
              </a>
            </li>

            //-- les adhésions du client --
            <li>
              <a class="dropdown-item border-radius-md d-flex justify-content-star align-items-center"
                 role="button" data-bs-toggle="modal" data-bs-target="#membership-owned-modal">
                <i class="fa fa-users fa-fw me-1 text-dark" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Adhésions</h6>
              </a>
            </li>

            //-- isStaff --
            <li v-if="isStaff() === true">
              <a v-if="asP() === true"
                 class="dropdown-item border-radius-md d-flex justify-content-star align-items-center"
                 role="button" href="/admin">
                <i class="fa fa-cog fa-fw me-1 text-dark tourne-ticket" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Administration</h6>
              </a>
              <a v-else class="dropdown-item border-radius-md d-flex justify-content-star align-items-center"
                 role="button" data-bs-toggle="modal" data-bs-target="#set-password-modal">
                <i class="fa fa-cog fa-fw me-1 text-dark tourne-ticket" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Administration</h6>
              </a>
            </li>

            //-- déconnexion --
            <li v-if="refreshToken !== ''">
              <a class="dropdown-item border-radius-md d-flex justify-content-star align-items-center"
                 role="button" @click="disconnect()">
                <i class="fa fa-sign-out fa-fw me-1 text-dark" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Deconnexion</h6>
              </a>
            </li>

          </ul>
        </li>

        //-- pas de connexion --
        <li class="nav-item">
          <a v-if="refreshToken === ''" class="nav-link ps-1 d-flex justify-content-between align-items-center"
             role="button"
             data-bs-toggle="modal" data-bs-target="#modal-form-login">
            <i class="fa fa-user-circle-o me-1 text-white" aria-hidden="true"></i>
            <h6 class="m-0 text-white" data-test-id="seConnecter">Se connecter</h6>
          </a>
        </li>

        //-- adhésions --
        <li class="nav-item">
          <a v-if="routeName !== 'Adhesions'" href="/adhesions"
             class="nav-link ps-1 d-flex justify-content-between align-items-center"
             :title="`Adhésions possibles à l'association '${ place.organisation }'`">
            <i class="fa fa-users me-1 text-white" aria-hidden="true"></i>
            <h6 class="m-0 text-white">Adhésions</h6>
          </a>
        </li>

      </ul>

      <ul v-else class="navbar-nav d-flex flex-row-reverse ms-auto d-block">
        <li class="nav-item">
          <a class="nav-link ps-1 d-flex justify-content-between align-items-center"
             role="button"
             data-bs-toggle="modal" data-bs-target="#modal-onboard">
            <i class="fa fa-plane me-1 text-white" aria-hidden="true"></i>
            <h6 class="m-0 text-white" data-test-id="seConnecter">Créer son espace</h6>
          </a>
        </li>
      </ul>
      -->
    </div>
  </nav>
</template>

<script setup>
console.log(' -> Navbar.vue !')
import { useSessionStore } from '@/stores/session'
import { useLocalStore } from '@/stores/local'

// action
const { getHeader } = useSessionStore()
const { getEmail, getRefreshToken } = useLocalStore()

/*
//vue
import { ref } from 'vue'

// store
import { storeToRefs } from 'pinia'
import { useAllStore } from '@/stores/all'
import { useLocalStore } from '@/stores/local'

const { place, events, adhesion, routeName, loading, error } = storeToRefs(useAllStore())
const { getPlace, setHeaderPlace } = useAllStore()
const { refreshToken, email, me } = storeToRefs(useLocalStore())
const { infosCardExist, infosReservationExist, getMe, refreshAccessToken, isStaff, asP } = useLocalStore()

// load place
getPlace()

if (window.accessToken === '' && refreshToken.value !== '') {
  updateAccessToken()
}

async function updateAccessToken () {
  // console.log('-> fonc updateAccessToken !')
  loading.value = true
  await refreshAccessToken(refreshToken.value)
  loading.value = false
}

function disconnect () {
  refreshToken.value = ''
  me.value = {
    cashless: {},
    reservations: [],
    membership: []
  }
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

// menu transparant / non transparant
window.addEventListener('scroll', () => {
  if (document.querySelector('#navbar') !== null) {
    if (scrollY === 0) {
      document.querySelector('#navbar').style.backgroundColor = ''
    } else {
      document.querySelector('#navbar').style.backgroundColor = '#384663'
    }
  }
})
*/
</script>

<style scoped>
.tourne-ticket {
  transform: rotate(-20deg);
}
</style>