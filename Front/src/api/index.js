import {ref} from 'vue'

export const domain = `${location.protocol}//${location.host}`

export function loadPlace() {
  const apiLieu = `/api/here/`
  const retourPlace = ref(null)
  const errorPlace = ref(null)
  console.log(`-> charge le lieu ${domain + apiLieu}`)
  fetch(domain + apiLieu).then((res) => res.json())
    .then((json) => (retourPlace.value = json))
    .catch((err) => (errorPlace.value = err))

  return {retourPlace, errorPlace}

  /*
  } catch (erreur) {
    console.log('Api, place, erreur:', erreur)
    emitter.emit('message', {
      tmp: 4,
      typeMsg: 'danger',
      contenu: `/api/here/, erreur: ${erreur}`
    })
  */
}