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

            <tr v-for="item in this.$store.state.events">
              <td>
                <p class="text-xs font-weight-bold mb-0">{{ formateDate(item.datetime) }}</p>
              </td>
              <td>
                <p class="text-xs font-weight-bold mb-0">{{ item.name }}</p>
              </td>
              <td class="align-middle text-center text-sm">
                <p v-for="(uuidProd, index) in item.products" :key="index" class="text-xs font-weight-bold mb-0">

                <span v-for="produit in produits.filter(prod => prod.uuid === uuidProd)" :key="produit.uuid">
                  <span v-if="produit.categorie_article === categorieArticle">
                    <span v-for="price in produit.prices" class="me-2">
                      {{ price.name }} - {{ price.prix }}€
                    </span>
                  </span>
                </span>

                </p>
              </td>
              <td class="align-middle text-center">
                <button type="button" class="btn btn-outline-primary btn-sm mb-0" @click="goEvenement(item.slug)">Réserver</button>
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
import {useStore} from 'vuex'

const props = defineProps({
  categorieArticle: String
})
const store = useStore()

// convertion du proxy en array
let produits = JSON.parse(JSON.stringify(store.state.products))

function goEvenement(slug) {
  // console.log('-> evenement, slug =', slug)
  emitter.emit("goEvenement", slug)
}

function formateDate(dateString) {
  const date = new Date(dateString)
  return `${date.toLocaleDateString()} - ${date.toLocaleTimeString()}`
}
</script>
