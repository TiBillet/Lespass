<template>
  <input type="file" id="tibillet-input-file-header" style="display: none">
  <div class="tibillet-header-event bg-secondary text-white" :style="styleHeader" style="height: 250px;">
    <div class="tibillet-load-image-header-event d-flex">
      <div class="container d-flex flex-column justify-content-center align-items-center">

        <!-- name -->
        <h2 class="text-white tibillet-toggle-edit" data-toggle-edit-target="name" role="heading"
          :aria-label="`Titre de l'évènement : ` + header.name" @click="toggleEdit($event)" style="cursor: pointer;">
          {{ header.name }}
        </h2>
        <input type="text" class="h2 text-dark bg-transparent tibillet-toggle-edit" data-toggle-edit-target="name"
          :placeholder="header.name" @blur="toggleEdit($event)"
          @keyup.enter.prevent="toggleEdit($event, header, 'name', true)">

        <!-- short_description -->
        <p v-if="header.short_description !== null" class="text-white tibillet-toggle-edit"
          data-toggle-edit-target="short_description" style="white-space: pre-line" @click="toggleEdit($event)">
          {{ header.short_description }}</p>
        <input type="text" class="tibillet-toggle-edit" data-toggle-edit-target="short_description"
          :placeholder="header.short_description" @blur="toggleEdit($event)"
          @keyup.enter.prevent="toggleEdit($event, header, 'short_description', true)">

      </div>
      <font-awesome-icon icon="fa-solid fa-folder" class="tibillet-action-icon-header text-white fs-3 align-self-end me-2"
        data-toggle="tooltip" data-placement="top" title="Sélectionner l'image de fond." />
      <font-awesome-icon icon="fa-solid fa-image" class="tibillet-action-icon-header text-white fs-3 align-self-end"
        data-toggle="tooltip" data-placement="top" title="Ajouter / modifier l'image de fond."
        @click="fakeClick('#tibillet-input-file-header')" />
    </div>
  </div>
  <div class="container mt-1 text-dark w-100" style="height: 100px;">
    <!-- longue description -->
    <p class="tibillet-toggle-edit" data-toggle-edit-target="long_description" @click="toggleEdit($event)"
      style="white-space: pre-line;">
      {{ header.long_description }}
    </p>
    <textarea type="text" class="tibillet-toggle-edit" data-toggle-edit-target="long_description"
      @blur="toggleEdit($event)" @keyup.enter.prevent="toggleEdit($event, header, 'long_description', true)">
      {{ header.long_description }}
      </textarea>
  </div>
</template>

<script setup>
console.log('-> CardUpdateHeader.vue');
import { computed, ref, onMounted, onUnmounted } from "vue"

const props = defineProps({
  modelValue: Object
})
defineEmits(['update:modelValue'])


const header = computed({  // Use computed to wrap the object
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

let styleHeader = ref({
  backgroundImage: "url('')",
  backgroundRepeat: "no-repeat"
})

/**
 * Simule un clique sur un élément donné
 * @param {String} selector - sélecteur css 
 */
function fakeClick(selector) {
  document.querySelector(selector).click()
}

/**
 * Cache un élement et affiche un input pour l'éditer le contenu de celui-ci
 * et enfin le réaffiche avec le nouveau contenu.
 * @param {Object} evt - évènement 
 * @param {Object} obj - varaible à mettre à jour
 * @param {Boolean} state - true = toggleEdit est appelé après que la touche entrée est été appuyée 
 */
function toggleEdit(evt, obj, key, state) {
  evt.preventDefault()
  const element = evt.target
  const commun = element.getAttribute('data-toggle-edit-target')
  let input = null, text = null
  element.style.display = "none"
  console.log('element.tagName =', element.tagName)
  if (element.tagName !== "INPUT" && element.tagName !== "TEXTAREA") {
    input = document.querySelector(`input[class~="tibillet-toggle-edit"][data-toggle-edit-target="${commun}"]`)
    if (input === null) {
      input = document.querySelector(`textarea[class~="tibillet-toggle-edit"][data-toggle-edit-target="${commun}"]`)
    }
    input.style.display = "flex"
    input.focus()
  }

  if (element.tagName === "INPUT" || element.tagName === "TEXTAREA") {
    const eles = document.querySelectorAll(`[class~="tibillet-toggle-edit"][data-toggle-edit-target="${commun}"]`)
    // text = document.querySelector(`*:not(input)[class~="tibillet-toggle-edit"][data-toggle-edit-target="${commun}"]`)
    for (let i = 0; i < eles.length; i++) {
      if (eles[i].tagName !== "INPUT" || eles[i].tagName !== "TEXTAREA") {
        text = eles[i]
        break
      }

    }
    text.style.display = "flex"
  }

  // touche entrée appuyée
  if (state) {
    console.log('obj =', obj);
    const value = element.value
    obj[key] = value
    text.innerHTML = value
  }
}

function changeSrcImage(evt) {
  const file = evt.target.files[0]
  const reader = new FileReader();
  reader.onloadend = function () {
    styleHeader.value.background = `url('${reader.result}') no-repeat center`
    styleHeader.value.backgroundSize = '100% auto'
  }
  if (file) {
    reader.readAsDataURL(file);
  }
}

onMounted(() => {
  document.querySelector('#tibillet-input-file-header').addEventListener('change', changeSrcImage)
})

onUnmounted(() => {
  document.querySelector('#tibillet-input-file-header').removeEventListener('change', changeSrcImage)
})

</script>

<style scoped>
.tibillet-header-event {
  padding: 4px;
}


.tibillet-load-image-header-event {
  width: 100%;
  height: calc(250px - 8px);
  color: aliceblue;
}

.tibillet-load-image-header-event:hover {
  border: 2px dashed var(--bs-info);
}

*:not(input)[class~="tibillet-toggle-edit"]:hover,
*:not(textarea)[class~="tibillet-toggle-edit"]:hover {
  border: 2px dashed var(--bs-info);
  cursor: pointer;
}

.tibillet-action-icon-header,
input[class~="tibillet-toggle-edit"],
textarea[class~="tibillet-toggle-edit"] {
  display: none;
}

.tibillet-load-image-header-event:hover .tibillet-action-icon-header {
  display: flex;
  cursor: pointer;
}

textarea {
  width: 100%;
  height: 100%;
  resize: none;
}
</style>