<template>
  <Header :header-event="getHeaderEvent()"/>
  <div class="container mt-7">
    <!-- lieu -->
    <div class="row">
      <div class="col-lg-12">
        <CardPlace :data-card="getDataCardPlace()"/>
      </div>
    </div>
    <!-- artistes -->
    <div class="row mt-5">
      <div v-for="(artist, index) in currentEvent.artists" :key="index" class="col-lg-4 mb-lg-0 mb-4">
        <CardArtist :data-artist="artist"/>
        <hr>
      </div>
    </div>
    <!-- achats -->
    <div class="row">
      <form @submit.prevent="goValiderAchats($event)" class="needs-validation" novalidate>
        <!-- index-memo="unique00" = "index fixe" bon pour tous les évènements -->
        <CardEmail index-memo="unique00"/>
        <CardProducts :products="currentEvent.products" :categories="['A', 'D']"/>

        <fieldset v-if="currentEvent.options_checkbox.length > 0 || currentEvent.options_radio.length > 0 "
                  class="col-md-12 col-lg-9 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
          <legend>options</legend>
          <ListOptionsCheckbox :options-checkbox="currentEvent.options_checkbox" :index-memo="store.currentUuidEvent"/>
        </fieldset>

        <CardProducts :products="currentEvent.products" :categories="['B', 'F']"/>
        <div class="col-md-12 col-lg-9">
          <button type="submit" class="btn bg-gradient-dark w-100">Valider la réservation</button>
        </div>
      </form>
    </div>
  </div>

</template>

<script setup>
// console.clear()
console.log('-> Event.vue !')

// vue
import {ref} from 'vue'
import {useRoute} from 'vue-router'

// composants
import Header from '@/components/Header.vue'
import CardPlace from '@/components/CardPlace.vue'
import CardArtist from '@/components/CardArtist.vue'
import CardEmail from '@/components/CardEmail.vue'
import CardProducts from '@/components/CardProducts.vue'
import ListOptionsCheckbox from '@/components/ListOptionsCheckbox.vue'

// test dev
import {getMe} from '@/api'
// import {fakeEvent} from "../../tempo/fakeCurrentEventsTest"

// store
import {useStore} from '@/store'

const route = useRoute()
const slug = route.params.slug
const store = useStore()
const domain = `${location.protocol}//${location.host}`

// récupération du uuid évènement à partir du slug
const uuidEventBrut = store.events.find(evt => evt.slug === slug).uuid
let uuidEvent = uuidEventBrut
// un retour de navigation("history")  donne un proxy et non un string
if (typeof (uuidEventBrut) === 'object') {
  // converti le proxy en string son type original avant le retour de navigation
  uuidEvent = JSON.parse(JSON.stringify(uuidEventBrut)).uuid
}

// currentEvent production
const currentEvent = store.events.find(evt => evt.uuid === uuidEvent)

// currentEvent test dev
// * const currentEvent = fakeEvent

console.log('currentEvent =', currentEvent)

store.currentUuidEvent = uuidEvent


function getHeaderEvent() {
  let urlImage
  if (currentEvent.img_variations.fhd === undefined) {
    urlImage = `${domain}/media/images/image_non_disponible.svg`
  } else {
    urlImage = currentEvent.img_variations.fhd
  }
  // console.log('urlImage =', urlImage)
  return {
    urlImage: urlImage,
    shortDescription: currentEvent.short_description,
    longDescription: currentEvent.long_description,
    titre: currentEvent.name
  }
}


function getDataCardPlace() {
  let urlImage
  if (store.place.img_variations.med === undefined) {
    urlImage = `${domain}/media/images/image_non_disponible.svg`
  } else {
    urlImage = store.place.img_variations.med
  }

  return {
    urlImage: urlImage,
    titre: store.place.organisation,
    lonDescription: store.place.long_description,
    shortDescription: store.place.short_description
  }
}

