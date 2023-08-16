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
// store
import { useSessionStore } from '@/stores/session'


const emit = defineEmits(['update:customers'])
const props = defineProps({
  customers: Array,
  membershipRequired: String
})

const { deactivationProductMembership } = useSessionStore()

function emitValue (customerUuid, key, value) {
  props.customers.find(cust => cust.uuid === customerUuid)[key] = value
  emit('update:customers', props.customers)
}

function deleteCustomer(customerUuid) {
  const newData = props.customers.filter(cust => cust.uuid !== customerUuid)
  emit('update:customers', newData)
  // désactive l'adhésion liée au prix si "cutomer/client" = 0
  if ((props.customers.length - 1) === 0 && props.membershipRequired !== null) {
    deactivationProductMembership(props.membershipRequired)
  }
}
</script>

<style scoped></style>