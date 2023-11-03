<template>
  <nav v-if="headerPlace !== null" id="navbar" class="navbar navbar-expand-lg bg-dark opacity-8 w-100 fixed-top">
    <div class="container">
      <!-- lieu -->
      <div class="navbar-brand opacity-10">
        <a href="/" class="navbar-brand d-flex justify-content-between align-items-center">
          <h6 class="m-0 text-white" data-bs-toggle="tooltip" data-bs-placement="bottom"
            title="Actualise les données évènements et lieu !">{{ getTitle(headerPlace) }}</h6>
        </a>
      </div>
      <!-- partie droite -->
      <ul class="navbar-nav d-flex flex-row-reverse ms-auto">
        <!-- user connecté -->
        <li v-if="accessToken !== ''" class="nav-item dropdown">
          <a class="nav-link d-flex flex-row justify-content-between align-items-center dropdown-toggle" href="#"
            id="menuUser" role="button" data-bs-toggle="dropdown" aria-expanded="false">
            <font-awesome-icon icon="fa-solid fa-user" class="text-white mb-1" />
            <h6 class="ms-1 m-0 text-white">Mon compte</h6>
          </a>

          <!-- sous menu user -->
          <ul class="dropdown-menu" aria-labelledby="menuUser">
            <!-- info email user connecté -->
            <li class="dropdown-item border-radius-md d-flex justify-content-star align-items-center"
              style="cursor: default">
              {{ me.email }}
            </li>
            <!-- les réservations  prisent par le client -->
            <li>
              <a v-if="me.reservations.length > 0"
                class="dropdown-item border-radius-md d-flex justify-content-star align-items-center" role="button"
                @click="showModal('reservation-list-modal')">
                <font-awesome-icon icon="fa-solid fa-ticket" class="text-dark mb-1" />
                <h6 class="ms-1 m-0 text-dark">Réservations - {{ me.reservations.length }}</h6>
              </a>
              <a v-if="me.reservations.length === 0"
                class="dropdown-item border-radius-md d-flex justify-content-star align-items-center">
                <font-awesome-icon icon="fa-solid fa-ticket" class="text-dark mb-1" />
                <h6 class="ms-1 m-0 text-dark">Réservations - 0</h6>
              </a>

            </li>

            <!-- les adhésions prisent par le client -->
            <li>
              <a v-if="me.membership.length > 0"
                class="dropdown-item border-radius-md d-flex justify-content-star align-items-center" role="button"
                data-bs-toggle="modal" data-bs-target="#membership-owned-modal">
                <font-awesome-icon icon="fa-solid fa-people-group" class="text-dark mb-1" />
                <h6 class="ms-1 m-0 text-dark">Adhésions - {{ me.membership.length }}</h6>
              </a>
              <a v-if="me.membership.length === 0"
                class="dropdown-item border-radius-md d-flex justify-content-star align-items-center">
                <font-awesome-icon icon="fa-solid fa-people-group" class="text-dark mb-1" />
                <h6 class="ms-1 m-0 text-dark">Adhésions - 0</h6>
              </a>
            </li>

            <!-- déconnexion -->
            <li v-if="accessToken !== ''">
              <a class="dropdown-item border-radius-md d-flex justify-content-star align-items-center" role="button"
                @click="disconnect()">
                <font-awesome-icon icon="fa-solid fa-right-from-bracket" class="text-dark mb-1" />
                <h6 class="ms-1 m-0 text-dark">Deconnexion</h6>
              </a>
            </li>
          </ul>
          <!-- fin sous menu user -->
        </li>

        <!-- pas de connexion -->
        <li v-else class="nav-item">
          <a class="nav-link d-flex flex-row justify-content-center align-items-center" role="button"
            @click="showModalLogin()">
            <font-awesome-icon icon="fa-solid fa-user" class="text-white mb-1" />
            <h6 class="ms-1 m-0 text-white" data-test-id="seConnecter">Se connecter</h6>
          </a>
        </li>

        <!-- Aller page adhésions -->
        <li v-if="!['M'].includes(headerPlace.categorie) && !['CreateEvent'].includes(routeName)" class="nav-item">
          <router-link to="/adhesions"
            class="nav-link d-flex flex-row justify-content-center align-items-center cursor-pointer">
            <font-awesome-icon icon="fa-solid fa-users" class="text-white mb-1" />
            <h6 class="ms-1 m-0 text-white">Adhésions</h6>
          </router-link>
        </li>

        <li v-if="['M'].includes(headerPlace.categorie)" class="nav-item">
          <router-link to="/tenant"
            class="nav-link d-flex flex-row justify-content-center align-items-center cursor-pointer">
            <font-awesome-icon icon="fa-solid fa-house-flag" class="text-white mb-1" />
            <h6 class="ms-1 m-0 text-white" data-test-id="seConnecter">Créer son espace</h6>
          </router-link>
        </li>
      </ul>
    </div>
  </nav>
</template>

<script setup>
// console.log(' -> Navbar.vue !')
import { storeToRefs } from 'pinia'
import { useSessionStore } from '@/stores/session'


const sessionStore = useSessionStore()
// reactif
const { headerPlace, routeName, accessToken, me } = storeToRefs(sessionStore)
// actions
const { getIsLogin, disconnect, getEmail, automaticConnection } = sessionStore

const titleException = [
  { categorie: 'M', title: "Agenda TiBillet" }
]

const getTitle = (headerPlace) => {
  const result = titleException.find(excep => excep.categorie === headerPlace.categorie)
  if (result === undefined) {
    return headerPlace.titre
  } else {
    return result.title
  }
}

function showModalLogin() {
  const elementModal = document.querySelector('#modal-form-login')
  const modal = bootstrap.Modal.getOrCreateInstance(elementModal) // Returns a Bootstrap modal instance
  // peuple l'email
  modal.show()
  document.querySelector('#login-email').value = getEmail
}

async function showModal(id) {
  const reservations = JSON.parse(JSON.stringify(me))._object.me.reservations
  console.log('reservations =', reservations)
  if (reservations.length > 0) {
    const elementModal = document.querySelector('#' + id)
    const modal = bootstrap.Modal.getOrCreateInstance(elementModal) // Returns a Bootstrap modal instance
    // peuple l'email
    modal.show()
  }

}

automaticConnection()
</script>

<style scoped>
ul[class~="dropdown-menu"]::before {
  content: '' !important;
}

.navbar .nav-link {
  padding: 0.5rem;
}

svg[class~="fa-ticket"] {
  transform: translateY(-2px) rotate(20deg);
}

.dropdown .dropdown-menu::before {
  content: "\f0d8";
  position: absolute;
  top: -20px;
  left: 28px;
  right: auto;
  font-size: 22px;
  color: #fff;
  transition: top .35s ease;
}
</style>