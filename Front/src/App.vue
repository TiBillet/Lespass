<template>
  <Loading v-if="loading" />
  <!-- en cours -->
  <Navbar v-if="identitySite && loadingPlace" />
  <Header v-if="identitySite && loadingPlace" />
  <router-view></router-view>
  <ModalMessage />
  <Modallogin />
  <ModalMembershipOwned />
  <ToastContainer />
  <ModalReservationList />
  <ModalOnboard />
  <!--
  <ModalPassword/>
  <ModalCardsList/>

  -->
</template>

<script setup>
console.log('-> App.vue')
import { ref } from 'vue'

import Plausible from 'plausible-tracker'

// composants
import Loading from "@/components/Loading.vue"
import Navbar from "@/components/Navbar.vue"
import Header from "@/components/Header.vue"
import ModalMessage from "@/components/ModalMessage.vue"
import Modallogin from "@/components/Modallogin.vue"
import ModalMembershipOwned from "@/components/ModalMembershipOwned.vue"
import ToastContainer from "./components/ToastContainer.vue"
import ModalReservationList from "@/components/ModalReservationList.vue"
import ModalOnboard from "@/components/ModalOnboard.vue"


// import ModalPassword from '@/components/ModalPassword.vue'
// import ModalCardsList from '@/components/ModalCardsList.vue'

// store
import { storeToRefs } from 'pinia'
import { useSessionStore } from '@/stores/session'

// font monserrat
import './assets/css/font_Montserrat_Open_Sans_Condensed.css'

// session store
const sessionStore = useSessionStore()
const { identitySite, loading } = storeToRefs(sessionStore)
const { loadPlace } = sessionStore
const loadingPlace = ref(false)

// gestion synchrone du chargement des informations du tenant/lieu/artist/...
async function waitLoadPlace() {
  loadingPlace.value = await loadPlace()
}

waitLoadPlace()

const plausible = Plausible({
  domain: `${window.location.protocol}//${window.location.host}`
})


</script>

<style>
/* ajout partie arrondie sur groupe input por l'ensemble de l'application 
.app-rounded-right-20 {
  border-bottom-right-radius: 20px !important;
  border-top-right-radius: 20px !important;
}

.w-15 {
  width: 15% !important;
}
*/

#app {
  --app-color-primary: #f05f3e;
}

.boutik-outline-primary {
  color: var(--app-color-primary) !important;
  border-color: #f05f3e !important;
}

.boutik-text-primary span {
  color: #f05f3e !important;
}

.boutik-bg-primary {
  background-color: #f05f3e !important;
}

.boutik-color-primary {
  color: #f05f3e !important;
}
</style>
