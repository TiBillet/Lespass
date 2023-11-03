<template>
    <div class="d-flex flex-row justify-content-start bg-dark text-white">
        <div class="ms-1">{{ name }}</div>
    </div>
    <div v-for="(item, index) in list" :key="index" class="d-flex flex-column text-dark border-bottom">
        <div class="d-flex flex-row text-dark">
        <div class="tibillet-prod-name">{{ item.name }}</div>
        <div class="tibillet-prod-short-description">{{ item.short_description }}</div>
        <div class="tibillet-prod-menu">
            <font-awesome-icon icon="fa-solid fa-caret-down" class="tibillet-action-icon-header fs-4 align-self-end me-2"
        data-toggle="tooltip" data-placement="top" title="Plus d'infos." />
        </div>
        <div :id="`tibillet-prod-${uuidComponent}-${index}`" class="d-flex flex-row text-dark">

        </div>
    </div>
    </div>
</template>

<script setup>
import { v4 as uuidv4 } from 'uuid'

const props = defineProps({
    list: Array,
    name: String,
    show: Boolean
})
const uuidComponent = uuidv4()


function toggleShowAllInfosProduct(selector) {
    document.querySelector(selector).style.display = 'flex'
}

</script>

<style scoped></style>