// formatage des données POST events
function formaterDatas(adhesionActive, adhesionPrix) {
  console.clear()
  const data = {
    event: store.currentUuidEvent,
    email: store.memoComposants.CardEmail.unique00.email,
    prices: [],
    options: []
  }

  // options checkbox
  const optionsCheckbox = store.memoComposants.ListOptionsCheckbox[store.currentUuidEvent]
  for (let i = 0; i < optionsCheckbox.length; i++) {
    const option = optionsCheckbox[i]
    // console.log('-> ',JSON.stringify(option, null, 2))
    if (option.activation === true) {
      data.options.push(option.uuid)
    }
  }

  // TODO: options radio
  // options radio


  // prix adhésion
  if (adhesionActive === true && adhesionPrix !== '') {
    const dataAdhesion = store.memoComposants.CardAdhesion[store.currentUuidEvent]
    data.prices.push({
      "uuid": dataAdhesion.uuidPrix,
      "qty": 1,
      "customers": [
        {
          "first_name": dataAdhesion.firstName,
          "last_name": dataAdhesion.lastName,
          "phone": dataAdhesion.phone,
          "postal_code": dataAdhesion.postalCode
        }
      ]
    })
  }

  // don
  const don = store.memoComposants.Don[store.currentUuidEvent]
  if (don.activation === true) {
    data.prices.push({
      "uuid": don.uuidPrix,
      "qty": 1
    })
  }

  // prix billets
  const billets = store.memoComposants.CardBillet[store.currentUuidEvent]
  for (let i = 0; i < billets.length; i++) {
    const billet = billets[i]
    const nbBillets = billet.users.length
    if (nbBillets > 0) {
      const obj = {
        "uuid": billet.uuid,
        "qty": nbBillets,
        "customers": []
      }
      for (let j = 0; j < billet.users.length; j++) {
        const user = billet.users[j]
        obj.customers.push({
          "first_name": user.first_name,
          "last_name": user.last_name,
        })
      }
      data.prices.push(obj)
    }
  }
  return data
}

function goValiderAchats(event) {
  // console.log('-> fonc goValiderAchats !')

  // efface tous les messages d'invalidité
  const msgInvalides = event.target.querySelectorAll('.invalid-feedback')
  for (let i = 0; i < msgInvalides.length; i++) {
    msgInvalides[i].style.display = 'none'
  }

  // vérifier activation adhésion
  const adhesionActive = store.memoComposants.CardAdhesion[store.currentUuidEvent].activation
  console.log('adhesionActive =', adhesionActive)

  // vérifier la sélection d'un prix d'adhésion
  const adhesionPrix = store.memoComposants.CardAdhesion[store.currentUuidEvent].uuidPrix
  console.log('adhesionPrix =', adhesionPrix)

  // enlever ancien sigalement (si adhésion active et aucune sélection de prix)
  if (document.querySelector(`#card-adhesion-uuid-price-parent0`)) {
    document.querySelector(`#card-adhesion-uuid-price-parent0`).querySelector(`.invalid-feedback`).style.display = 'none'
  }

  // signaler si adhésion active et aucune sélection de prix
  if (adhesionActive === true && adhesionPrix === '') {
    document.querySelector(`#card-adhesion-uuid-price-parent0`).querySelector(`.invalid-feedback`).style.display = 'block'
    document.querySelector(`#card-adhesion-uuid-price-parent0`).scrollIntoView({
      behavior: 'smooth',
      inline: 'center',
      block: 'center'
    })
  }

  // continuer validation du formulaire
  if ((adhesionActive === true && adhesionPrix !== '') || adhesionActive === false) {
    console.log('valider les autres champs du formulaire !!')
    if (event.target.checkValidity() === true) {
      // formulaire valide, formatage data pour api
      console.log('validation formulaire ok, formatage des datas !')
      const data = formaterDatas(adhesionActive, adhesionPrix)
      const body = JSON.stringify(data)
      console.log('body =', body)

      if (data.prices.length === 0) {
        // pas d'achats
        emitter.emit('message', {
          tmp: 4,
          typeMsg: 'warning',
          contenu: `Rien à valider !`
        })
      } else {
        // ---- requête "POST" achat billets ----
        const urlApi = `/api/reservations/`
        // options de la requête
        const options = {
          method: 'POST',
          body: body,
          headers: {
            'Content-Type': 'application/json'
          }
        }
        fetch(urlApi, options).then(response => {
          if (response.status !== 201) {
            throw new Error(`${response.status} - ${response.statusText}`)
          }
          return response.json()
        }).then(retour => {
          console.log('retour =', retour)
          // redirection vers stripe en conservant l'historique de navigation
          window.location.assign(retour.checkout_url)
        }).catch(function (erreur) {
          emitter.emit('message', {
            tmp: 6,
            typeMsg: 'danger',
            contenu: `Store, réservation produits erreur: ${erreur}`
          })
        })

      }
    } else {
      // formulaire non valide
      console.log('formulaire pas vailde !')
      // scroll vers l'entrée non valide et affiche un message
      const elements = event.target.querySelectorAll('input')
      for (let i = 0; i < elements.length; i++) {
        const element = elements[i]
        if (element.checkValidity() === false) {
          // console.log('element = ', element)
          element.scrollIntoView({behavior: 'smooth', inline: 'center', block: 'center'})
          element.parentNode.querySelector('.invalid-feedback').style.display = 'block'
          break
        }
      }
    }
  }

  /*

      // email": "{{$randomEmail}}", ok
      // "first_name": "{{$randomFirstName}}",
      // "last_name": "{{$randomLastName}}",
      // "phone": "{{$randomPhoneNumber}}",
      // "postal_code": "97480",
      // "birth_date": "1984-04-18",
      // "adhesion":"{{price_adhesion_plein_tarif_uuid}}


   */
}

