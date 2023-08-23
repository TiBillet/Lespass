<template>
  <div class="input-group mb-2 rounded-right w-25">
    <button class="btn btn-primary mb-0" type="button" role="button" aria-label="Ajouter 1 crédit cashless"
            @click="price.qty <= 0 ? price.qty = 0 : price.qty--">
      <i class="fa fa-minus" aria-hidden="true"></i>
    </button>
    <input type="text" class="form-control ps-1" :placeholder="price.qty"
           role="textbox" aria-label="Recharge cashless" v-model="price.qty"
           required>
    <button class="btn btn-primary mb-0 app-rounded-right-20" type="button" role="button"
            aria-label="Supprimer 1 crédit cashless"
            @click="price.qty > 998 ? price.qty = 998 : price.qty++">
      <i class="fa fa-plus" aria-hidden="true"></i>
    </button>
    <div class="input-group-append invalid-feedback">Pas de recharge.</div>
  </div>
</template>

<script setup>

const props = defineProps({
  price: Object
})

</script>

<style scoped>

</style>