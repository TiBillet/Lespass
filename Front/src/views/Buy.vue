<template>
  <div class="container-fluid">
    <div class="row">
      <div class="text-center">
        <h1>{{ currentEvent.name }}</h1>
      </div>
      <div class="col-lg-6 mx-auto d-flex justify-content-center flex-column">
        <form @submit.prevent="validerAchats($event)" class="needs-validation" novalidate>
          <div class="card-body">
            <div class="row">

              <!-- email -->
              <fieldset class="col-md-12 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
                <legend>Email</legend>
                <div class="mb-2">
                  <div class="input-group has-validation">
                    <input :value="this.$store.state.formulaire[uuidEvent].email" type="email"
                           pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$"
                           class="form-control" placeholder="Adresse" required @keyup="majFormulaire($event, 'email')">
                    <div class="invalid-feedback">
                      Une adresse email valide svp !
                    </div>
                  </div>
                </div>

                <div class="mb-2">
                  <div class="input-group has-validation">
                    <input id="email-confirmation" :value="this.$store.state.formulaire[uuidEvent].confirmeEmail"
                           type="email"
                           pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$" class="form-control"
                           placeholder="Confirmer adresse" required @change="majFormulaire($event, 'confirmeEmail')">
                    <div class="invalid-feedback">
                      Une adresse email valide et identique svp !
                    </div>
                  </div>
                </div>

                <!-- message pour l'adresse email -->
                <div class="text-warning mb-0">
                  Cette adresse email vous permet de recevoir votre(vos) billet(s),
                  si celle-ci comporte une erreur vous n'aurez pas votre(vos) billet(s).
                </div>
                <!-- attention adresse email -->
                <div class="col-md-12">
                  <div class="form-check form-switch">
                    <input v-model="attentionEmail" class="form-check-input"
                           type="checkbox" id="valid-email"
                           @change="majFormulaire($event, 'attentionEmail')" required>
                    <label class="form-check-label text-dark" for="valid-email">Prise en compte du message
                      si-dessus. {{ this.$store.state.formulaire[uuidEvent].attentionEmail }}</label>
                    <div class="invalid-feedback">La prise en compte doit être activée, svp !</div>
                  </div>
                </div>

              </fieldset>

              <!-- Position -->
              <fieldset class="col-md-12 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
                <legend>Position</legend>
                <div class="d-flex flex-row">
                  <div class="form-check">
                    <input value="fosse" id="position1" class="form-check-input" type="radio"
                           v-model="this.$store.state.formulaire[uuidEvent].position"
                           @change="majFormulaire($event, 'position')">
                    <label class="form-check-label" for="position1">Fosse</label>
                    <div class="invalid-feedback">Position, svp !</div>
                  </div>
                  <div class="form-check ms-4">
                    <input value="gradin" id="position2" class="form-check-input" type="radio"
                           v-model="this.$store.state.formulaire[uuidEvent].position"
                           @change="majFormulaire($event, 'position')">
                    <label class="form-check-label" for="position2">Gradin</label>
                    <div class="invalid-feedback">Position, svp !</div>
                  </div>

                </div>
              </fieldset>

              <!-- adhésion -->
              <fieldset class="col-md-12 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
                <legend>Adhésion</legend>
                <div class="form-check form-switch">
                  <input v-model="adhesion" class="form-check-input" type="checkbox" id="etat-adhesion"
                         @change="majFormulaire($event, 'adhesion')">
                  <label class="form-check-label text-dark" for="etat-adhesion">Prendre une adhésion
                    associative.</label>
                </div>
                <div v-if="adhesion">
                  <!-- nom -->
                  <div class="input-group mb-2 has-validation">
                    <input :value="this.$store.state.formulaire[uuidEvent].adhesionInfos.nom" type="text"
                           class="form-control"
                           placeholder="Nom" aria-label="Nom pour l'adhésion" required
                           @keyup="majFormulaire($event, 'adhesionInfos.nom')">
                    <div class="invalid-feedback">Un nom svp !</div>
                  </div>
                  <!-- prénom -->
                  <div class="input-group mb-2 has-validation">
                    <input :value="this.$store.state.formulaire[uuidEvent].adhesionInfos.prenom" type="text"
                           id="adhesion-prenom" class="form-control"
                           placeholder="Prénom" aria-label="Prénom pour l'adhésion" required
                           @keyup="majFormulaire($event, 'adhesionInfos.prenom')">
                    <div class="invalid-feedback">Un prénom svp !</div>
                  </div>
                  <!-- adresse -->
                  <div class="input-group mb-2 has-validation">
                    <input :value="this.$store.state.formulaire[uuidEvent].adhesionInfos.adresse" id="adhesion-adresse"
                           type="text"
                           class="form-control" placeholder="Adresse" aria-label="Adresse pour l'adhésion" required
                           @keyup="majFormulaire($event, 'adhesionInfos.adresse')">
                    <div class="invalid-feedback">Une adresse svp !</div>
                  </div>
                  <!-- téléphone -->
                  <div class="input-group mb-2 has-validation">
                    <input :value="this.$store.state.formulaire[uuidEvent].adhesionInfos.tel" type="tel"
                           class="form-control"
                           placeholder="Fixe ou Mobile" pattern="^[0-9-+\s()]*$"
                           aria-label="Adresse pour l'adhésion" required
                           @keyup="majFormulaire($event, 'adhesionInfos.tel')">
                    <div class="invalid-feedback">Un numéro de téléphone svp !</div>
                  </div>

                </div>
              </fieldset>

              <!-- products/Billets -->
              <BilletsInputs :uuid-event="uuidEvent" :product-name="product.name" :prices="product.prices"/>

              <div class="col-md-12">
                <button type="submit" class="btn bg-gradient-dark w-100">Valider la réservation</button>
              </div>

            </div>
          </div>
        </form>

      </div>


    </div>
  </div>
