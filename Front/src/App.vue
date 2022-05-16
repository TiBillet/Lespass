<template>
  <Navbar />
  <router-view/>
  <!--
  <Footer :place="place"/>
  <Message/>
  <ModalMessage/>
  -->
  <!-- adhésion -->
  <ModalAdhesion v-if="place.button_adhesion === true"/>
</template>

<script setup>
console.log(' -> App.vue !')

// composants
import Navbar from './components/Navbar.vue'
import ModalAdhesion from './components/ModalAdhesion.vue'

// store
import {storeToRefs} from 'pinia'
import {useAllStore} from '@/stores/all'

const {place} = storeToRefs(useAllStore())

/*
import Footer from './components/Footer.vue'
import Message from './components/Message.vue'
import ModalMessage from './components/ModalMessage.vue'
*/


/*
// vue
import {ref} from 'vue'

// store
import {useStore} from '@/store'

// myStore
// import {StoreLocal} from '@/storelocal'
import {storeLocalInit} from '@/storelocal'

const store = useStore()

// init store local
storeLocalInit()


const loading = ref(false)

// console.log('-> App.vue, storeLocal.state =', storeLocal.state())
// console.log('-> App.vue, storeLocal =', storeLocal.state)

// aller à la page évènement (lien défini si-dessous et dans le store) => /views/Event.vue
emitter.on('statusLoading', (status) => {
  // console.log('-> Emmiter, réception "statusLoading"; status')
  loading.value = status
})
*/
</script>
<style>
</style>
