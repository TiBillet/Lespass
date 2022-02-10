<template>
  <Message/>
  <router-view></router-view>
</template>

<script setup>
import {useRouter} from 'vue-router'
import Message from './components/Message.vue'

const router = useRouter()

// router.push({name: 'ChargementDatas'})
</script>

<style>
</style>
