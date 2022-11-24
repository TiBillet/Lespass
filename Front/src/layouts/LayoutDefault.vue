<template>
  <Loading v-if="loading"/>
  <Navbar v-if="identitySite"/>
  <Header v-if="identitySite"/>
  <p v-if="error !== null" class="text-dark">{{ error }}</p>
  <div>
    <slot/>
  </div>
  <!--
  <Footer :place="place"/>
    -->
  <ModalMessage/>
  <Modallogin/>
  <ModalPassword/>
  <ModalMembershipOwned/>
  <ModalCardsList/>
  <ModalReservationList/>
  <ModalOnboard/>
</template>

<script setup>
// composants
import Loading from '@/components/Loading.vue'
import Navbar from '@/components/Navbar.vue'
import Header from '@/components/Header.vue'
import ModalMessage from '@/components/ModalMessage.vue'
import Modallogin from '@/components/Modallogin.vue'
import ModalPassword from '@/components/ModalPassword.vue'
import ModalMembershipOwned from '@/components/ModalMembershipOwned.vue'
import ModalCardsList from "@/components/ModalCardsList.vue"
import ModalReservationList from "@/components/ModalReservationList.vue"
import ModalOnboard from "@/components/ModalOnboard.vue"
// import Footer from '@/components/Footer.vue'

// store
import {storeToRefs} from 'pinia'
import {useAllStore} from '@/stores/all'

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

// console.log('dataHeader =', dataHeader)
const {identitySite, loading, error} = storeToRefs(useAllStore())
</script>
<style></style>