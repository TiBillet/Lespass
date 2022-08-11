<template>
  <header>
    <div
      class="page-header min-vh-50"
      :style="{ backgroundImage: `url('${header.urlImage}')`, maxHeight: `365px` }"
    >
      <span class="mask bg-dark opacity-8"></span>
      <div class="container">
        <div class="row">
          <div class="col-lg-8 mx-auto text-white text-center">
            <h2 class="text-white">{{ header.titre }}</h2>
            <p v-if="header.shortDescription !== null" class="lead">{{ header.shortDescription }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- search -->
    <div v-if="routeName === 'Accueil'" class="container">
      <Search />
    </div>
  </header>
</template>

<script setup>
// console.log('-> Header.vue')

// components
import Search from '@/components/Search.vue'

import { watch } from "vue"

// store
import { storeToRefs } from 'pinia'
import { useAllStore } from '@/stores/all'

const { routeName, header } = storeToRefs(useAllStore())

watch(routeName, (newValue, oldValue) => {
  console.log('-> routeName:', newValue, oldValue)
})
</script>
