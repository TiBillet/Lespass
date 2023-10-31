<template>
  <fieldset class="shadow-sm p-3 mb-5 bg-body rounded"
    v-for="(product, index) in products.filter(prod => prod.categorie_article === 'S')" :key="index">
    <legend>
      <h3 class="font-weight-bolder text-info text-gradient align-self-start">Cashless</h3>
      <p>Les organisateurs du lieux utilisent un système de carte cashless. C'est gratuit, valable à vie et
        remboursable à tout moment. Une recharge minimale de 10€ est réclamée pour votre réservation.
        Si vous n'avez pas encore de carte, elle vous sera remise, chargée, contre la confirmation de cette
        reservation.</p>
    </legend>

    <!-- activation -->
    <div class="form-switch">
      <input class="form-check-input" type="checkbox" id="credit-cashless" v-model="product.activated"
        :checked="product.activated" role="checkbox" aria-label="Activer cashless."
        :class="product.activated ? 'bg-success' : ''">
      <label class="form-check-label text-dark ms-2" for="credit-cashless">Recharger carte</label>
    </div>

    <!-- la recharge -->
    <InputNumber v-if="product.activated === true" :button="false"
                 v-model:price="products.filter(prod => prod.categorie_article === 'S')[index]" :min="min" :max="max"
                 info-aria="Recharge cashless"/>

  </fieldset>
</template>

<script setup>
console.log('-> CardCreditCashless.vue')
// components
import InputNumber from './InputNumber.vue'

// attributs/props
const emit = defineEmits(['update:products'])
const props = defineProps({
  products: Object,
  min: Number,
  max: Number
})

function inputFocus(id) {
  document.querySelector(`#${id}`).focus()
}

function formatNumber(event, limit) {
  const element = event.target
  // obligation de changer le type pour ce code, si non "replace" ne fait pas "correctement" son travail
  element.setAttribute('type', 'text')
  let initValue = element.value
  element.value = initValue.replace(/[^\d+]/g, '').substring(0, limit)
}

</script>
