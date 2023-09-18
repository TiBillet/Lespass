<template>
  <Story title="components/QuickCommands" :layout="{ type: 'single', iframe: true }">
    <Variant title="default" :init-state="state">
      <QuickCommands :user="state.user"/>
    </Variant>
    <Variant title="test2" :init-state="state2">
       <QuickCommands :user="state2.user"/>
    </Variant>
    <template #controls>
    </template>
  </Story>
</template>

<script setup>
import QuickCommands from '../components/QuickCommands.vue'

const state = {
  user: 'jean',
  etat: true
}

const state2 = {
  user: 'julie',
  etat: false
}

</script>

<docs lang="md">
# Composant QuicCommands
## A quoi ça sert  ?

</docs>