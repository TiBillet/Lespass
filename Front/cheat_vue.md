```
import {ref, computed, watch, onMounted, reactive} from "vue"
```
## povide/inject (object global)

. main.js
```
// définition de l'objet "glob"
app.provide('glob', {
  test: 'salut',
  affMsg: (msg) => {
    console.log('message =', msg)
  }
})
```
. Pour y accéder dans chaque composant
```
// vue (inject, pour avoir accés  à l'objet "glob") 
import {inject} from 'vue'

// récupère l'objet glob défini dans main.js avec provide
const glob = inject('glob')

console.log('test =', glob.test)
glob.affMsg('Salut la compagnie !')
```
. Utiliser "provide" dans un composant
```
import {provide} from 'vue'
provide ('glob', {
    test: "salut"
})
```

##computed
```
const variable = computed(() => {
    ... votre code
})
```

## onMounted
```
onMounted(() => {
    ... votre code
})
```

## Attendre la mise à jour du DOM
```
<script>
import { nextTick } from 'vue'

export default {
  data() {
    return {
      count: 0
    }
  },
  methods: {
    async increment() {
      this.count++

      // DOM not yet updated
      console.log(document.getElementById('counter').textContent) // 0

      await nextTick()
      // DOM is now updated
      console.log(document.getElementById('counter').textContent) // 1
    }
  }
}
</script>

<template>
  <button id="counter" @click="increment">{{ count }}</button>
</template>
```