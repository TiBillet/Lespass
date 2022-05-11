<template>
  <p v-if="error">{{ error.message }}</p>
  <Loading v-if="loading === true"/>

  <h1>Navbar</h1>
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

const {email, refreshToken} = storeToRefs(useLocalStore())

// load place (infos pour Navbar)
getPlace()

</script>

<style scoped>
</style>