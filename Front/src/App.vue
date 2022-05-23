<template>
  <Navbar />
  <router-view/>
  <!--
  <Footer :place="place"/>
    -->
  <ModalMessage/>
  <!-- adhésion
  <ModalAdhesion v-if="place.button_adhesion === true"/> -->
  <ModalAdhesion />
</template>

<script setup>
// console.log(' -> App.vue !')

// composants
import Navbar from './components/Navbar.vue'
import ModalAdhesion from './components/ModalAdhesion.vue'
import ModalMessage from './components/ModalMessage.vue'

// store
import {storeToRefs} from 'pinia'
import {useAllStore} from '@/stores/all'

const {place} = storeToRefs(useAllStore())

/*
import Footer from './components/Footer.vue'
*/

</script>
<style>
</style>
