<template>
  <header>
    <div class="page-header min-vh-50" :style="{ backgroundImage: getBackgroundImage(), maxHeight: `365px` }">
      <span class="mask bg-dark opacity-8"></span>
      <div class="container">
        <div class="row">
          <div class="col-lg-8 mx-auto text-white text-center">
            <h2 class="text-white">{{ dataHeader.titre }}</h2>
            <p v-if="dataHeader.longDescription === null && dataHeader.shortDescription !== null" class="lead">{{ dataHeader.shortDescription }}</p>
            <p v-if="dataHeader.longDescription !== null" class="lead">{{ dataHeader.longDescription }}</p>
          </div>
        </div>
      </div>
    </div>
    <!-- search -->
    <div class="container">
      <div class="row bg-white shadow mt-n5 border-radius-lg pb-4 p-3 position-relative w-75 mx-auto">
        <div class="col-lg-8 mt-lg-n2 mt-2">
          <label>Rechercher</label>
          <div class="input-group">
            <span class="input-group-text"><i class="fas fa-search" aria-hidden="true"></i></span>
            <input class="form-control" placeholder="Rechercher for category" type="text">
          </div>
        </div>
        <div class="col-lg-4 d-flex align-items-center mt-lg-auto mt-2">
          <button type="button" class="btn bg-gradient-primary w-100 mb-0">Rechercher</button>
        </div>
      </div>

    </div>
  </header>
</template>

<script setup>
  console.log('-> Header.vue')
  const props = defineProps({
    dataHeader: Object
  })

  const getBackgroundImage = () => {
    if (props.dataHeader.urlImage === undefined) {
      return `url('${props.dataHeader.domain}/media/images/image_non_disponible.svg')`
    } else {
      return `url('${ props.dataHeader.domain + props.dataHeader.urlImage }')`
    }
  }
  console.log('props =', props)
</script>
