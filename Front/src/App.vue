<template>
  <Message/>
  <Navbar :data-header="getDataHeader()"/>
  <router-view></router-view>
  <Footer :data-header="getDataHeader()"/>
</template>

<script setup>
// vue
import Message from './components/Message.vue'
import {useStore} from 'vuex'

// composants
import Navbar from './components/Navbar.vue'
import Footer from './components/Footer.vue'

const store = useStore()

function getDataHeader() {
  return {
    urlImage: store.state.place.img_variations.med,
    shortDescription: store.state.place.short_description,
    longDescription: store.state.place.long_description,
    logo: store.state.place.logo_variations.med,
    titre: store.state.place.organisation,
    domain: `${location.protocol}//${location.host}`
  }
}

</script>

<style>
</style>
