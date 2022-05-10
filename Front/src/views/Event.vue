<template>
  <Loading v-if="loading"/>
  <p v-if="error">{{ error.message }}</p>
  <Header v-if="Object.entries(event).length > 0" :header-event="getEventHeader()"/>
  <div v-if="Object.entries(event).length > 0" class="container mt-7">

    <!-- artistes -->
    <div v-for="(artist, index) in event.artists" :key="index">
      <CardArtist :data-artist="artist" class="mb-6"/>
    </div>


    <form @submit.prevent="goValiderAchats($event)" class="needs-validation" novalidate>
      <!-- sans attribut "image" le nom du billet est affiché -->
      <CardBillet :image="true" :style-image="styleImage" />

      <!--
      <CardProducts :products="currentEvent.products" :categories="['B', 'F']"/>

      <CardOptions :options="options"  :index-memo="store.currentUuidEvent"/>

       index-memo="unique00" = "index fixe" bon pour tous les évènements
      <CardEmail :default-email="storeLocalGet('email')" index-memo="unique00"/>

      <CardProducts :products="currentEvent.products" :categories="['A', 'D']"/>

      <button type="submit" class="btn bg-gradient-dark w-100">Valider la réservation</button>
-->
    </form>


  </div>

</template>

<script setup>
// console.clear()
console.log('-> Event.vue !')

// vue
import {useRoute} from 'vue-router'

// store
import {storeToRefs} from 'pinia'
// import {useStore} from '@/store'
import {useEventsStore} from '@/stores/events'

const {event, loading, error} = storeToRefs(useEventsStore())
const {getEventBySlug} = useEventsStore()

// composants
import Loading from '@/components/Loading.vue'
import Header from '@/components/Header.vue'
import CardArtist from '@/components/CardArtist.vue'
import CardBillet from '@/components/CardBillet.vue'

// const store = useStore()
const route = useRoute()
const slug = route.params.slug

const styleImage = {
  height: '30px',
  width: 'auto'
}

// current event
getEventBySlug(slug)

function getEventHeader() {
  // console.log('-> fonc getHeaderEvent, event =', event)
  const domain = `${location.protocol}//${location.host}`
  let urlImage
  try {
    urlImage = event.value.img_variations.fhd
  } catch (e) {
    urlImage = `${domain}/media/images/image_non_disponible.svg`
  }
  // console.log('urlImage =', urlImage)
  return {
    urlImage: urlImage,
    shortDescription: event.value.short_description,
    longDescription: event.value.long_description,
    titre: event.value.name
  }
}


/*
// vue
import {ref} from 'vue'
import {useRoute} from 'vue-router'


// myStore
import {storeLocalGet, storeLocalSet} from '@/storelocal'

// composants
import Header from '@/components/Header.vue'
import CardPlace from '@/components/CardPlace.vue'
import CardArtist from '@/components/CardArtist.vue'
import CardEmail from '@/components/CardEmail.vue'
import CardProducts from '@/components/CardProducts.vue'
import CardOptions  from '@/components/CardOptions.vue'

// test dev
// import {fakeEvent} from "../../tests/fakeCurrentEventTest"
// import {fakeEvent} from "../../tests/fakeCurrentEventTestNoArtists.js"
// import {fakeEvent} from "../../tests/fakeSimpleCurrentEventRaffinerie.js"

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
// const currentEvent = fakeEvent

console.log('currentEvent =', currentEvent)


// TODO: maj currentEvent et ses store.memoComposants[composant][currentUuidEvent] provenant d'un websocket

// un objet options contenant les checkbox et radio
const options = {
  checkbox: currentEvent.options_checkbox,
  radio: currentEvent.options_radio
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
  const optionsCheckbox = store.memoComposants.Options[store.currentUuidEvent].checkbox
  for (let i = 0; i < optionsCheckbox.length; i++) {
    const option = optionsCheckbox[i]
    // console.log('-> ',JSON.stringify(option, null, 2))
    if (option.activation === true) {
      data.options.push(option.uuid)
    }
  }

  // options radio
  const optionsRadio = store.memoComposants.Options[store.currentUuidEvent].radio
  for (let i = 0; i < optionsRadio.length; i++) {
    const option = optionsRadio[i]
    if (option.selection === true) {
      data.options.push(option.uuid)
    }
  }

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

  // vérifier email
  const email = document.querySelector('#profil-email')
  if (email.checkValidity() === false) {
    email.parentNode.querySelector(`.invalid-feedback`).style.display = 'block'
    email.scrollIntoView({behavior: 'smooth', inline: 'center', block: 'center'})
  } else {
    email.parentNode.querySelector(`.invalid-feedback`).style.display = 'none'
  }
  const confirmEmail = document.querySelector('#profil-confirme-email')
  if (email.value !== confirmEmail.value) {
    confirmEmail.parentNode.querySelector(`.invalid-feedback`).style.display = 'block'
    confirmEmail.setCustomValidity('erreur')
    confirmEmail.scrollIntoView({behavior: 'smooth', inline: 'center', block: 'center'})
  } else {
    confirmEmail.parentNode.querySelector(`.invalid-feedback`).style.display = 'none'
    confirmEmail.setCustomValidity('')
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
          if (response.status !== 201 && response.status !== 400) {
            throw new Error(`${response.status} - ${response.statusText}`)
          }
          return response.json()
        }).then(retour => {
          console.log('retour =', retour)
          if (retour.checkout_url !== undefined) {
            // icon de chargement
            emitter.emit('statusLoading', true)
            // redirection vers stripe en conservant l'historique de navigation
            window.location.assign(retour.checkout_url)
          } else {
            let contenuMessage = ''
            for (const key in retour) {
              for (let i = 0; i < retour[key].length; i++) {
                contenuMessage += `<h3>- ${retour[key][i]}</h3>`
              }
            }
            emitter.emit('modalMessage', {
              titre: 'Information',
              dynamique: true,
              contenu: contenuMessage
            })
          }
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
 */
</script>
<style>
.invalid-feedback {
  margin-top: -4px !important;
  margin-left: 4px !important;
}
</style>