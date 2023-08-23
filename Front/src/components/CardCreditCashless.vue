<template>
  <fieldset class="shadow-sm p-3 mb-5 bg-body rounded"
            v-for="(product, index) in products.filter(prod => prod.categorie_article === 'S')"
            :key="index">
    <legend>
      <h3 class="font-weight-bolder text-info text-gradient align-self-start">Cashless</h3>
      <p>Les organisateurs du lieux utilisent un système de carte cashless. C'est gratuit, valable à vie
        et remboursable à tout moment. Souhaitez vous recharger maintenant pour gagner du temps ? Si vous n'avez pas
        encore de carte, elle vous sera remise, chargée, contre la confirmation de cette reservation.</p>
    </legend>

    <!-- activation -->
    <div class="form-switch">
      <input class="form-check-input" type="checkbox" id="credit-cashless" v-model="product.activated"
             :checked="product.activated">
      <label class="form-check-label text-dark" for="credit-cashless">Recharger carte</label>
    </div>

    <!-- la recharge -->
    <div v-if="product.activated === true" class="input-group mb-2 rounded-right w-15">
      <button class="btn btn-primary mb-0" type="button" role="button" aria-label="Ajouter 1 crédit cashless"
              @click="product.qty <= 0 ? product.qty = 0 : product.qty--">
        <i class="fa fa-minus" aria-hidden="true"></i>
      </button>
      <input type="text" class="form-control ps-1" :placeholder="product.qty"
             role="textbox" aria-label="Recharge cashless" v-model="product.qty"
             @keyup="formatNumber($event, 3)" required>
      <button class="btn btn-primary mb-0 app-rounded-right-20" type="button" role="button" aria-label="Supprimer 1 crédit cashless"
              @click="product.qty > 998 ? product.qty = 998 : product.qty++">
        <i class="fa fa-plus" aria-hidden="true"></i>
      </button>
      <div class="input-group-append invalid-feedback">Pas de recharge.</div>
    </div>


  </fieldset>
</template>

<script setup>
console.log('-> CardCreditCashless.vue')

// attributs/props
const emit = defineEmits(['update:products'])
const props = defineProps({
  products: Object
})

function inputFocus (id) {
  document.querySelector(`#${id}`).focus()
}

function formatNumber (event, limit) {
  const element = event.target
  // obligation de changer le type pour ce code, si non "replace" ne fait pas "correctement" son travail
  element.setAttribute('type', 'text')
  let initValue = element.value
  element.value = initValue.replace(/[^\d+]/g, '').substring(0, limit)
}

</script>