</template>

<script setup>
console.log('-> Buy.vue')

import { ref } from 'vue'
import { useStore } from 'vuex'
import { useRoute } from 'vue-router'

// composants
import BilletsInputs from '../components/BilletsInputs.vue'

const route = useRoute()
const store = useStore()

const uuidEvent = route.params.uuidEvent
let adhesion = ref(store.state.formulaire[uuidEvent].adhesion)
let attentionEmail = ref(store.state.formulaire[uuidEvent].attentionEmail)
const currentEvent = store.state.events.find(evt => evt.uuid === uuidEvent)
const product = currentEvent.products.find(prod => prod.uuid === route.params.productUuid)

// console.log('currentEvent =', currentEvent)
// console.log('store =', store)
// console.log('uuidEvent =', uuidEvent)

function majFormulaire(event, sujet) {
  let valeur = event.target.value
  if (sujet === 'attentionEmail') {
    valeur = attentionEmail.value
  }
  if (sujet === 'adhesion') {
    valeur = adhesion.value
  }
  // console.log('-> majFormulaire, sujet =', sujet, '  --  valeur =', valeur)
  store.commit('majFormulaire', {uuidEvent: uuidEvent, sujet: sujet, valeur: valeur})
}


function validerAchats(event) {
  console.clear()

  if (event.target.checkValidity() === false) {
    // lance le test de validation du formulaire (méthode bootstrap)
    event.target.classList.add('was-validated')
  } else {
    // rendre le cham input '#email-confirmation' invalid si les emails sont différents
    if (this.store.state.formulaire[uuidEvent].email !== this.store.state.formulaire[uuidEvent].confirmeEmail) {
      document.querySelector('#email-confirmation').classList.add('is-invalid')
    } else {
      // Validation du formulaire ok
      document.querySelector('#email-confirmation').classList.remove('is-invalid')
      event.target.classList.remove('was-validated')

      // requête reservation/achat dd@hh.fr
      let data = {
        event: uuidEvent,
        email: this.store.state.formulaire[uuidEvent].email,
        position: this.store.state.formulaire[uuidEvent].position
      }
      // données adhésion
      if (this.store.state.formulaire[uuidEvent].adhesion === true) {
        data.adhesion = {
          nom: this.store.state.formulaire[uuidEvent].adhesionInfos.nom,
          prenom: this.store.state.formulaire[uuidEvent].adhesionInfos.prenom,
          adresse: this.store.state.formulaire[uuidEvent].adhesionInfos.adresse,
          tel: this.store.state.formulaire[uuidEvent].adhesionInfos.tel
        }
      }

      let identifiants = store.state.formulaire[uuidEvent].identifiants
      // console.log('identifiants =', identifiants)

      // regroupement d'identifiants par uuidTarif
      let groupes = {}
      for (let i = 0; i < identifiants.length; i++) {
        const uuidTarif = identifiants[i].uuidTarif
        if (identifiants[i].uuidTarif === uuidTarif) {
          if (groupes[uuidTarif] === undefined) {
            groupes[uuidTarif] = []
          }
          groupes[uuidTarif].push({
            first_name: identifiants[i].prenom,
            last_name: identifiants[i].nom
          })
        }
      }

      // console.log('groupes =', groupes)

      // composition des "data prices"
      let prices = []
      for (let uuidTarif in groupes) {
        // console.log('uuidTarif =', uuidTarif, '  --  qty =', groupes[uuidTarif].length)
        let tabIdentifiants = []
        for (let i = 0; i < groupes[uuidTarif].length; i++) {
          const identifiant = groupes[uuidTarif][i]
          tabIdentifiants.push(identifiant)
        }
        prices.push({
          uuid: uuidTarif,
          qty: groupes[uuidTarif].length,
          customers: tabIdentifiants
        })
      }
      data.prices = prices

      // console.log('data =', JSON.stringify(data, null, 2))

      // ne "POST" pas si pas d'adhésion ni achats (prices = [] = vide)
      if (data.adhesion === undefined && data.prices.length === 0) {
         emitter.emit('message', {typeMsg: 'info', contenu: 'Aucun achat !', tmp: 5})
      }

      // achat de billets +/ou pas adhésion
       if (data.prices.length > 0) {
         const urlApi = `/api/reservations/`
        // options de la requête
        const options = {
          method: 'POST',
          body: JSON.stringify(data),
          headers: {
            'Content-Type': 'application/json'
          }
        }
        // console.log(`-> achète le(s) prodruit(s), ${urlApi} !`)
        // console.log('options =', options)

         fetch(urlApi, options).then((reponse) => {
          if (reponse.ok === true) {
            return reponse.json()
          } else {
            // informe erreur réseau
            emitter.emit('message', {
              typeMsg: 'danger',
              contenu: `Store, réservation produits : ${reponse.status} - ${reponse.statusText}`,
              tmp: 5
            })
          }
        }).then((data) => {
          console.log('réponse à la reservation =', data)
        })
       }

       // TODO: paiement adhésion
    }
  }
}
</script>

<style scoped>
</style>