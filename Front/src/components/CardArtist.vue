<template>
  <div class="card card-background">
    <div class="full-background" :style="{ backgroundImage: getBackgroundImage() }"></div>
    <div class="card-body pt-12">
      <h4 class="text-white" role="heading" :aria-label="artist.organisation">{{ artist.organisation }}</h4>
      <p v-if="artist.long_description !== null"> {{ artist.long_description }}</p>
      <p v-if="artist.long_description === null && artist.short_description !== null">
        {{ artist.short_description }}</p>
    </div>
  </div>
  <div></div>
</template>

<script setup>
// console.log('-> CardArtist.vue')
const props = defineProps({
  artist: Object
})

const domain = `${location.protocol}//${location.host}`
const getBackgroundImage = () => {
  if (props.artist.img_variations.fhd === undefined) {
    return `url('${domain}/media/images/image_non_disponible.svg')`
  } else {
    return `url('${domain + props.artist.img_variations.fhd}')`
  }
}
</script>

<style scoped></style>