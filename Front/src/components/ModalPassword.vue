<template>
  <div id="set-password-modal" aria-hidden="true" aria-labelledby="set-password-modal"
       class="modal fade" role="dialog"
       tabindex="-1">
    <div class="modal-dialog modal-dialog-centered" role="document">
      <div class="modal-content">
        <div class="modal-body p-0">
          <div class="container card card-plain">
            <div class="card-header pb-0 text-left">
              <h3 class="font-weight-bolder text-info text-center">Créez votre mot de passe d'administration</h3>

              <div class="d-flex flex-row justify-content-center">
                <hr class="text-dark w-50">
              </div>

            </div>

            <div class="card-body">
              <form role="form" class="text-left" @submit.prevent="validerPassword($event)">
                <div class="input-group">
                  <input id="admin-password" laria-describedby="admin-password" aria-label="Password"
                         class="form-control" placeholder="Password" type="password"
                         required>
                </div>

                <div class="input-group mt-2">
                  <input id="admin-password-bis" laria-describedby="admin-password-bis" aria-label="Password"
                         class="form-control" placeholder="Password" type="password"
                         required>
                </div>
                <p class="mt-2">Notez le bien, il vous sera demandé à la page suivante :)</p>
                <div class="text-center">
                  <button class="btn btn-round bg-gradient-info btn-lg mt-4 mb-0 h-44px" type="submit">Valider
                  </button>
                </div>
              </form>


            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup>
// store
import {storeToRefs} from 'pinia'
import {useAllStore} from '@/stores/all'


// const {adhesion} = useLocalStore()
const domain = `${location.protocol}//${location.host}`
const {loading, error} = storeToRefs(useAllStore())

async function validerPassword(event) {
  if (event.target.checkValidity() === true) {
    // enregistre l'email dans le storeUser
    const password = document.querySelector('#admin-password').value
    console.log(password)

    const api = `/api/user/setpassword/`
    try {
      loading.value = true
      const response = await fetch(domain + api, {
        method: 'POST',
        cache: 'no-cache',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({password: password})
      })
      const retour = await response.json()
      console.log('retour =', retour)
      // if (response.status === 201 || response.status === 401 || response.status === 202) {

      if (response.status === 200) {
        // ferme le modal
        const elementModal = document.querySelector('#set-password-modal')
        const modal = bootstrap.Modal.getInstance(elementModal) // Returns a Bootstrap modal instance
        modal.hide()
        // message de succès
        emitter.emit('modalMessage', {
          titre: 'Validation',
          contenu: retour
        })
      } else {
        throw new Error(`Erreur lors de la création du mot de passe. Contactez l'administration.`)
      }
    } catch (erreur) {
      console.log('-> validerPassword, erreur :', erreur)
      error.value = erreur
    }
  }
  loading.value = false
}

function goAdmin() {
  location.href = '/admin'
}
</script>

<style scoped>
.h-44px {
  height: 44px;
}

.communecter-logo {
  height: 26px;
  width: auto;
}
</style>