<template>

  <section v-if="chargement">
    <div class="position-relative d-flex justify-content-center align-items-center vw-100 vh-100">
      <h1>Chargement des données !</h1>
      <div class="position-absolute d-flex justify-content-center align-items-center vw-100 vh-100">
        <div class="spinner-border text-success" role="status" style="width: 10rem; height: 10rem;"></div>
      </div>
    </div>
  </section>
  <section v-if="!chargement">
    <Header :data-header="getDataHeader()"/>
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
    <div class="container mt-5" v-for="produit in tabProduits" :key="produit.uuid">
      <div class="row">
        <CardBillet v-if="produit.categorie_article === 'B'" :data-product="produit" :uuid-event="currentEvent.uuid"/>
      </div>
    </div>
  </section>

</template>

<script setup>
// vue
import {ref} from 'vue'
import {useStore} from 'vuex'
import {useRoute} from 'vue-router'

// composants
import Header from '../components/Header.vue'
import CardPlace from '../components/CardPlace.vue'
import CardArtist from '../components/CardArtist.vue'
import CardBillet from '../components/CardBillet.vue'

let chargement = ref(true)

const store = useStore()
const route = useRoute()
const slug = route.params.slug

// récupération du uuid évènement à partir du slug
const uuidEvent = store.state.events.find(evt => evt.slug === slug).uuid

// init formulaire si n'existe pas
if (store.state.formulaireBillet[uuidEvent] === undefined) {
  store.commit('initFormulaireBillet', uuidEvent)
}

// récupère l'évènement à jour
let currentEvent = store.getters.getEventBySlug(slug)

const domain = `${location.protocol}//${location.host}`

// convertion du proxy en array
let produits = JSON.parse(JSON.stringify(store.state.products))

let tabProduits = []
for (let index in currentEvent.products) {
  let uuidProd = currentEvent.products[index]
  let produit = produits.find(prod => prod.uuid === uuidProd)
  tabProduits.push(produit)
}

// chargement de l'évènement
const urlApi = `/api/events/${uuidEvent}`
// console.log('urlApi =', urlApi)
fetch(domain + urlApi).then(response => {
  if (!response.ok) {
    throw new Error(`${response.status} - ${response.statusText}`)
  }
  return response.json()
}).then(retour => {
  // console.log('retour event =', retour)
  store.commit('updateEvent', retour)
  chargement.value = false

}).catch(function (erreur) {
  emitter.emit('message', {
    tmp: 4,
    typeMsg: 'danger',
    contenu: `Chargement de l'évènement ${uuidEvent}, erreur: ${erreur}`
  })
})

function getDataHeader() {
  return {
    urlImage: currentEvent.img_variations.med,
    shortDescription: currentEvent.short_description,
    longDescription: currentEvent.long_description,
    titre: currentEvent.name,
    domain: domain
  }
}

function getDataCardPlace() {
  return {
    urlImage: store.state.place.img_variations.med,
    titre: store.state.place.organisation,
    lonDescription: store.state.place.long_description,
    shortDescription: store.state.place.short_description
  }
}

emitter.on('goValiderAchat', (form) => {
  console.log('-> goValiderAchat form =', form)
  console.clear()
  if (form.checkValidity() === false) {
    // lance le test de validation du formulaire (méthode bootstrap)
    form.classList.add('was-validated')
  } else {
    // rendre le cham input '#email-confirmation' invalid si les emails sont différents
    if (store.state.formulaireBillet[uuidEvent].email !== store.state.formulaireBillet[uuidEvent].confirmeEmail) {
      document.querySelector('#email-confirmation').classList.add('is-invalid')
    } else {
      // Validation du formulaire ok
      console.log('Validation du formulaire ok !')
      document.querySelector('#email-confirmation').classList.remove('is-invalid')
      form.classList.remove('was-validated')
      // requête reservation/achat dd@hh.fr
      let data = {
        event: currentEvent.uuid,
        email: store.state.formulaireBillet[currentEvent.uuid].email,
        position: store.state.formulaireBillet[currentEvent.uuid].position
      }
      // données adhésion
      if (store.state.formulaireBillet[currentEvent.uuid].adhesion === true) {
        data.adhesion = {
          nom: store.state.formulaireBillet[currentEvent.uuid].adhesionInfos.nom,
          prenom: store.state.formulaireBillet[currentEvent.uuid].adhesionInfos.prenom,
          adresse: store.state.formulaireBillet[currentEvent.uuid].adhesionInfos.adresse,
          tel: store.state.formulaireBillet[currentEvent.uuid].adhesionInfos.tel
        }
      }
      let identifiants = store.state.formulaireBillet[currentEvent.uuid].identifiants
      // console.log('identifiants =', identifiants)
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
      console.log('data =', JSON.stringify(data, null, 2))
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

        console.log(`-> achète le(s) prodruit(s), ${urlApi} !`)
        console.log('options =', JSON.stringify(options, null, 2))
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
    }
  }
})


</script>

<style scoped>

</style>