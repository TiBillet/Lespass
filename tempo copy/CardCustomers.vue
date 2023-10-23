<template>
  <div class="input-group mt-2" v-for="(customer, index) in customers" :key="index"
  role="group" :aria-label="'Customer - ' + price.name + ' - ' + index">
    <input type="text" :value="customer.last_name" @input="emitValue(customer.uuid, 'last_name', $event.target.value)"
           placeholder="Nom" class="form-control"
           required role="textbox" :aria-label="`Nom ${price.name} - ${index}`">
    <input type="text" :value="customer.first_name" @input="emitValue(customer.uuid, 'first_name', $event.target.value)"
           placeholder="Prénom" class="form-control"
           required role="textbox" :aria-label="`Prénom ${price.name} - ${index}`">
    <button class="btn btn-primary mb-0" type="button" @click="deleteCustomer(customer.uuid)"
            style="border-top-right-radius: 30px; border-bottom-right-radius: 30px;"
    role="button" :aria-label="`Supprimer champ ${price.name} - ${index}`">
      <i class="fa fa-trash" aria-hidden="true"></i>
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
  price: Object
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
  if ((props.customers.length - 1) === 0 && props.price.adhesion_obligatoire !== null) {
    deactivationProductMembership(props.price.adhesion_obligatoire)
  }
}
</script>

<style scoped></style>