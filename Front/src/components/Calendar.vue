<template>
  <div class="container">
    <div class="row">
      <div class="card">
        <div class="table-responsive">
          <table class="table align-items-center mb-0">
            <thead>
              <tr>
                <th class="text-uppercase text-secondary text-xxs font-weight-bolder opacity-7">Date</th>
                <th class="text-uppercase text-secondary text-xxs font-weight-bolder opacity-7 ps-2">Évenement</th>
                <th class="text-center text-uppercase text-secondary text-xxs font-weight-bolder opacity-7">Prix</th>
                <th class="text-center text-uppercase text-secondary text-xxs font-weight-bolder opacity-7"></th>
                <th class="text-secondary opacity-7"></th>
              </tr>
            </thead>
            <tbody>

              <tr v-for="event in store.events">
                <td>
                  <p class="text-xs font-weight-bold mb-0">{{ formateDate(event.datetime) }}</p>
                </td>
                <td>
                  <p class="text-xs font-weight-bold mb-0">{{ event.name }}</p>
                </td>
                <td class="align-middle text-center text-sm">
                  <p v-for="(product, index) in event.products" :key="index" class="text-xs font-weight-bold mb-0">
                    <span v-if="product.categorie_article === categorieArticle">
                      <span v-for="price in product.prices" class="me-2">
                        {{ price.name }} - {{ price.prix }}€
                      </span>
                    </span>
                  </p>
                </td>
                <td class="align-middle text-center">
                  <button type="button" class="btn btn-outline-primary btn-sm mb-0"
                    @click="goEvenement(event.slug)">Réserver</button>
                </td>
              </tr>

            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
// console.log('-> Calendar.vue')
// storeMain
import { useStore } from '@/store'

const props = defineProps({
  categorieArticle: String
})
const store = useStore()


function goEvenement(slug) {
  // console.log('-> evenement, slug =', slug)
  emitter.emit("goEvenement", slug)
}

function formateDate(dateString) {
  const date = new Date(dateString)
  return `${date.toLocaleDateString()} - ${date.toLocaleTimeString()}`
}
</script>
