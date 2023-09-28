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
      <ul class="navbar-nav d-flex flex-row-reverse ms-auto d-block">
        <!-- user connecté -->
        <li v-if="accessToken !== ''" class="nav-item dropdown">
          <a class="nav-link d-flex justify-content-between align-items-center dropdown-toggle me-1" href="#"
            id="menuUser" role="button" data-bs-toggle="dropdown" aria-expanded="false">
            <i class="fas fa-user me-1" aria-hidden="true"></i>
            <h6 class="m-0 text-white">Mon compte</h6>
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
                <i class="fa fa-ticket fa-fw me-1 text-dark tourne-ticket" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Réservations - {{ me.reservations.length }}</h6>
              </a>
              <a v-if="me.reservations.length === 0"
                class="dropdown-item border-radius-md d-flex justify-content-star align-items-center">
                <i class="fa fa-ticket fa-fw me-1 text-dark tourne-ticket" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Réservations - 0</h6>
              </a>

            </li>

            <!-- les adhésions prisent par le client -->
            <li>
              <a v-if="me.membership.length > 0"
                class="dropdown-item border-radius-md d-flex justify-content-star align-items-center" role="button"
                data-bs-toggle="modal" data-bs-target="#membership-owned-modal">
                <i class="fa fa-users fa-fw me-1 text-dark" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Adhésions - {{ me.membership.length }}</h6>
              </a>
              <a v-if="me.membership.length === 0"
                class="dropdown-item border-radius-md d-flex justify-content-star align-items-center">
                <i class="fa fa-users fa-fw me-1 text-dark" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Adhésions - 0</h6>
              </a>
            </li>

            <!-- déconnexion -->
            <li v-if="accessToken !== ''">
              <a class="dropdown-item border-radius-md d-flex justify-content-star align-items-center" role="button"
                @click="disconnect()">
                <i class="fa fa-sign-out fa-fw me-1 text-dark" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Deconnexion</h6>
              </a>
            </li>
          </ul>
        </li>

        <!-- pas de connexion -->
        <li v-else class="nav-item">
          <a class="nav-link ps-1 d-flex justify-content-between align-items-center" role="button"
            @click="showModalLogin()">
            <i class="fa fa-user-circle-o me-1 text-white" aria-hidden="true"></i>
            <h6 class="m-0 text-white" data-test-id="seConnecter">Se connecter</h6>
          </a>
        </li>

        <!-- Aller page adhésions -->
        <li v-if="!['M'].includes(headerPlace.categorie)" class="nav-item">
          <a v-if="routeName !== 'Adhesions' && headerPlace !== null" href="/adhesions"
            class="nav-link ps-1 d-flex justify-content-between align-items-center"
            :title="`Adhésions possibles à l'association '${headerPlace.titre}'`">
            <i class="fa fa-users me-1 text-white" aria-hidden="true"></i>
            <h6 class="m-0 text-white">Adhésions</h6>
          </a>
        </li>

        <li v-if="['M'].includes(headerPlace.categorie) && accessToken !== ''" class="nav-item">
          <router-link to="/tenant"
            class="nav-link ps-1 d-flex justify-content-between align-items-center cursor-pointer">
            <i class="fa fa-plane me-1 text-white" aria-hidden="true"></i>
            <h6 class="m-0 text-white" data-test-id="seConnecter">Créer son espace</h6>
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

if (getIsLogin) {
  automaticConnection()
}

</script>

<style scoped>
.tourne-ticket {
  transform: rotate(-20deg);
}
</style>