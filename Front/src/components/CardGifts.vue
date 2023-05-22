<template>
  <!--  <fieldset v-if="getExistGift" class="shadow-sm p-3 mb-5 bg-body rounded"-->
  <!--            v-for="product in event.products.filter(prod => prod.categorie_article === 'D')" :key="product.uuid">-->
  <fieldset class="shadow-sm p-3 mb-5 bg-body rounded"
            v-for="gift in event.products.filter(prod => prod.categorie_article === 'D')" :key="gift.uuid">
    <legend>
      <h3 class="font-weight-bolder text-info text-gradient align-self-start">Don</h3>
    </legend>
    <div class="form-check form-switch">
      <input class="form-check-input" type="checkbox" :id="`don${gift.uuid}`"
             @change="toggleEnableGift(gift.uuid, $event.target.checked)"
             :checked="getEnableGift(gift.uuid) === true ? true: false">
      <label class="form-check-label text-dark" :for="`don${gift.uuid}`">
        Je donne pour soutenir les actions de la coopérative
        <a target="_blank" href="https://tibillet.org">TiBillet</a> en faveur de la culture et de l'économie sociale et
        solidaire.
      </label>
    </div>

    <!-- prix -->
    <div class="col form-check" v-for="(price, index) in gift.prices" :key="index">
      <!-- getPriceGift(gift.uuid) -->
      <input v-if="getPriceGift(gift.uuid) === price.uuid"
             :class="`form-check-input don-uuid-price-${price.uuid}`" type="radio"
             :name="`don-prix-${price.uuid}`" :id="`don-uuid-price-${price.uuid}`"
             @change="changePriceGift(gift.uuid, price.uuid)" checked>
      <input v-else :class="`form-check-input don-uuid-price-${price.uuid}`" type="radio"
             :name="`don-prix-${price.uuid}`" :id="`don-uuid-price-${price.uuid}`"
             @change="changePriceGift(gift.uuid, price.uuid)">
      <label class="form-check-label" :for="`don-uuid-price-${price.uuid}`">{{ price.prix }}€</label>
    </div>

  </fieldset>
</template>

<script setup>
console.log('-> CardGifts.vue')
import { ref } from 'vue'

// store
import { storeToRefs } from 'pinia'
import { useEventStore } from '@/stores/event'

// state event
const { event } = storeToRefs(useEventStore())
// action(s) du state event
// const {enableGifts, getEnableGift, setEnableGift, getPriceGift, changePriceGift, getExistGift} = useEventStore()
const { toggleEnableGift, getEnableGift, getPriceGift, changePriceGift } = useEventStore()

// activation des dons de la liste 'props.enableNames'
// enableGifts(props.enableNames)
</script>

<style scoped>
</style>