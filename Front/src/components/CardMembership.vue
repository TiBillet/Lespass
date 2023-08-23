<template>

  <fieldset class="shadow-sm p-3 mb-5 bg-body rounded test-card-billet">
    <legend>
      <div class="d-flex flex-row align-items-center justify-content-between">
        <h3 class="font-weight-bolder text-info text-gradient align-self-start">{{ product.name }}</h3>
        <button class="btn btn-primary mb-0 test-card-billet-bt-add" type="button"
                @click="resetPriceCustomers(product)"
                role="button" aria-label="Supprimer adhésion associative">
          <i class="fa fa-trash" aria-hidden="true"></i>
          <span class="ms-1">Supprimer</span>
        </button>
      </div>
      <h6 v-if="product.short_description !== null" class="text-info">{{ product.short_description }}</h6>
    </legend>

    <!-- conditions -->
    <div class="input-group mb-2 has-validation">

      <div class="form-check form-switch">
        <input class="form-check-input" type="checkbox" v-model="product.conditionsRead"
               true-value="true" false-value="false" required/>
        <label class="form-check-label text-dark" for="read-conditions">
          <span>j'ai pris connaissance des </span>
          <span v-if="product.categorie_article === 'A'">
                <a v-if="product.legal_link !== null" class="text-info"
                   @click="goStatus()">statuts et du règlement intérieur de l'association.</a>
                <span v-else>statuts et du règlement intérieur de l'association</span>
          </span>
          <span v-else>
                <a v-if="product.legal_link !== null" class="text-info" @click="goStatus()">CGU/CGV.</a>
                <span v-else>CGU/CGV.</span>
          </span>
        </label>
        <div class="invalid-feedback">Conditions non acceptées.</div>
      </div>
    </div>

    <!-- prix -->
    <div class="input-group mb-2 has-validation">
      <div class="col form-check mb-2"
           v-for="(price, index) in product.prices" :key="index">
        <input v-trigger="{index,nbPrices: product.prices.length}"
               name="membership-prices" :id="`uuidcardmembershippriceradio${index}`" type="radio"
               v-model="product.customers[0].uuid" :value="price.uuid"
               class="form-check-input input-adesion-modal-price" required/>
        <label class="form-check-label text-dark" :for="`uuidcardmembershippriceradio${index}`">
          {{ price.name }} - {{ price.prix }}€
        </label>
        <div v-if="index === 0" class="invalid-feedback w-100">
          Tarif SVP
        </div>
      </div>
    </div>

    <!-- nom / prénom -->
    <div class="input-group mb-1">
      <input type="text" v-model="product.customers[0].last_name"
             placeholder="Nom ou Structure" aria-label="Nom ou Structure" class="form-control" required>
      <input type="text" v-model="product.customers[0].first_name"
             placeholder="Prénom" aria-label="Prénom" class="form-control app-rounded-right-20" required>
      <div class="invalid-feedback">Donnée(s) manquante(s).</div>
    </div>


    <!-- code postal / téléphone -->
    <div class="input-group mb-1 test-membership-input-group">
      <input type="text" v-model="product.customers[0].postal_code" placeholder="Code postal" aria-label="Code postal"
             class="form-control" @keyup="formatNumberPrentNode2($event, 5)" required>
      <input type="text" v-model="product.customers[0].phone" placeholder="Fixe ou mobile" aria-label="Fixe ou mobile"
             class="form-control app-rounded-right-20" @keyup="formatNumberPrentNode2($event, 10)" required>
      <div class="invalid-feedback">Donnée(s) manquante(s).</div>
    </div>

    <!-- options radio -->
    <div v-if="product.option_generale_radio.length > 0" class="input-group mb-2 has-validation">
      <div class="col form-check mb-2"
           v-for="(option, index) in product.option_generale_radio" :key="index">
        <input name="membership-options-radio" :id="`uuidmembershipoptionsradio${index}`" type="radio"
               v-model="product.optionRadio" :value="option.uuid"
               class="form-check-input input-adesion-modal-price"/>
        <label class="form-check-label text-dark mb-0" :for="`uuidmembershipoptionsradio${index}`">
          {{ option.name }}
        </label>
        <div v-if="index === 0" class="invalid-feedback w-100">
          Sélectionner un don
        </div>
      </div>
    </div>

    <!-- options checkbox -->
    <div v-if="product.option_generale_checkbox.length > 0" class="mt-3">
      <div v-for="(option, index) in product.option_generale_checkbox"
           :key="index" class="mb-1">
        <div class="form-switch input-group has-validation">
          <input class="form-check-input me-2 options-adhesion-to-unchecked" type="checkbox"
                 :id="`option-checkbox-adhesion${option.uuid}`" v-model="option.checked"
                 true-value="true" false-value="false">

          <label class="form-check-label text-dark mb-0" :for="`option-checkbox-adhesion${option.uuid}`">
            {{ option.name }}
          </label>
        </div>
        <div class="ms-5">{{ option.description }}</div>
        <div class="invalid-feedback">Choisisser une options !</div>
      </div>
    </div>

  </fieldset>

</template>

<script setup>
console.log('-> CardMembership.vue !')
import { onMounted } from "vue"

import { useSessionStore } from '../stores/session'

const emit = defineEmits(['update:product'])
const props = defineProps({
  product: Object,
})
const { resetPriceCustomers } = useSessionStore()

// directive qui active un prix si il est unique
const vTrigger = {
  mounted: (el, binding) => {
    const index = binding.value.index
    const nbPrices = binding.value.nbPrices
    if (index === 0 && nbPrices === 1) {
      el.click()
    }
  }
}

function goStatus () {
  const lien = getMembershipData(props.productUuid).legal_link
  // console.log('-> goStatus, lien =', lien)
  if (lien !== null) {
    window.open(lien, '_blank')
  }
}

function formatNumberPrentNode2 (event, limit) {
  const element = event.target
  // obligation de changer le type pour ce code, si non "replace" ne fait pas "correctement" son travail
  element.setAttribute('type', 'text')
  let initValue = element.value
  element.value = initValue.replace(/[^\d+]/g, '').substring(0, limit)
  if (element.value.length < limit) {
    element.parentNode.parentNode.querySelector('.invalid-feedback').style.display = 'block'
  } else {
    element.parentNode.parentNode.querySelector('.invalid-feedback').style.display = 'none'
  }
}

</script>

<style></style>