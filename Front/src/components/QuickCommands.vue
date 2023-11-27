<template>
	<h1>QuickCommands</h1>
	{{ user }}
	<input type="checkbox" :checked="etat">
</template>

<script setup>
const props = defineProps({
	user: String,
	etat: Boolean
})
</script>

<style></style>