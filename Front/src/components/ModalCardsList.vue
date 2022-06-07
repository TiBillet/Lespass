<template>
  <div class="modal fade" id="cards-list-modal" tabindex="-1" role="dialog"
       aria-labelledby="Exemple de message sous forme d'un modal."
       aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered modal-dialog-scrollable" role="document">
      <div class="modal-content">
        <div class="modal-header">
          <h2 class="modal-title">Cartes</h2>
          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close">
            <span aria-hidden="true">&times;</span>
          </button>
        </div>
        <!-- contenu  -->
        <div class="modal-body">

{{}}
          <fieldset class="shadow-sm p-3 mb-5 bg-body rounded" v-for="(card, index) in me.cashless.cards" :key="index">
            <legend>
              <h5 class="font-weight-bolder text-info text-gradient align-self-start w-85">Numéro {{ card.number }}</h5>
            </legend>
            <div class="row" v-for="(monnaie, indexM) in card.assets" :key="indexM">
              <div class="col-8">{{ monnaie.qty }} {{ monnaie.monnaie_name }}</div>
              <div class="col-4">{{ dateToFrenchFormat(monnaie.last_date_used) }}</div>
            </div>

            <a :href="getReloadLink(card.uuid_qrcode)" class="btn btn-secondary btn-sm active mt-4" role="button"
               aria-pressed="true">
              <div class="d-flex justify-content-star align-items-center">
                <div>Recharger</div>
                <i class="fas fa-address-card fa-fw ms-2" aria-hidden="true"></i>
              </div>
            </a>
          </fieldset>

        </div>
        <div class="modal-footer">
          <button type="button" class="btn bg-gradient-secondary" data-bs-dismiss="modal">Close</button>
        </div>
      </div>
    </div>
  </div>


</template>

<script setup>
// vue
import {onMounted} from 'vue'

// store
import {storeToRefs} from 'pinia'
import {useAllStore} from '@/stores/all'
import {useLocalStore} from '@/stores/local'

const {loading, error} = storeToRefs(useAllStore())
const {me} = storeToRefs(useLocalStore())
const {getMe} = useLocalStore()

function dateToFrenchFormat(dateString) {
  const nomMois = ['','Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
  const dateArray = dateString.split('T')[0].split('-')
  const mois = nomMois[parseInt(dateArray[1])]
  return dateArray[2] + ' ' + mois + ' ' + dateArray[0]
}

function getReloadLink(uuidQrcode) {
  return `${location.protocol}//${location.host}/qr/${uuidQrcode}`
}

// maj des data une fois le moal affiché
onMounted(() => {
  if (document.querySelector('#cards-list-modal')) {
    document.querySelector('#cards-list-modal').addEventListener('shown.bs.modal', async function () {
      try {
        loading.value = true
        me.value = await getMe(window.accessToken)
        loading.value = false
      } catch (error) {
        loading.value = false
        error.value = error
      }
    })
  }
})

</script>

<style scoped>

</style>