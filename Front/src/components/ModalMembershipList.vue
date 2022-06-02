<template>
  <div class="modal fade" id="modal-liste-adhesion" tabindex="-1" role="dialog"
       aria-labelledby="modal-form-adhesion"
       aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered modal-xl" role="document">
      <div class="modal-content">
        <div class="modal-body p-0">
          <div class="card card-plain">
            <div class="card-header pb-0 d-flex align-items-center">
              <h3 class="font-weight-bolder text-info text-gradient align-self-start w-85">Vos adhésions</h3>
            </div>
            <div class="card-body">

              <fieldset class="shadow-sm p-3 mb-5 bg-body rounded" v-for="(product, index) in me.membership" :key="index">
                <legend>
                  <h5 class="font-weight-bolder text-info text-gradient align-self-start w-85">
                    {{ product.price_name }} - {{product.contribution_value}}€</h5>
                </legend>
                <div class="flex-column">
                  <h5>Inscription: {{ product.last_contribution }}</h5>
                  <h5>Echéance: {{ product.deadline }}</h5>
                </div>
              </fieldset>

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
import {useLocalStore} from '@/stores/local'

const {me} = storeToRefs(useLocalStore())
</script>

<style scoped>

</style>