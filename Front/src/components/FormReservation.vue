<template>
  <section>
    <div class="container py-4">
      <div class="row">
        <div class="col-lg-7 mx-auto d-flex justify-content-center flex-column">
          <h3 class="text-center">Réservation</h3>

          <form @submit.prevent="validerReservation">
            <div class="card-body">
              <div class="row">

                <!-- email -->
                <fieldset class="col-md-12 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
                  <legend>Email</legend>
                  <div class="mb-4">
                    <label for="email">Adresse</label>
                    <div class="input-group">
                      <input id="email" type="email" class="form-control" placeholder="" >
                    </div>
                  </div>

                  <div class="mb-4">
                    <label for="email-confirmation">Confirmation adresse</label>
                    <div class="input-group">
                      <input id="email-confirmation" type="email" class="form-control" placeholder="" >
                    </div>
                  </div>


                  <p class="mb-4 text-warning">
                    Cette adresse email vous permet de recevoir votre(vos) billet(s),
                    si celle-ci comporte une erreur vous n'aurez pas votre(vos) billet(s).
                    <div class="col-md-12">
                      <div class="form-check form-switch">
                        <input class="form-check-input" type="checkbox" id="valid-email">
                        <label class="form-check-label text-dark" for="valid-email">Prise en compte du message si-dessus.</label>
                      </div>
                    </div>
                  </p>
                </fieldset>

                <!-- Position -->
                <fieldset class="col-md-12 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
                   <legend>Position</legend>
                  <div class="row mb-4">
                    <div class="col-md-2">
                      <div class="form-check">
                        <input class="form-check-input" type="radio" name="position" id="position1">
                        <label class="form-check-label" for="position1">Fosse</label>
                      </div>
                    </div>
                    <div class="col-md-2">
                      <div class="form-check">
                        <input class="form-check-input" type="radio" name="position" id="position2" checked>
                        <label class="form-check-label" for="position2">Gradin</label>
                      </div>
                    </div>
                  </div>
                </fieldset>

                <!-- adhésion -->
                <fieldset class="col-md-12 mb-4 shadow-sm p-3 mb-5 bg-body rounded">
                  <legend>Adhésion</legend>
                  <div class="form-check form-switch">
                    <input class="form-check-input" type="checkbox" id="changer-etat-adhesion" @click="adhesionIsActive = !adhesionIsActive">
                    <label class="form-check-label text-dark" for="changer-etat-adhesion">Prendre une adhésion associative.</label>
                  </div>

                  <div v-if="adhesionIsActive">
                    <div class="input-group mb-3" style="width: 200px">
                      <button class="btn btn-primary mb-0 " type="button" id="button-add-adhesion"><i class="fas fa-plus"></i></button>
                      <input id="nb-adhesion" type="text" class="form-control text-center" placeholder="" aria-label="input adhésion" aria-describedby="input adhésion">
                      <button class="btn btn-primary mb-0" type="button" id="button-del-adhesion"><i class="fas fa-minus"></i></button>
                    </div>

                    <!-- nom/prénom -->
                    <div class="row">
                      <div class="col-md-6">
                        <label for="adhesion-nom">Nom</label>
                        <div class="input-group mb-4">
                          <input id="adhesion-nom" class="form-control" placeholder="" aria-label="Nom pour l'adhésion" type="text" >
                        </div>
                      </div>
                      <div class="col-md-6 ps-2">
                        <label for="adhesion-prenom">Prénom</label>
                        <div class="input-group">
                          <input id="adhesion-prenom" type="text" class="form-control" placeholder="" aria-label="Prénom pour l'adhésion" >
                        </div>
                      </div>
                    </div>
                  </div>
                </fieldset>

                <!-- Billet(s) -->
                <ProductsList :products-data="productsData" />

                <div class="col-md-12">
                  <button type="submit" class="btn bg-gradient-dark w-100">Valider la réservation</button>
                </div>

              </div>
            </div>
          </form>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup="">
  console.log('-> FormReservation.vue')
  // console.log('context =', context)
  import { ref, onMounted } from 'vue'

  // composants
  import ProductsList from './ProductsList.vue'

  // attributs/props
  const props = defineProps({
    currentEvent: Object
  })

  let adhesionIsActive = ref(false)

  let productsData = {
    products: props.currentEvent.products,
    eventUuid: props.currentEvent.uuid
  }


  function verifierEtatAdhesion(event) {
    if (event.target.checked === true) {
      adhesionIsActive = true
    } else {
      adhesionIsActive = false
    }
    console.log('event.target.checked =', event.target.checked)
  }
  onMounted(() =>{
    console.log('rendu ok !')

  })

  function validerReservation() {
    console.log('Validation de la réservation !')
  }
</script>