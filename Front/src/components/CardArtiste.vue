<template>

  <!-- Start Card Blog Fullbackground - text centered -->
  <a href="javascript:;">
    <div class="card card-background">
      <div class="full-background" style="background-image: url('../../assets/img/bg1.jpg')"></div>
      <div class="card-body pt-12">
        <h4 class="text-white text-decoration-underline-hover">Ability to Focus</h4>
        <p>Why would anyone pick blue over pink? Pink is obviously a better color. Everyone’s born confident, and
          everything’s taken away from you</p>
      </div>
    </div>
  </a>
  <!-- End Card Blog Fullbackground - text centered -->

</template>

<script setup>
const props = defineProps({
  dataArtist: Object
})

console.log('dataArtist =', props.dataArtist)
</script>

<style scoped>

</style>