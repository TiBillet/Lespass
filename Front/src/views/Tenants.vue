<template>
  <WizardCreation title="Créer votre espace">
    <template #wizard-subtitle>
      Sélectionner, éditer un type d'espace.
    </template>
    <template #wizard-tabs-content>
      <div id="espace" class="wizard-tab-content">
        contenu espace
      </div>
      <div id="informations" class="wizard-tab-content">
        contenu informations
      </div>
      <div id="validation" class="wizard-tab-content">
        contenu validation
      </div>
    </template>
  </WizardCreation>
</template>

<script setup>
console.log('-> Tenants.vue')
import WizardCreation from '../components/WizardCreation.vue'

</script>
<style scoped></style>