<template>
  <Navbar/>
  <Header/>
  <p v-if="error !== null" class="text-dark">{{ error }}</p>
  <Loading v-if="loading === true"/>
  <div>
    <slot/>
  </div>
  <!--
  <Footer :place="place"/>
    -->
  <ModalMessage/>
  <ModalAdhesion/>
  <Modallogin/>
</template>

<script setup>
// composants
import Loading from '@/components/Loading.vue'
import Navbar from '@/components/Navbar.vue'
import Header from '@/components/Header.vue'
import ModalAdhesion from '@/components/ModalAdhesion.vue'
import ModalMessage from '@/components/ModalMessage.vue'
import Modallogin from '@/components/Modallogin.vue'
// import Footer from '@/components/Footer.vue'

// store
import {storeToRefs} from 'pinia'
import {useAllStore} from '@/stores/all'

// console.log('dataHeader =', dataHeader)
const {loading, error} = storeToRefs(useAllStore())
</script>

<style scoped>
</style>