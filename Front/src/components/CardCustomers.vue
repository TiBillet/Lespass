<template>
  <div class="position-relative d-flex flex-row tibillet-input-group mt-4" v-for="(customer, index) in customers"
    :key="index" role="group" :aria-label="'Customer - ' + price.name + ' - ' + index">
    <InputMd :id="'customer-last-name' + index" label="Nom" :msg-role="`Nom ${price.name} - ${index}`"
      msg-error="Entrer un nom." v-model="customer.last_name" type="email" :validation="true" style="width: 48%;" />
    <InputMd :id="'customer-fist-name' + index" label="Prenom" :msg-role="`Prénom ${price.name} - ${index}`"
      msg-error="Entrer un prénom." v-model="customer.first_name" type="email" :validation="true" style="width: 48%;" />
    <font-awesome-icon icon="fa-solid fa-trash-can" @click="deleteCustomer(customer.uuid)" role="button"
      :aria-label="`Supprimer champ ${price.name} - ${index}`" style="font-size: 1.3rem;"
      class="tibillet-input-group-icon" />
  </div>
</template>

<script setup>
// console.log('-> CardCustomers.vue !')
// store
import { useSessionStore } from "@/stores/session"
import InputMd from "@/components/InputMd.vue"

const emit = defineEmits(['update:customers'])
const props = defineProps({
  customers: Array,
  price: Object
})

const { deactivationProductMembership } = useSessionStore()

function deleteCustomer(customerUuid) {
  const newData = props.customers.filter(cust => cust.uuid !== customerUuid)
  emit('update:customers', newData)
  // désactive l'adhésion liée au prix si "cutomer/client" = 0
  if ((props.customers.length - 1) === 0 && props.price.adhesion_obligatoire !== null) {
    deactivationProductMembership(props.price.adhesion_obligatoire)
  }
}
</script>

<style scoped>
.mb-4 {
  margin-bottom: 0 !important;
}

.tibillet-input-group-icon {
  position: absolute;
  top: calc(1rem + 2px);
  right: 0;
}
</style>
