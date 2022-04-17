<template>
  <!-- Navbar -->
  <nav
      class="navbar navbar-expand-lg navbar-transparent blur blur-light fixed-top z-index-3 py-3">
    <div class="container">

      <ul class="navbar-nav navbar-nav-hover mx-auto">

        <li v-if="store.place.button_adhesion === true && statusAdhesion === false"
            class="nav-item mx-2">
          <a class="btn btn-sm bg-gradient-primary btn-round mb-0 me-1" role="button"
             data-bs-toggle="modal" data-bs-target="#modal-form-adhesion">
            Adhérez à l'association {{ place.organisation }}
          </a>
        </li>

      </ul>


      <ul class="navbar-nav d-lg-block">
        <!-- menu Profil -->
        <li v-if="statusAdhesion === true" class="nav-item dropdown dropdown-hover mx-2">
          <a id="dropDownMenuProfil" class="btn btn-sm  bg-gradient-primary btn-round mb-0 me-1" role="button"
             data-bs-toggle="dropdown" aria-expanded="false">
            <i class="fas fa-user me-1" aria-hidden="true"></i>Profil
          </a>

          <!-- sous menu Profil -->
          <div class="dropdown-menu dropdown-menu-animation dropdown-lg border-radius-lg py-0 mt-0 mt-lg-auto pe-auto"
               aria-labelledby="dropDownMenuProfil">
            <!-- menu desktop -->
            <div class="d-none d-lg-block">
              <ul class="list-group mx-auto">
                <li class="nav-item list-group-item border-0 p-0">
                  <a class="dropdown-item py-2 ps-3 border-radius-md" role="button" @click="showAssets()">
                    <div class="d-flex">
                      <div class="icon h-10 me-3 d-flex mt-1">
                        <i class="fas fa-address-card fa-fw me-1"></i>
                      </div>
                      <div>
                        <h6 class="dropdown-header text-dark font-weight-bold d-flex justify-content-cente align-items-center p-0">
                          Carte
                        </h6>
                      </div>
                    </div>
                  </a>
                </li>
                <li class="nav-item list-group-item border-0 p-0">
                  <a class="dropdown-item py-2 ps-3 border-radius-md" role="button" @click="showAdhesion()">
                    <div class="d-flex">
                      <div class="icon h-10 me-3 d-flex mt-1">
                        <i class="fas fa-hourglass-start fa-fw me-1"></i>
                      </div>
                      <div>
                        <h6 class="dropdown-header text-dark font-weight-bold d-flex justify-content-cente align-items-center p-0">
                          Adhésion
                        </h6>
                      </div>
                    </div>
                  </a>
                </li>
              </ul>
            </div>

            <!-- mobile -->

            <div class="row d-lg-none">
              <div class="col-md-12 g-0">
                <a class="dropdown-item py-2 ps-3 border-radius-md" role="button" @click="showAssets()">
                  <div class="d-flex">
                    <div class="icon h-10 me-3 d-flex mt-1">
                      <i class="fas fa-address-card fa-fw me-1"></i>
                    </div>
                    <div>
                      <h6 class="dropdown-header text-dark font-weight-bold d-flex justify-content-cente align-items-center p-0">
                        Carte
                      </h6>
                    </div>
                  </div>
                </a>
                <a class="dropdown-item py-2 ps-3 border-radius-md" role="button" @click="showAdhesion()">
                  <div class="d-flex">
                    <div class="icon h-10 me-3 d-flex mt-1">
                      <i class="fas fa-hourglass-start fa-fw me-1"></i>
                    </div>
                    <div>
                      <h6 class="dropdown-header text-dark font-weight-bold d-flex justify-content-cente align-items-center p-0">
                        Adhésion
                      </h6>
                    </div>
                  </div>
                </a>
              </div>
            </div>
          </div>
        </li>

        <li v-if="statusAdhesion === false && connection === true" class="nav-item">
          <a class="btn btn-sm  bg-gradient-primary  btn-round mb-0 me-1" role="button">
            <i class="fas fa-user me-1" aria-hidden="true"></i>Connecté
          </a>
        </li>
        <!-- connexion -->
        <li v-if="connection === false" class="nav-item">
          <a class="btn btn-sm  bg-gradient-info btn-round mb-0 me-1" role="button"
             data-bs-toggle="modal" data-bs-target="#modal-form-login">
            <i class="fas fa-sign-in-alt me-1" aria-hidden="true"></i>Se connecter
          </a>
        </li>

      </ul>
    </div>
  </nav>
  <!-- modal login -->
  <Modallogin/>
