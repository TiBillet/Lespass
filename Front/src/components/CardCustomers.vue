<template>
  <div class="input-group mb-1 test-card-billet-input-group" v-for="(customer, index) in customers" :key="index">
    <input type="text" :value="customer.last_name" @input="emitValue(customer.uuid, 'last_name', $event.target.value)"
           placeholder="Nom" aria-label="Nom" class="form-control test-card-billet-input-group-nom"
           required>
    <input type="text" :value="customer.first_name" @input="emitValue(customer.uuid, 'first_name', $event.target.value)"
           placeholder="Prénom" aria-label="Prénom" class="form-control test-card-billet-input-group-prenom"
           required>
    <button class="btn btn-primary mb-0" type="button" @click="deleteCustomer(customer.uuid)"
            style="border-top-right-radius: 30px; border-bottom-right-radius: 30px;">
      <i class="fas fa-times"></i>
    </button>
    <div class="invalid-feedback">Donnée(s) manquante(s) !</div>
  </div>
</template>

<script setup>
// console.log('-> CardCustomers.vue !')
const emit = defineEmits(['update:customers'])
const props = defineProps({
  customers: Array,
  priceUuid: String
})

function emitValue (customerUuid, key, value) {
  console.log('-> emitValue, customerUuid =', customerUuid, '  --  value =', value)
  props.customers.find(cust => cust.uuid === customerUuid)[key] = value
  emit('update:customers', props.customers)
}

function deleteCustomer(customerUuid) {
  const newData = props.customers.filter(cust => cust.uuid !== customerUuid)
  emit('update:customers', newData)
}

</script>

<style scoped>

</style>