// ---- gestion des évènements provenant des enfants ----
// mise à jour données du profil
emitter.on('emitUpdateProfil', (data) => {
  console.log('réception "emitUpdateProfil", data=', JSON.stringify(data, null, 2))
  store.formulaireBillet[store.currentUuidEvent][data.key] = data.value
})

// mise à jour données de l'adhésion
emitter.on('majAdhesion', (data) => {
  console.log('réception "majAdhesion", data=', JSON.stringify(data, null, 2))
  store.formulaireBillet[store.currentUuidEvent].adhesion[data.key] = data.value
})

emitter.on('majActiveSimpleProduct', (data) => {
  console.log('réception "majActiveSimpleProduct", data=', JSON.stringify(data, null, 2))
  store.formulaireBillet[store.currentUuidEvent].activeSimpleProduct[data.uuidProduct][data.key] = data.value
})

emitter.on('majOptionsEvent', (data) => {
  console.log('réception "majOptionsEvent", data=', JSON.stringify(data, null, 2))

  if (data.name === 'check') {
    const option = store.formulaireBillet[store.currentUuidEvent]['options'].find(obj => obj.uuid === data.uuid)
    option.activation = data.value
    console.log('option =', option)
  }
})

emitter.on('gererCardBillet', (data) => {
  console.log('réception "gererCardBillet", data=', JSON.stringify(data, null, 2))

  // stock actualisé
  const nbBillet = store.formulaireBillet[store.currentUuidEvent].identifiants[data.uuidTarif].users.length
  const stock = store.formulaireBillet[store.currentUuidEvent].identifiants[data.uuidTarif].stock
  console.log('nbBillet =', nbBillet)

  // ajouter identifiant
  if (data.action === 'ajouter') {
    if (nbBillet + 1 <= stock) {
      const id = store.formulaireBillet[store.currentUuidEvent].identifiants[data.uuidTarif].index + 1
      // store.formulaireBillet[store.currentUuidEvent].identifiants.push({id: id, uuidTarif: data.uuidTarif, prenom: '', nom: ''})
      store.formulaireBillet[store.currentUuidEvent].identifiants[data.uuidTarif].users.push({
        id: id,
        prenom: '',
        nom: ''
      })
      store.formulaireBillet[store.currentUuidEvent].identifiants[data.uuidTarif].index = id
    }
  }

  // supprimer
  if (data.action === 'supprimer') {
    const suppData = store.formulaireBillet[store.currentUuidEvent].identifiants[data.uuidTarif].users.filter(ident => ident.id !== data.id)
    store.formulaireBillet[store.currentUuidEvent].identifiants[data.uuidTarif].users = suppData
    console.log('identifiants =', store.formulaireBillet[store.currentUuidEvent].identifiants)
  }

  // modifier
  if (data.action === 'modifier') {
    //{ action: 'modifier', uuidTarif: uuidTarif, valeur: valeur, champ: champ, id: id })
    store.formulaireBillet[store.currentUuidEvent].identifiants[data.uuidTarif].users.find(ident => ident.id === data.id)[data.champ] = data.valeur
  }
})
</script>
<style>
.invalid-feedback {
  margin-top: -4px !important;
  margin-left: 4px !important;
}
</style>