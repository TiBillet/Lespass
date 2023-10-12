<template>
    <div class="row bg-white shadow mt-n5 border-radius-lg pb-4 p-3 position-relative w-75 mx-auto">
        <div class="col-lg-8 mt-lg-n2 mt-2">
            <label></label>
            <div class="input-group">
                <span class="input-group-text">
                    <font-awesome-icon :icon="faMagnifyingGlass" />
                </span>
                <input v-model.lazy="research" class="form-control" placeholder="Rechechez un évènement" type="text" />
            </div>
        </div>
        <div class="col-lg-4 d-flex align-items-center mt-lg-auto mt-2">
            <button type="button" class="btn bg-gradient-primary w-100 mb-0">Rechercher</button>
        </div>
    </div>
</template>

<script setup>
let research = ''
// Le composant "font-awesome-icon" est importé globallement dans main.js
// import specific icons
import { faMagnifyingGlass } from '@fortawesome/free-solid-svg-icons'
</script>

<style></style>