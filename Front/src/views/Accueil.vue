<template>
    <div class="container mt-5">
      <div class="row">
        <div class="col-lg-4 col-md-6 mb-2" v-for="(event, index) in events" :key="index">
          <CardEvent :event="event" @go-event="goEvent"/>
        </div>
      </div>
    </div>
    <div id="calendar" class="container">
      <!-- <Calendar categorie-article="B"/> -->
    </div>
</template>

<script setup>
console.log('-> Accueil.vue')

// store
import {storeToRefs} from 'pinia'
import {useAllStore} from '@/stores/all'

// routes
import {useRouter} from 'vue-router'

// composants
import CardEvent from '@/components/CardEvent.vue'
// import Calendar from '../components/Calendar.vue'


// state
const {place, header, events, loading, error} = storeToRefs(useAllStore())
// actions du state
const {getEvents} = useAllStore()
const router = useRouter()

// load events and update data header
getEvents()

function goEvent(slug) {
  // console.log('-> fonc "goEvenement"; slug =', slug)
  router.push({name: 'Event', params: {slug: slug}})
}
</script>

<style>
</style>
