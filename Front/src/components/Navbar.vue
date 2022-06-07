<template>
  <nav id="navbar" class="navbar navbar-expand-lg z-index-3 w-100 navbar-transparent position-fixed">
    <div class="container">
      <!-- lieu -->
      <div class="navbar-brand">
        <a href="/" class="navbar-brand d-flex justify-content-between align-items-center">
          <h6 class="m-0 text-white">{{ place.organisation }}</h6>
        </a>
      </div>

      <!-- partie droite -->
      <ul class="navbar-nav d-flex flex-row-reverse ms-auto d-block">
        <!-- user -->
        <!-- <li v-if="adhesion.status === 'membership' || refreshToken !== ''" class="nav-item dropdown"> -->
        <li v-if="refreshToken !== ''" class="nav-item dropdown">
          <a class="nav-link d-flex justify-content-between align-items-center dropdown-toggle me-1" href="#"
             id="menuUser"
             role="button" data-bs-toggle="dropdown" aria-expanded="false">
            <i class="fas fa-user me-1" aria-hidden="true"></i>
            <h6 class="m-0 text-white">User</h6>
          </a>
          <!-- menu user -->
          <ul class="dropdown-menu w-100" aria-labelledby="menuUser">
            <!-- déconnexion -->
            <li v-if="refreshToken !== ''">
              <a class="dropdown-item border-radius-md d-flex justify-content-star align-items-center"
                 role="button" @click="disconnect()">
                <i class="fa fa-sign-out text-dark" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Deconnexion</h6>
              </a>
            </li>
            <!-- assets -->
            <li v-if="infosCardExist() === true">
              <a class="dropdown-item border-radius-md d-flex justify-content-star align-items-center"
                 role="button" @click="showAssets()">
                <i class="fa fa-money fa-fw me-1 text-dark" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Monnaies</h6>
              </a>
            </li>
            <!-- réservations -->
            <li v-if="infosReservationExist() === true">
              <a class="dropdown-item border-radius-md d-flex justify-content-star align-items-center"
                 role="button" @click="showReservations()">
                <i class="fa fa-ticket fa-fw me-1 text-dark tourne-ticket" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Réservation(s)</h6>
              </a>
            </li>

            <!-- les adhésions du client -->
            <li>
              <a class="dropdown-item border-radius-md d-flex justify-content-star align-items-center"
                 role="button" data-bs-toggle="modal" data-bs-target="#membership-owned-modal">
                <i class="fa fa-users fa-fw me-1 text-dark" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Mes adhésions</h6>
              </a>
            </li>
          </ul>
        </li>

        <!-- pas de connexion -->
        <li class="nav-item">
          <a v-if="refreshToken === ''" class="nav-link ps-1 d-flex justify-content-between align-items-center"
             role="button"
             data-bs-toggle="modal" data-bs-target="#modal-form-login">
            <i class="fa fa-user-circle-o me-1 text-white" aria-hidden="true"></i>
            <h6 class="m-0 text-white">Se connecter</h6>
          </a>
        </li>

        <!-- adhésions -->
        <li class="nav-item">
          <a v-if="routeName !== 'Adhesions'" href="/adhesions"
             class="nav-link ps-1 d-flex justify-content-between align-items-center"
             :title="`Adhésions possibles à l'association '${ place.organisation }'`">
            <i class="fa fa-users me-1 text-white" aria-hidden="true"></i>
            <h6 class="m-0 text-white">Adhésions</h6>
          </a>
        </li>

      </ul>

    </div>
  </nav>
</template>

<script setup>
// console.log(' -> Navbar.vue !')

// store
import {storeToRefs} from 'pinia'
import {useAllStore} from '@/stores/all'
import {useLocalStore} from '@/stores/local'

const {place, events, adhesion, routeName, loading, error} = storeToRefs(useAllStore())
const {getPlace, setHeaderPlace} = useAllStore()
const {refreshToken, me} = storeToRefs(useLocalStore())
const {infosCardExist, infosReservationExist, getMe, refreshAccessToken} = useLocalStore()

// load place
getPlace()

if (window.accessToken === '' && refreshToken.value !== '') {
  updateAccessToken()
}

async function updateAccessToken() {
  // console.log('-> fonc updateAccessToken !')
  loading.value = true
  await refreshAccessToken(refreshToken.value)
  loading.value = false
}

function disconnect() {
  refreshToken.value = ''
  me.value = {}
  adhesion.value = {
    email: '',
    first_name: '',
    last_name: '',
    phone: null,
    postal_code: null,
    adhesion: '',
    status: ''
  }
}

