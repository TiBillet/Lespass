<template>
  <Navbar :place="store.place"/>
  <div class="espace-navbar"></div>
  <router-view/>
  <Footer :place="store.place"/>
  <Message/>
  <ModalMessage/>
</template>

<script setup>
// bootstrap (ui)
import './assets/js/core/popper.min.js'
import './assets/js/core/bootstrap.bundle.min.js'
// en attente (erreur t n'est pas défini)
import './assets/js/plugins/perfect-scrollbar.js'
import './assets/js/now-design-system-pro.js'

// Nucleo Icons (ui)
import './assets/css/nucleo-icons.css'
import './assets/css/nucleo-svg.css'

// css (ui)
import './assets/css/now-design-system-pro.min.css'

// composants
import Navbar from './components/Navbar.vue'
import Footer from './components/Footer.vue'
import Message from './components/Message.vue'
import ModalMessage from './components/ModalMessage.vue'

// store
import {useStore} from '@/store'

const store = useStore()

</script>
<style>
.espace-navbar {
  margin-bottom: 72px;
}
</style>