</template>

<script setup>
console.log('-> Navbar.vue')

import '../assets/css/google_fonts_family_montserrat_400.700.200.css'

// Nucleo Icons (ui)
import '../assets/css/nucleo-icons.css'


// Font Awesome Free 5.15.4 MIT License
import '../assets/js/kit-fontawesome-42d5adcbca.js'

// bootstrap (ui)
import '../assets/css/bootstrap-5.0.2/bootstrap.min.css'
import '../assets/js/bootstrap-5.0.2/bootstrap.bundle.min.js'

// perfect-scrollbar
import '../assets/css/perfect-scrollbar.css'
import '../assets/js/perfect-scrollbar/perfect-scrollbar.min.js'

// css (ui)
import '../assets/css/now-design-system-pro.min.css'
import '../assets/js/now-design-system-pro.js'

// composants
import Modallogin from './Modallogin.vue'

// vue
import {ref, onMounted} from 'vue'
import {useRouter} from 'vue-router'
// api
import {refreshAccessToken} from '@/api'
// store
import {useStore} from '@/store'
// myStore
import {StoreLocal} from '@/divers'

const router = useRouter()
const store = useStore()
let storeLocal = StoreLocal.use('localStorage', 'Tibilet-identite')
const props = defineProps({
  place: Object
})
const domain = `${location.protocol}//${location.host}`

let statusAdhesion = ref(false)
let profil = ref(null)

let connection = ref(false)
if (storeLocal.refreshToken !== '') {
  connection.value = true
}

// actualiser le accessToken
if (storeLocal.refreshToken !== '' && window.accessToken === '') {
  refreshAccessToken(storeLocal.refreshToken)
}

// si pas d'image
const getLogo = () => {
  if (props.place.logo_variations === undefined) {
    return `${domain}/media/images/image_non_disponible.svg`
  } else {
    if (props.place.logo_variations.thumbnail === undefined) {
      return `${domain}/media/images/image_non_disponible.svg`
    }
  }
  return `${domain + props.place.logo_variations.thumbnail}`
}

function showAssets() {
  const monnaies = profil.value.assets
  let contenu = `<h3>Numéro de carte : ${profil.value.numberCahslessCard}</h3>`
  for (let i = 0; i < monnaies.length; i++) {
    const monnaie = monnaies[i]
    console.log('monnaie =', monnaie)
    // <i class="fas fa-gift"></i>
    if (monnaie.monnaie_name.toLowerCase().indexOf('cadeau') !== -1) {
      contenu += `<h3>${monnaie.monnaie_name.split(' ')[0]}<i class="fas fa-gift ms-1"></i> = ${monnaie.qty}</h3>`
    } else {
      contenu += `<h3>${monnaie.monnaie_name} = ${monnaie.qty}</h3>`
    }

  }
  emitter.emit('modalMessage', {
    titre: 'Monnaies',
    dynamique: true,
    contenu: contenu
  })

}

function showAdhesion() {
  emitter.emit('modalMessage', {
    titre: 'Adhesion',
    dynamique: true,
    contenu: `
      <h3>Email : ${profil.value.email}</h3>
      <h3>Nom : ${profil.value.lastName}</h3>
      <h3>Prenom : ${profil.value.firstName}</h3>
      <h3>Inscription : ${profil.value.inscription}</h3>
      <h3>Echéance : ${profil.value.echeance}</h3>
    `
  })
}

emitter.on('statusConnection', (data) => {
  // console.log('réception de "statusConnection", data =', data)
  connection.value = data
})

emitter.on('statusAdhesion', (data) => {
  console.log('réception de "statusAdhesion", data =', data)
  if (data.cashless.a_jour_cotisation === true) {
    statusAdhesion.value = true
    profil.value = {
      email: data.email,
      lastName: data.cashless.name,
      firstName: data.cashless.prenom,
      inscription: data.cashless.date_inscription,
      echeance: data.cashless.prochaine_echeance,
      numberCahslessCard: data.cashless.cards[0].number,
      assets: data.cashless.cards[0].assets
    }
  }
})

</script>

<style scoped>
</style>