function dateToFrenchFormat(dateString) {
  const nomMois = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
  const dateArray = dateString.split('T')[0].split('-')
  const mois = nomMois[parseInt(dateArray[1])]
  return dateArray[2] + ' ' + mois + ' ' + dateArray[0]
}

async function updateMe() {
  if (window.accessToken !== '') {
    loading.value = true
    me.value = await getMe(window.accessToken)
    loading.value = false
    return {error: 0}
  }
  return {error: 1, message: 'Access token inconnu !'}
}

async function showAssets() {
  let contenu = ``
  try {
    const actu = await updateMe()
    console.log('actu =', actu)
    if (actu.error === 1) {
      throw new Error(message)
    }
    for (const cardKey in me.value.cashless.cards) {
      const card = me.value.cashless.cards[cardKey]
      contenu += `
        <fieldset class="shadow-sm p-3 mb-5 bg-body rounded">
          <legend>
              <h5 class="font-weight-bolder text-info text-gradient align-self-start w-85">Numéro ${card.number}</h5>
          </legend>
          <div class="flex-column">
      `

      // lien de rechargement
      const reloadLink = `${location.protocol}//${location.host}/qr/${card.uuid_qrcode}`

      // assets
      for (const assetKey1 in card.assets) {
        const monnaie = card.assets[assetKey1]
        contenu += `
          <div class="row">
            <div class="col-8">${monnaie.qty} ${monnaie.monnaie_name}</div>
            <div class="col-4">${dateToFrenchFormat(monnaie.last_date_used)}</div>
          </div>
        `
      }

      contenu += `
            <a href="${reloadLink}" class="btn btn-secondary btn-sm active mt-4" role="button" aria-pressed="true">
              <div class="d-flex justify-content-star align-items-center">
                <div>Recharger</div>
                <i class="fas fa-address-card fa-fw ms-2" aria-hidden="true"></i>
              </div>
            </a>
          </div>
        </fieldset>
      `
    }
  } catch (error) {
    contenu = `<h3>Aucune donnée !</h3>`
  }

  emitter.emit('modalMessage', {
    titre: 'Monnaies',
    dynamic: true,
    scrollable: true,
    contenu: contenu
  })
}

async function showReservations() {
  let contenu = ``
  try {
    const actu = await updateMe()
    if (actu.error === 1) {
      throw new Error(message)
    }

    for (const key in me.value.reservations) {
      const reservation = me.value.reservations[key]
      console.log('--> reservation =', reservation)
      const eventFind = events.value.find(evt => evt.uuid === reservation.event)
      console.log('eventFind =', eventFind)

      for (const prodKey in eventFind.products) {
        const prices = eventFind.products[prodKey].prices
        console.log('prices =', prices)
      }

      const eventName = eventFind.name

      contenu += `
        <fieldset class="shadow-sm p-3 mb-5 bg-body rounded">
          <legend>
              <h5 class="font-weight-bolder text-info text-gradient align-self-start w-85"> ${eventName} - ${dateToFrenchFormat(reservation.datetime)}</h5>
          </legend>
          <div class="flex-column">
      `

      for (const ticketKey in reservation.tickets) {
        const ticket = reservation.tickets[ticketKey]
        console.log('ticket = ', ticket)
        contenu += `
          <div class="row">
            <div class="col-8">${ticket.first_name} ${ticket.last_name}</div>
            <div class="col-4">
              <a href="${ticket.pdf_url}" download="ticket-${ticket.first_name}_${ticket.last_name}" class="d-flex flex-row-reverse align-items-center">
                <i class="fa fa-download ms-1" aria-hidden="true"></i>
                <h6 class="m-0 text-dark">Télécharger</h6>
              </a>
            </div>
          </div>
        `
      }

      contenu += `
          </div>
        </fieldset>
      `
    }


  } catch (error) {
    console.log('Rservation, erreur:', error)
    contenu = `<h3>Aucune donnée !</h3>`
  }
  emitter.emit('modalMessage', {
    titre: 'Réservation(s)',
    dynamic: true,
    // xl, lg, sm
    size: 'xl',
    scrollable: true,
    contenu: contenu
  })
}

// menu transparant / non transparant
window.addEventListener("scroll", () => {
  if (document.querySelector('#navbar') !== null) {
    if (scrollY === 0) {
      document.querySelector('#navbar').style.backgroundColor = ''
    } else {
      document.querySelector('#navbar').style.backgroundColor = '#384663'
    }
  }
})

</script>

<style scoped>
.tourne-ticket {
  transform: rotate(-20deg);
}
</style>