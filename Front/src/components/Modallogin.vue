<template>
  <!-- login -->
  <div v-if="store.state.token === ''" id="modal-form-login" aria-hidden="true" aria-labelledby="modal-form-login"
       class="modal fade" role="dialog"
       tabindex="-1">
    <div class="modal-dialog modal-dialog-centered modal-sm" role="document">
      <div class="modal-content">
        <div class="modal-body p-0">
          <div class="card card-plain">
            <div class="card-header pb-0 text-left">
              <h3 class="font-weight-bolder text-info text-gradient">Connectez vous</h3>
              <p class="mb-0">Entrez votre email</p>
            </div>
            <div class="card-body">
              <form role="form text-left" @submit.prevent="validerLogin()">
                <div class="input-group mb-3">
                  <input v-model="email" laria-describedby="email-addon" aria-label="Email" class="form-control"
                         placeholder="Email"
                         type="email" pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$" required>
                </div>
                <div class="text-center">
                  <button class="btn btn-round bg-gradient-info btn-lg w-100 mt-4 mb-0" type="submit">Valider</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- logout -->
  <div v-if="store.state.token !== ''" id="modal-form-logout" class="modal fade" tabindex="-1" role="dialog"
       aria-labelledby="modal-notification" aria-hidden="true">
    <div class="modal-dialog modal-danger modal-dialog-centered modal-" role="document">
      <div class="modal-content">
        <div class="modal-header">
          <h6 class="modal-title" id="modal-title-notification">Attention</h6>
          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close">
            <span aria-hidden="true">×</span>
          </button>
        </div>
        <div class="modal-body">
          <div class="py-3 text-center">
            <i class="ni ni-bell-55 ni-3x"></i>
            <h4 class="text-gradient text-danger mt-4">Confirmer la déconnexion !</h4>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="validerLogout">Valider</button>
          <button type="button" class="btn btn-link text-success ml-auto" data-bs-dismiss="modal">Close</button>
        </div>
      </div>
    </div>
  </div>

</template>
<script setup>
import {useStore} from 'vuex'
import {ref} from 'vue'

const email = ref('')

const store = useStore()
const domain = `${location.protocol}//${location.host}`

function validerLogout() {
  console.log('Valider logout !')

  let api = `/auth/token/logout/`
  fetch(domain + api, {
    method: 'POST',
    cache: 'no-cache',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Token ${store.state.token}`
    },
    body: ''
  }).then(response => {
    console.log('response =', response)
    if (!response.ok) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    // vide le token
    store.commit('updateToken', '')
    // ferme le modal
    const elementModal = document.querySelector('#modal-form-logout')
    const modal = bootstrap.Modal.getInstance(elementModal) // Returns a Bootstrap modal instance
    modal.hide()

  }).catch(function (erreur) {
    // chargement.value = false
    emitter.emit('message', {
      tmp: 6,
      typeMsg: 'warning',
      contenu: `Erreur, ${domain + api} : ${erreur}`
    })
  })
}

function validerLogin() {
  console.log('fonc validerLogin, email =', email.value)

  // test membre
  const emailB64 = btoa(email.value)
  let api = `/api/membership/${emailB64}/`

  console.log('url =', domain + api )
  fetch(domain + api + emailB64 + '/', {
    method: 'GET',
    cache: 'no-cache', // *default, no-cache, reload, force-cache, only-if-cached
    headers: {
      'Content-Type': 'application/json'
      // 'Authorization': 'Bearer ${inMemoryToken}'
    }
  }).then(response => {
    if (!response.ok) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    return response.json()
  }).then(retour => {
    console.log('Retour =', JSON.stringify(retour, null, 2))
  }).catch(function (erreur) {
    // chargement.value = false
    emitter.emit('message', {
      tmp: 6,
      typeMsg: 'warning',
      contenu: `Erreur, ${domain + api} : ${erreur}`
    })
  })

  /*
  let api = `/auth/token/login/`
  console.log(`-> Obtenir le token ${domain + api}`)
  console.log('data =', JSON.stringify(form.value))

  fetch(domain + api, {
    method: 'POST',
    cache: 'no-cache', // *default, no-cache, reload, force-cache, only-if-cached
    headers: {
      'Content-Type': 'application/json'
      // 'Authorization': 'Bearer ${inMemoryToken}'
    },
    body: JSON.stringify(form.value)
  }).then(response => {
    if (!response.ok) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    return response.json()
  }).then(retour => {
    console.log('resultat =', retour)
    // enregistre le token dans le state
    store.commit('updateToken', retour.access_token)
    // ferme le modal
    const elementModal = document.querySelector('#modal-form-login')
    const modal = bootstrap.Modal.getInstance(elementModal) // Returns a Bootstrap modal instance
    modal.hide()
    // password et username vidés
    form.value.username = ''
    form.value.password = ''
  }).catch(function (erreur) {
    // chargement.value = false
    emitter.emit('message', {
      tmp: 6,
      typeMsg: 'warning',
      // contenu: `Erreur, ${domain + api} : ${erreur}`
      contenu: `Impossible de se connecter avec les informations d'identification fournies.`
    })
  })
*/
}
</script>
<style>

</style>