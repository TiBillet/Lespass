<template>
  <div id="modal-onboard" aria-hidden="true" aria-labelledby="modal-onboard"
       class="modal fade" role="dialog"
       tabindex="-1" >
    <div class="modal-dialog modal-dialog-centered" role="document">
      <div class="modal-content">
        <div class="modal-body p-0">
          <div class="container card card-plain">
            <div class="card-header pb-0 text-left">
              <h3 class="font-weight-bolder text-info text-center">Créez votre espace !</h3>
              <div class="d-flex flex-row justify-content-center">
                <hr class="text-dark w-50">
              </div>
            </div>

            <div class="card-body">
              <p class="">Gérez vos abonnements, vos évènements, votre café ou restaurant et bien plus encore avec <a
                  href="https://tibillet.org">TiBillet</a> !</p>
              <p class="">Créez un espace autonome et sécurisé de paiement en partenariat avec Stripe.</p>
              <p class="mt-2">Lorsque vos informations légales seront validées, un mail vous sera envoyé pour finaliser
                votre espace.</p>

              <div class="d-flex flex-row justify-content-center mt-4">
                <hr class="text-dark w-50">
              </div>

              <div class="text-center mt-2">
                <button class="btn btn-round bg-gradient-info btn-lg" type="button"
                        @click="goStripe()">
                  <div class="d-flex flex-row justify-content-center align-items-center w-100 ">
                    <span>Créer son espace</span>
                  </div>
                </button>
              </div>
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

// asset
import communecterLogo from '@/assets/img/communecterLogo_31x28.png'

// const {adhesion} = useLocalStore()
const domain = `${location.protocol}//${location.host}`
const {adhesion, loading, error} = storeToRefs(useAllStore())

async function goStripe() {
    // enregistre l'email dans le storeUser
    console.log('-> goStripe Onboard')

    const api = `/api/onboard/`
    try {
      loading.value = true
      const response = await fetch(domain + api, {
        method: 'GET',
        cache: 'no-cache',
        headers: {
          'Content-Type': 'application/json'
        },
      })
      const retour = await response.json()
      console.log('retour =', retour)
      // if (response.status === 201 || response.status === 401 || response.status === 202) {

      if (response.status === 202) {
          location.href = retour
      } else {
        throw new Error(`Erreur goStripe Onboard'`)
      }
    } catch (erreur) {
      console.log('-> validerLogin, erreur :', erreur)
      error.value = erreur
      loading.value = false
    }
}



</script>

<style scoped>

/*.no-click {*/
/*    opacity: 0.2;*/
/*    pointer-events: none;*/
/*}*/

.h-44px {
  height: 44px;
}

.communecter-logo {
  height: 26px;
  width: auto;
}
</style>