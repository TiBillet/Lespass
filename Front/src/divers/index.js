// store
import {useStore} from '@/store'

export class StoreLocal {
  constructor(typeStorage, path, content) {
    try {
      if (window[typeStorage].getItem(path) === null) {
        window[typeStorage].setItem(path, JSON.stringify(content))
      }
    } catch (error) {
      console.log('Constructor StoreLocal,', error)
    }
  }

  static use(typeStorage, path) {
    // console.log('-> static use !!')
    let content = {}
    if (window[typeStorage].getItem(path) === null) {
      window[typeStorage].setItem(path, JSON.stringify(content))
    } else {
      content = JSON.parse(window[typeStorage].getItem(path))
    }
    const state = new Proxy(content, {
      path,
      typeStorage,
      get(target, name, receiver) {
        if (Reflect.has(target, name)) {
          return Reflect.get(target, name, receiver)
        }
        return null
      },
      set(target, name, value, receiver) {
        if (Reflect.has(target, name)) {
          let newState = Reflect.set(target, name, value, receiver)
          // update storage
          console.log('target =', target)
          window[typeStorage].setItem(this.path, JSON.stringify(target))
          return newState
        }
      }
    })
    return state
  }
}

// traduction
const listTrad = [
  {'fr': 'Termes et conditions', 'en': 'Terms and conditions'},
  {'fr': 'termes généraux', 'en': 'General Terms'},
  {'en': 'Disclaimer', 'fr': 'Avertissement'},
  {'en': 'Liability', 'fr': 'Responsabilité'},
  {'en': 'Hyperlinking', 'fr': 'Hyperlien'}
]

export function trad(text,options) {
  // store
  const store = useStore()
  const langueSite = store.language

  for (let i = 0; i < listTrad.length; i++) {
    const terme = listTrad[i]
    for (const langue in terme) {
      console.log(`${langue}: ${terme[langue]}`);
      if (text === terme[langue]) {
        console.log('options =', options)
        if (options !== undefined) {
          // capitalise
          // console.log('options.FirstLetterCapitalise =', options.FirstLetterCapitalise)
          if (options.FirstLetterCapitalise === true) {
            return terme[langueSite].charAt(0).toUpperCase() + terme[langueSite].slice(1)
          }
        }
        return terme[langueSite]
      }
    }
  }
}