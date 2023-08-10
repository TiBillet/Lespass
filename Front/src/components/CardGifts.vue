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
        Je donne pour soutenir les actions de la coopérative
        <a target="_blank" href="https://tibillet.org" data-bs-toggle="tooltip" data-bs-placement="top"
           title="go TiBillet">TiBillet</a> en faveur de la culture et de l'économie sociale et
        solidaire.
      </label>
    </div>

    <!-- prix -->
    <div v-if="gift.activatedGift === true" class="input-group has-validation">
      <div class="col form-check" v-for="(price, index) in gift.prices" :key="index">
        <input type="radio" :name="`don-prix-${index}`" :id="`don-uuid-price-${index}`"
               v-model="gift.selectedPrice" :value="price.uuid"
               :class="`form-check-input don-uuid-price-${price.uuid}`" required>
        <label class="form-check-label" :for="`don-uuid-price-${index}`">{{ price.prix }}€</label>
        <div v-if="index === 0" class="invalid-feedback w-100">
          Option SVP
        </div>
      </div>
    </div>
  </fieldset>
  <button @click="deleteCurrentEventForm()">Test reset form</button>
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