// store
import {useAllStore} from '@/stores/all'
const {language} = storeToRefs(useAllStore())

// traduction
const listTrad = [
  {'fr': 'Termes et conditions', 'en': 'Terms and conditions'},
  {'fr': 'termes généraux', 'en': 'General Terms'},
  {'en': 'Disclaimer', 'fr': 'Avertissement'},
  {'en': 'Liability', 'fr': 'Responsabilité'},
  {'en': 'Hyperlinking', 'fr': 'Hyperlien'},
  {'en': 'connected', 'fr': 'connecté'},
  {'en': 'user', 'fr': 'utilisateur'},
  {'en': 'log out', 'fr': 'se déconnecter'}

]

export function trad(text,options) {
  // store
  const store = useStore()
  const langueSite = language

  for (let i = 0; i < listTrad.length; i++) {
    const terme = listTrad[i]
    for (const langue in terme) {
      if (text === terme[langue]) {
        if (options !== undefined) {
          // capitalise
          if (options.FirstLetterCapitalise === true) {
            return terme[langueSite].charAt(0).toUpperCase() + terme[langueSite].slice(1)
          }
        }
        return terme[langueSite]
      }
    }
  }
}