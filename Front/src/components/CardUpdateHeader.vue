<template>
    <div class="page-header min-vh-50 bg-secondary" title="Cliquer moi pour ajouter/mettre à jour l'image de fond">
        {{ dataHeader }}
    </div>
</template>

<script setup>
console.log('-> CardUpdateHeader.vue');
const props = defineProps({
    dataHeader: Object
})
defineEmits(['update:dataHeader'])

</script>

<style scoped>
.page-header::after {
    content: '';
    display: block;
    background-color: chartreuse;
}
.page-header::after:hover {
    content: '';
    display: block;
    border: 1px dashed var(--bs-info);
}

</style>