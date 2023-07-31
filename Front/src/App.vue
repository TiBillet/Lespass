<template>
  <Loading v-if="loading"/>
  <!-- en cours -->
  <Navbar v-if="identitySite && loadingPlace" />
  <Header v-if="identitySite && loadingPlace" />
  <router-view></router-view>
  <ModalMessage/>
  <Modallogin/>
  <!--
  <ModalMembershipOwned/>
  <ModalPassword/>
  <ModalCardsList/>
  <ModalReservationList/>
  <ModalOnboard/> -->
</template>

<script setup>
console.log('-> App.vue')
import { ref } from "vue"

// composants
import Loading from '@/components/Loading.vue'
import Navbar from '@/components/Navbar.vue'
import Header from '@/components/Header.vue'
import ModalMessage from '@/components/ModalMessage.vue'
import Modallogin from '@/components/Modallogin.vue'
/*
import ModalMembershipOwned from '@/components/ModalMembershipOwned.vue'
import ModalPassword from '@/components/ModalPassword.vue'
import ModalCardsList from '@/components/ModalCardsList.vue'
import ModalReservationList from '@/components/ModalReservationList.vue'
import ModalOnboard from '@/components/ModalOnboard.vue'
*/
// store
import { storeToRefs } from 'pinia'
import { useSessionStore } from '@/stores/session'
import { useLocalStore } from '@/stores/local'

// font monserrat
import '@/assets/css/font_Montserrat_Open_Sans_Condensed.css'

// Nucleo Icons (ui)
import '@/assets/css/nucleo-icons.css'

// Font Awesome Free 5.15.4 MIT License
import '@/assets/js/kit-fontawesome-42d5adcbca.js'

// bootstrap (ui)
import '@/assets/css/bootstrap-5.0.2/bootstrap.min.css'
import '@/assets/js/bootstrap-5.0.2/bootstrap.bundle.min.js'

// perfect-scrollbar
import '@/assets/css/perfect-scrollbar.css'
import '@/assets/js/perfect-scrollbar/perfect-scrollbar.min.js'

// css (ui)
import '@/assets/css/now-design-system-pro.min.css'
import '@/assets/js/now-design-system-pro.js'

// local store
const localStore = useLocalStore()
const { initLocalStore } = localStore
// pour créer le local store dans le cache
initLocalStore()

// session store
const sessionStore = useSessionStore()
const { identitySite, loading } = storeToRefs(sessionStore)
const { loadPlace } = sessionStore
const loadingPlace = ref(false)

async function waitLoadPlace() {
  loadingPlace.value = await loadPlace()
}
waitLoadPlace()
</script>
