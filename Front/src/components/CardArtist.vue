<template>
  <a @click="goArtistPage(artist.slug)">
    <div class="card card-background">
      <div class="full-background" :style="{ backgroundImage: getBackgroundImage() }"></div>
      <div class="card-body pt-12">
        <h4 class="text-white text-decoration-underline-hover">{{ artist.organisation }}</h4>
        <p v-if="artist.long_description !== null"> {{ artist.long_description }}</p>
        <p v-if="artist.long_description === null && artist.short_description !== null"> {{
            artist.short_description
          }}</p>
      </div>
    </div>
  </a>
</template>

<script setup>
// vue
import {useRouter} from 'vue-router'

const props = defineProps({
  dataArtist: Object
})

const router = useRouter()
const domain = `${location.protocol}//${location.host}`
const artist = props.dataArtist.configuration
console.log('artist =', artist)

const getBackgroundImage = () => {
  if (artist.img_variations.med === undefined) {
    return `url('${domain}/media/images/image_non_disponible.svg')`
  } else {
    return `url('${domain + artist.img_variations.med}')`
  }
}

function goArtistPage(slugArtist) {
  console.log('-> goArtistPage, slugArtist =', slugArtist)
  router.push({name: 'Artist', params: {slug: slugArtist}})
}

</script>

<style scoped>

</style>