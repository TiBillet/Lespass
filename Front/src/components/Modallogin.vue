<template>
  <div id="modal-form-login" aria-hidden="true" aria-labelledby="modal-form-login"
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
                  <input id="test-email" v-model="email" laria-describedby="email-addon" aria-label="Email"
                         class="form-control" placeholder="Email" type="email"
                         pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$" required>
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
</template>
<script setup>
// vue
import {useStore} from 'vuex'
import {ref} from 'vue'

const email = ref('dijouxnicolas@sfr.fr')
const store = useStore()
const domain = `${location.protocol}//${location.host}`

async function validerLogin() {
  console.log('fonc validerLogin, email =', email.value)

  // test si adhérant et utilisateur
  const emailB64 = btoa(email.value)
  let api = `/api/membership/${emailB64}/`
  let aJourCotisation = null
  let user = false

  console.log('url =', domain + api)
  try {
    const response = await fetch(domain + api, {
      method: 'GET',
      cache: 'no-cache', // *default, no-cache, reload, force-cache, only-if-cached
      headers: {
        'Content-Type': 'application/json'
      }
    })
    // génère une erreur si response différent de 200(ok)
    if (response.status !== 200 && response.status !== 402) {
      throw new Error(`${response.status} - ${response.statusText}`)
    }
    const retour = await response.json()
    // console.log('retour =', JSON.stringify(retour, null, 2))
    // console.log('retour.a_jour_cotisation =', retour.a_jour_cotisation)
    if (retour.a_jour_cotisation !== undefined) {
      aJourCotisation = retour.a_jour_cotisation
      user = true
      store.commit('updateProfilEmail', email.value)
    }
    // 402
    if (retour === 'no User' || response.status === 402) {
      user = false
    }

  } catch (erreur) {
    emitter.emit('message', {
      tmp: 6,
      typeMsg: 'warning',
      contenu: `Erreur, ${domain + api} : ${erreur}`
    })
  }

  console.log('aJourCotisation =', aJourCotisation, '  --  user =', user)

  // créer l'utilisateur
  if (user === false) {
    api = `/api/user/create/`
    try {
      const response = await fetch(domain + api, {
        method: 'POST',
        cache: 'no-cache',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({email: email.value})
      })
      if (response.status !== 201) {
        throw new Error(`Erreur création utilisateur !`)
      }
      const retour = await response.json()
      if (response.status === 201) {
        // ferme le modal
        const elementModal = document.querySelector('#modal-form-login')
        const modal = bootstrap.Modal.getInstance(elementModal) // Returns a Bootstrap modal instance
        modal.hide()
        // message de succès
        emitter.emit('message', {
          tmp: 6,
          typeMsg: 'success',
          contenu: retour
        })
      }
    } catch (erreur) {
      emitter.emit('message', {
        tmp: 8,
        typeMsg: 'warning',
        contenu: `Erreur, ${domain + api} : ${erreur}`
      })
    }
  }
  /*
     .then(response => {
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
*/

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