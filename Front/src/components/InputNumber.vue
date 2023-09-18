<template>
  <div v-if="button" class="input-group mb-2 rounded-right" style="width: 30%;">
    <button class="btn btn-primary mb-0" type="button" role="button" :aria-label="`Supprimer une unité '${price.name}'`"
            @click="price.qty <= parseInt(min) ? price.qty = parseInt(min) : price.qty--">
      <i class="fa fa-minus" aria-hidden="true"></i>
    </button>
    <input type="number" class="form-control text-center" :placeholder="price.qty"
           role="textbox" :aria-label="infoAria" v-model="price.qty"
           @keydown="numOnly($event)" @keyup="limit($event, max)" required>
    <button class="btn btn-primary mb-0 app-rounded-right-20" type="button" role="button"
            :aria-label="`Ajouter une unité '${price.name}'`"
            @click="price.qty > (parseInt(max) - 1) ? price.qty = price.qty : price.qty++">
      <i class="fa fa-plus" aria-hidden="true"></i>
    </button>
    <div class="input-group-append invalid-feedback app-rounded-right-20">Pas de valeur.</div>
  </div>
  <div v-else class="input-group mb-2" style="width: 30%;">
    <!-- <input type="number" class="form-control text-center rounded-right" :placeholder="price.qty" -->
    <input type="number" class="form-control text-center app-rounded-right-20" :placeholder="price.qty"
           role="textbox" :aria-label="infoAria" v-model="price.qty"
           @keydown="numOnly($event)" @keyup="limit($event, max)" required>
    <div class="invalid-feedback" role="heading" aria-label="Pas de valeur.">Pas de valeur.</div>
  </div>
</template>

<script setup>
const props = defineProps({
  price: Object,
  max: Number,
  min: Number,
  infoAria: String,
  button: Boolean
})

if (props.max === undefined ) {
  max = 1000
}
let oldValue = props.price.qty

function numOnly (evt) {
  // chiffres seulement
  const test = evt.key.match(/[a-z]/i)
  // modification possible
  const test2 = ['Backspace', 'ArrowRight', 'ArrowLeft'].includes(evt.key)
  if (test !== null && test2 === false) {
    evt.preventDefault()
  }
  oldValue = parseInt(evt.target.value)
}

function limit (evt, max) {
  const value = parseInt(evt.target.value)
  if (value > max ) {
    evt.target.value = oldValue
  }

  if ( value < 0) {
    evt.target.value = 0
  }

}
</script>

<style>
/* Chrome, Safari, Edge, Opera : take off the arrows */
input::-webkit-outer-spin-button,
input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

/* Firefox : take off the arrows */
input[type=number] {
  -moz-appearance: textfield;
}
</style>