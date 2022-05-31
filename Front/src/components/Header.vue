<template>
  <header>
    <div class="page-header min-vh-50"
         :style="{ backgroundImage: `url('${header.urlImage}')`, maxHeight: `365px` }">
      <span class="mask bg-dark opacity-8"></span>
      <div class="container">
        <div class="row">
          <div class="col-lg-8 mx-auto text-white text-center">
            <h2 class="text-white">{{ header.titre }}</h2>
            <p v-if="header.shortDescription !== null" class="lead">
              {{ header.shortDescription }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- search -->
    <div v-if="routeName !== 'Event'" class="container">
      <div class="row bg-white shadow mt-n5 border-radius-lg pb-4 p-3 position-relative w-75 mx-auto">
        <div class="col-lg-8 mt-lg-n2 mt-2">
          <label></label>
          <div class="input-group">
            <span class="input-group-text"><i class="fas fa-search" aria-hidden="true"></i></span>
            <input class="form-control" placeholder="Rechechez un évènement" type="text">
          </div>
        </div>
        <div class="col-lg-4 d-flex align-items-center mt-lg-auto mt-2">
          <button type="button" class="btn bg-gradient-primary w-100 mb-0">Rechercher</button>
        </div>
      </div>
    </div>

  </header>
</template>

<script setup>
// console.log('-> Header.vue')

// store
import {storeToRefs} from 'pinia'
import {useAllStore} from '@/stores/all'


const {routeName, header} = storeToRefs(useAllStore())

</script>
