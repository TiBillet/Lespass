<template>
  <header v-if="header !== null">
    <div
        class="page-header min-vh-50" :style="{ backgroundImage: `url('${header.urlImage}')`, maxHeight: `365px` }">
      <span class="mask bg-dark opacity-8"></span>
      <div class="container">
        <div class="row">
          <div class="col-lg-8 mx-auto text-white text-center">
            <h2 class="text-white">{{ header.titre }}</h2>
            <p v-if="header.shortDescription !== null" class="lead" style="white-space: pre-line">
              {{ header.shortDescription }}</p>
          </div>
        </div>
      </div>
    </div>
    <!-- search -->
    <div v-if="routeName === 'Accueil'" class="container">
      <Search/>
    </div>

    <div class="container mt-5 mb-5" style="white-space: pre-line">{{ header.longDescription }}</div>

  </header>
</template>

<script setup>
// console.log('-> Header.vue')
import { storeToRefs } from 'pinia'
import { useSessionStore } from '@/stores/session'

// action
const sessionStore = useSessionStore()
const { header, routeName } = storeToRefs(sessionStore)

// components
import Search from '@/components/Search.vue'

</script>
