<template>
  <fieldset v-if="getExistGift" class="shadow-sm p-3 mb-5 bg-body rounded"
            v-for="product in event.products.filter(prod => prod.categorie_article === 'D')" :key="product.uuid">
    <legend>
      <h3 class="font-weight-bolder text-info text-gradient align-self-start">Don</h3>
    </legend>

    <div class="form-check form-switch">
      <input v-if="getEnableGift(product.uuid) === true" class="form-check-input" type="checkbox"
             :id="`don${product.uuid}`"
             @change="setEnableGift(product.uuid, $event.target.checked)" checked>
      <input v-else class="form-check-input" type="checkbox" :id="`don${product.uuid}`"
             @change="setEnableGift(product.uuid, $event.target.checked)">
      <label class="form-check-label text-dark" :for="`don${product.uuid}`">
        Je donne un euro de plus pour soutenir les actions de la coopérative <a
          href="https://wiki.tibillet.re">TiBillet</a> en faveur de la culture et de l'économie sociale et solidaire.
      </label>
    </div>

    <div v-if="getEnableGift(product.uuid) === true">
      <!-- prix -->
      <div class="input-group mb-2 has-validation">
        <div class="col form-check" v-for="(price, index) in product.prices" :key="index">
          <!-- getPriceGift(product.uuid) -->
          <input v-if="getPriceGift(product.uuid) === price.uuid"
                 :class="`form-check-input don-uuid-price-${price.uuid}`" type="radio"
                 :name="`don-prix-${price.uuid}`" :id="`don-uuid-price-${price.uuid}`"
                 @change="changePriceGift(product.uuid, price.uuid)" checked>

          <input v-else :class="`form-check-input don-uuid-price-${price.uuid}`" type="radio"
                 :name="`don-prix-${price.uuid}`" :id="`don-uuid-price-${price.uuid}`"
                 @change="changePriceGift(product.uuid, price.uuid)">
          <label class="form-check-label" :for="`don-uuid-price-${price.uuid}`">{{ price.prix }}€</label>
        </div>
      </div>
    </div>

  </fieldset>
</template>

<script setup>
console.log('-> CardGifts.vue')

// store
import {storeToRefs} from 'pinia'
import {useEventStore} from '@/stores/event'

const props = defineProps({
  enableNames: Array
})
// state event
const {event} = storeToRefs(useEventStore())
// action(s) du state event
const {enableGifts, getEnableGift, setEnableGift, getPriceGift, changePriceGift, getExistGift} = useEventStore()

// activation des dons de la liste 'props.enableNames'
enableGifts(props.enableNames)
</script>

<style scoped>
</style>