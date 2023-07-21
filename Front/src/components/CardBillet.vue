<template>
  <div
      v-for="product in event.products.filter(prod => prod.categorie_article === 'F' || prod.categorie_article === 'B')"
      :key="product.uuid">
    <fieldset class="shadow-sm p-3 mb-5 bg-body rounded test-card-billet">
      <legend>
        <img v-if="image === true" :src="product.img" class="image-product" :alt="product.name" :style="stImage">
        <h3 v-else class="font-weight-bolder text-info text-gradient align-self-start">{{ product.name }}</h3>
        <h6 v-if="product.short_description !== null" class="text-info">{{ product.short_description }}</h6>
      </legend>
      <!-- tous les produits de type billet -->
      <div v-for="price in product.prices" :key="price.uuid" class="mt-5">
        <!-- produit ne nécessitant pas une adhésion ou déjà adhérant -->
        <section
            v-if="getProductEnable(price.adhesion_obligatoire) === true || getStateEnabledMembership(price.adhesion_obligatoire) === true">
          <!-- prix -->
          <div class="d-flex justify-content-between">
            <!-- nom tarif -->
            <h4 v-if="price.prix > 0" class="font-weight-bolder text-info text-gradient align-self-start">
              {{ price.name.toLowerCase() }} :
              {{ price.prix }} €</h4>
            <h4 v-else class="font-weight-bolder text-info text-gradient align-self-start">{{
                price.name.toLowerCase()
              }}</h4>
            <button
                v-if="stop(price.uuid, price.stock, price.max_per_user) === false"
                class="btn btn-primary ms-3 test-card-billet-bt-add"
                type="button" @click.stop="addCustomer(price.uuid)">
              <i class="fas fa-plus"></i>
            </button>

          </div>
          <!-- clients -->
          <div class="input-group mb-1 test-card-billet-input-group"
               v-for="(customer, index) in getCustomersByUuidPrix(price.uuid)" :key="index">
            <input type="text" :value="customer.last_name" placeholder="Nom" aria-label="Nom"
                   class="form-control test-card-billet-input-group-nom"
                   @keyup="updateCustomer(price.uuid, customer.uuid, $event.target.value,'last_name')" required>
            <input type="text" :value="customer.first_name" placeholder="Prénom" aria-label="Prénom"
                   class="form-control test-card-billet-input-group-prenom"
                   @keyup="updateCustomer(price.uuid, customer.uuid, $event.target.value,'first_name')" required>
            <button class="btn btn-primary mb-0" type="button" @click="deleteCustomer(price.uuid, customer.uuid)"
                    style="border-top-right-radius: 30px; border-bottom-right-radius: 30px;">
              <i class="fas fa-times"></i>
            </button>
            <div class="invalid-feedback">Donnée(s) manquante(s) !</div>
          </div>
        </section>
        <!-- produit nécessitant une adhésion -->
        <section
            v-if="getProductEnable(price.adhesion_obligatoire) === false && getStateEnabledMembership(price.adhesion_obligatoire) === false">
          <div class="">
            <!-- nom tarif -->
            <h4 class="font-weight-bolder text-dark text-gradient">{{ price.name.toLowerCase() }} :
              {{ price.prix }} €</h4>
            <div v-if="refreshToken === ''" class="ms-2 mt-0 text-info font-weight-500">
              Vous devez être connecter pour accéder à ce produit.
            </div>
            <div v-else class="ms-2 mt-0">
              <button class="btn btn-primary mb-0" type="button"
                      @click="toggleEnabledMembership(price.adhesion_obligatoire)"
                      style="border-top-right-radius: 30px; border-bottom-right-radius: 30px;">
                <span>adhérez à "{{ getNameAdhesion(price.adhesion_obligatoire) }}" pour accéder à ce produit</span>
              </button>
            </div>
          </div>
        </section>
      </div>
    </fieldset>
    <!--
    pour chaque produit [ chaque prix ]
    -->
    <div v-for="price in product.prices" :key="price.uuid" class="mt-5">
      <fieldset v-if="getStateEnabledMembership(price.adhesion_obligatoire)"
                class="shadow-sm p-3 mb-5 bg-body rounded test-card-billet">
        <!-- accepte abonnement
        <div class="input-group mb-2 has-validation d-flex flex-row align-items-center">
          <div class="form-check form-switch">
            <input class="form-check-input" type="checkbox" :id="`membership-checkbox-${price.adhesion_obligatoire}`"
                   @change.stop="toggleEnabledMembership(price.adhesion_obligatoire)"
                   checked style="height: 20px;">
            <label class="form-check-label text-dark mb-0 ms-1"
                   :for="`membership-checkbox-${price.adhesion_obligatoire}`">
              Accepter l'adhésion.
            </label>
          </div>
        </div>
        -->

        <legend>
          <div class="card-header pb-0 d-flex flex-column align-items-star">
            <h3 class="font-weight-bolder text-info text-gradient align-self-start w-85">
              {{ price.adhesionObligatoireData.name }}</h3>
            <h5 style="white-space: pre-line">{{ price.adhesionObligatoireData.short_description }}</h5>
          </div>
        </legend>
        <!-- conditions -->
        <div class="input-group mb-2 has-validation">
          <div class="form-check form-switch">
            <div>
              <input id="read-conditions-membership" class="form-check-input" type="checkbox" required
                     @change.stop="toggleEnabledMembership(price.adhesion_obligatoire)" checked="false">
              <label v-if="price.adhesionObligatoireData.categorie_article === 'A'"
                     class="form-check-label text-dark" for="read-conditions-membership">
                J'ai pris connaissance des <a class="text-info" @click="goStatus()">statuts, du règlement
                intérieur de l'association</a> et j'accepte cette adhésion.
              </label>
              <label v-else class="form-check-label text-dark" for="read-conditions">
                J'ai pris connaissance des <a class="text-info" @click="goStatus()">CGU/CGV</a> et j'accepte cette
                adhésion.
              </label>
            </div>
          </div>
          <div class="invalid-feedback">Conditions non acceptées.</div>
        </div>

        <!--
        prix
        clique sur prix  = fonc updateSelectPrice => forms[index event].memberships[uuid adhesion].prixSelectionner = prix
        nom/prenom/tel/codePostal @keyup="upddate input $event
        -->
        <div class="input-group mb-2 has-validation">
          <div :id="`adesion-price-parent${index}`" class="col form-check mb-2"
               v-for="(prix, indexPrix) in price.adhesionObligatoireData.prices" :key="indexPrix">
            <input v-if="indexPrix === 0" :value="prix.uuid"
                   class="form-check-input input-adesion-modal-price" type="radio"
                   name="prixAdhesionModal" :id="`adhesion-price-radio${indexPrix}`"
                   required>
            <input v-else :value="prix.uuid"
                   class="form-check-input input-adesion-modal-price" type="radio"
                   name="prixAdhesionModal" :id="`adhesion-price-radio${indexPrix}`">
            <label class="form-check-label" :for="`adhesion-price-radio${indexPrix}`">
              {{ prix.name }} - {{ prix.prix }}€
            </label>
            <div v-if="index === 0" class="invalid-feedback">
              Merci de choisir un tarif.
            </div>
          </div>
        </div>

        <!-- Nom / Prénom -->
        <div class="input-group has-validation mb-1 test-card-billet-input-group">
          <input type="text" value="" placeholder="Nom" aria-label="Nom"
                 class="form-control test-card-billet-input-group-nom-membership" required>
          <input type="text" value="" placeholder="Prénom" aria-label="Prénom"
                 class="form-control test-card-billet-input-group-prenom-membership" required>
          <div class="invalid-feedback">Donnée(s) manquante(s) !</div>
        </div>
        <!-- Code postal / Fixe ou Mobile -->
        <div class="input-group has-validation mb-1 test-card-billet-input-group">
          <input type="text" value="" placeholder="Code postal" aria-label="Code postal"
                 class="form-control test-card-billet-input-group-nom-codepostal-membership" required>
          <input type="text" value="" placeholder="Fixe ou Mobile" aria-label="Fixe ou Mobile"
                 class="form-control test-card-billet-input-group-tel-membership" required>
          <div class="invalid-feedback">Donnée(s) manquante(s) !</div>
        </div>
      </fieldset>
    </div>
  </div>
</template>

<script setup>
console.log('-> CardBillet.vue')

// store
import { storeToRefs } from 'pinia'
import { useEventStore } from '@/stores/event'
import { useLocalStore } from '@/stores/local'
import { useAllStore } from '@/stores/all'

// attributs/props
const props = defineProps({
  image: Boolean,
  styleImage: Object,
})

let stImage = ''
// valeurs par défaut
if (props.styleImage === undefined) {
  stImage = {
    height: '20px',
    width: 'auto'
  }
} else {
  stImage = props.styleImage
}

// state
const { event } = storeToRefs(useEventStore())
const { place, getNameAdhesion } = storeToRefs(useAllStore())
// action(s) du state
const {
  getCustomersByUuidPrix,
  addCustomer,
  updateCustomer,
  deleteCustomer,
  stop,
  getProductEnable,
  toggleEnabledMembership,
  getStateEnabledMembership
} = useEventStore()
// action state
const { refreshToken, me } = storeToRefs(useLocalStore())

</script>

<style scoped>
</style>