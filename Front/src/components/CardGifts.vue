<template>

  <fieldset class="shadow-sm p-3 mb-5 bg-body rounded"
            v-for="(gift, index) in getEventForm.products.filter(prod => prod.categorie_article === 'D')" :key="index">
    <legend>
      <h3 class="font-weight-bolder text-info text-gradient align-self-start">Don</h3>
    </legend>
    <!-- activation du don -->
    <div class="form-check form-switch">
      <input class="form-check-input" type="checkbox" :id="`don${gift.uuid}`"
             v-model="gift.activatedGift">
      <label class="form-check-label text-dark" :for="`don${gift.uuid}`">
        Je donne {{ gift.prices[0].prix }} € pour soutenir les actions de la coopérative
        <a target="_blank" href="https://tibillet.org" data-bs-toggle="tooltip" data-bs-placement="top"
           title="go TiBillet">TiBillet</a> en faveur de la culture et de l'économie sociale et
        solidaire.
      </label>
    </div>
  </fieldset>
</template>

<script setup>
console.log('-> CardGifts.vue')
// store
import { useSessionStore } from '../stores/session'

const { getEventForm, deleteCurrentEventForm } = useSessionStore()

// active le premier prix par défaut si don activé
function selectFirstPrice (event) {
  if (event.target.checked === true) {
    document.querySelector('#don-uuid-price-0').click()
  } else {
    const eles = document.querySelectorAll('input[name="don-prix-0"]')
    eles.forEach((ele) => {
      ele.checked = false
    })
  }
}
</script>

<style scoped>
a[target] {
  color: #2ca8ff;
  font-weight: bold;
}
</style>