<template>
  <div class="modal fade" id="reservation-list-modal" tabindex="-1" role="dialog"
       aria-labelledby="Exemple de message sous forme d'un modal."
       aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered modal-dialog-scrollable modal-xl" role="document">
      <div class="modal-content">
        <div class="modal-header">
          <h2 class="modal-title">Réservations(s)</h2>
        </div>
        <!-- contenu  -->
        <div class="modal-body">

          <fieldset class="shadow-sm p-3 mb-5 bg-body rounded" v-for="(reservation, index) in me.reservations"
                    :key="index">
            <legend>
              <h5 class="font-weight-bolder text-info text-gradient align-self-start w-85">
                {{ getEventName(reservation.event) }} - {{ dateToFrenchFormat(reservation.datetime) }}
              </h5>
            </legend>
            <div class="row" v-for="(ticket, index2) in reservation.tickets" :key="index2">
              <div class="col-8 text-capitalize">{{ ticket.first_name }} {{ ticket.last_name }}</div>
              <div class="col-4">
                <a @click="downloadBlank(ticket.pdf_url)"
                   class="d-flex flex-row-reverse align-items-center cursor-pointer">
                  <i class="fa fa-download ms-1" aria-hidden="true"></i>
                  <h6 class="m-0 text-dark">Télécharger</h6>
                </a>
              </div>
            </div>
          </fieldset>

          <div class="modal-footer">
            <button type="button" class="btn bg-gradient-secondary" data-bs-dismiss="modal">Fermer</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
// vue
import {onMounted} from 'vue'

// store
import { storeToRefs } from 'pinia'
import { useSessionStore } from '@/stores/session'

const sessionStore = useSessionStore()
const { accessToken, me } = storeToRefs(sessionStore)

const { getEventName } = sessionStore
const domain = `${window.location.protocol}//${window.location.host}`

function dateToFrenchFormat(dateString) {
  const nomMois = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
  const dateArray = dateString.split('T')[0].split('-')
  const mois = nomMois[parseInt(dateArray[1])]
  return dateArray[2] + ' ' + mois + ' ' + dateArray[0]
}

function downloadBlank(pdfUrl) {
  const redirectWindow = window.open(pdfUrl, '_blank')
  redirectWindow.location
}
</script>

<style scoped>

</style>