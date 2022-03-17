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
  </div>
  <!-- achats -->
  <div class="container mt-5">
    <div class="row">
      <form @submit.prevent="goValiderAchats($event)" class="needs-validation" novalidate>

        <CardProfil :infos="store.formulaireBillet[uuidEvent]"/>
        <CardProducts :products="currentEvent.products" :categories="['A', 'D']"/>
        <CardOptions/>
        <CardProducts :products="currentEvent.products" :categories="['B', 'F']"/>
        <div class="col-md-12 col-lg-9">
          <button type="submit" class="btn bg-gradient-dark w-100">Valider la réservation</button>
        </div>
      </form>
    </div>
  </div>

</template>

<script setup>
console.clear()
console.log('-> Event.vue !')

// vue
import {ref} from 'vue'
import {useRoute} from 'vue-router'

// composants
import Header from '@/components/Header.vue'
import CardPlace from '@/components/CardPlace.vue'
import CardArtist from '@/components/CardArtist.vue'
import CardProfil from "@/components/CardProfil.vue"
import CardProducts from "@/components/CardProducts.vue"
import CardOptions from "@/components/CardOptions.vue"

// test dev
import {getMe} from '@/api'
import {fakeEvent} from "../../tempo/fakeCurrentEventsTest"

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
// const currentEvent = fakeEvent

console.log('currentEvent =', currentEvent)

store.currentUuidEvent = uuidEvent

// init mémoristation formulaire en fonction de l'évènement en cours
if (store.formulaireBillet[store.currentUuidEvent] === undefined) {
  store.formulaireBillet[store.currentUuidEvent] = {
    attentionEmail: false,
    email: '',
    confirmeEmail: ''
  }
}

// populate profil card if user connected
console.log('store.user.refreshToken =', store.user.refreshToken)
if (store.user.refreshToken !== '') {
  store.formulaireBillet[uuidEvent].attentionEmail = true
  store.formulaireBillet[uuidEvent].email = store.user.email
  store.formulaireBillet[uuidEvent].confirmeEmail = store.user.email
}

function getHeaderEvent() {
  let urlImage
  if (currentEvent.img_variations.med === undefined) {
    urlImage = `${domain}/media/images/image_non_disponible.svg`
  } else {
    urlImage = currentEvent.img_variations.med
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

function goValiderAchats(event) {
  console.log('-> fonc goValiderAchats !')

  // efface tous les messages d'invalidité
  const msgInvalides = event.target.querySelectorAll('.invalid-feedback')
  for (let i = 0; i < msgInvalides.length; i++) {
    msgInvalides[i].style.display = 'none'
  }

  // vérifier prix adhésion (.adhesion.adhesion = uuid prix)
  let prixAdhesionOk = true
  if (document.querySelector(`#prices-parent`)) {
    document.querySelector(`#prices-parent .invalid-feedback`).style.display = 'none'
  }
  console.log('-> prix adhésion =', store.formulaireBillet[store.currentUuidEvent].adhesion.adhesion)
  if (store.formulaireBillet[store.currentUuidEvent].adhesion.adhesion === undefined && store.formulaireBillet[store.currentUuidEvent].adhesion.activation === true) {
    prixAdhesionOk = false
    document.querySelector(`#prices-parent .invalid-feedback`).style.display = 'block'
    document.querySelector(`#prices-parent`).scrollIntoView({behavior: 'smooth', inline: 'center', block: 'center'})
  }

  if (prixAdhesionOk === true) {
    if (event.target.checkValidity() === true) {
      // formulaire valide
      console.log('validation formulaire ok !!')

      const data = {
        event: store.currentUuidEvent,
        email: store.formulaireBillet[store.currentUuidEvent].email,
        prices: []
      }
      // ---- détermine les prix/users pour les billets('B') ----
      const dataPrices = store.formulaireBillet[store.currentUuidEvent].identifiants
      for (const key in dataPrices) {
        const infos = dataPrices[key]
        console.log('key =', key)
        console.log('infos =', infos)
        const obj = {
          uuid: key,
          qty: infos.users.length,
          customers: []
        }
        for (let i = 0; i < infos.users.length; i++) {
          const info = infos.users[i]
          console.log('->', info)
          obj.customers.push({first_name: info.prenom, last_name: info.nom})
        }
        console.log('obj =', JSON.stringify(obj, null, 2))

        // prix enregistré si quantité supérieure à 0
        if (infos.users.length > 0) {
          data.prices.push(obj)
        }
      }
      console.log('data =', JSON.stringify(data, null, 2))

      /*
    email": "{{$randomEmail}}", ok
    "first_name": "{{$randomFirstName}}",
    "last_name": "{{$randomLastName}}",
    "phone": "{{$randomPhoneNumber}}",
    "postal_code": "97480",
    "birth_date": "1984-04-18",
    "adhesion":"{{price_adhesion_plein_tarif_uuid}}"
     */
      // gère l'adhésion
      if(store.formulaireBillet[store.currentUuidEvent].adhesion.activation === true) {

      }


    } else {
      // formulaire non valide
      console.log('formulaire pas vailde !')
      // scroll vers l'entrée non valide et affiche un message
      const elements = event.target.querySelectorAll('input')
      for (let i = 0; i < elements.length; i++) {
        const element = elements[i]
        if (element.checkValidity() === false) {
          console.log('element = ', element)
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
    store.formulaireBillet[store.currentUuidEvent]['options'][data.uuid] = data.value
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