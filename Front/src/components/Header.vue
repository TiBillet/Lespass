<template>
  <header v-if="getHeader !== null">
    <div
        class="page-header min-vh-50" :style="{ backgroundImage: `url('${getHeader.urlImage}')`, maxHeight: `365px` }">
      <span class="mask bg-dark opacity-8"></span>
      <div class="container">
        <div class="row">
          <div class="col-lg-8 mx-auto text-white text-center">
            <h2 class="text-white">{{ getHeader.titre }}</h2>
            <p v-if="getHeader.shortDescription !== null" class="lead" style="white-space: pre-line">
              {{ getHeader.shortDescription }}</p>
          </div>
        </div>
      </div>
    </div>
    <!-- search -->
    <div v-if="getRouteName === 'Accueil'" class="container">
      <Search/>
    </div>

    <div class="container mt-5 mb-5" style="white-space: pre-line">{{ getHeader.longDescription }}</div>

  </header>
</template>

<script setup>
// console.log('-> Header.vue')
import { useSessionStore } from '@/stores/session'

// action
const { getHeader, getRouteName} = useSessionStore()

// components
import Search from '@/components/Search.vue'

</script>
