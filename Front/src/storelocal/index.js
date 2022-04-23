// store
import {useStore} from '@/store'

// store local storage
const state = {
  email: '',
  refreshToken: '',
  storeBeforeUseExternalUrl: {},
}

// emit notifications
const notify = (name, value) => {
  const store = useStore()
  // --- add yours notification here ---

  // staus connection = status refreshToken
  if (name === 'refreshToken') {
    emitter.emit('refreshTokenChange', value)
  }

  if (name === 'email') {
    console.log('-> notify, email =', value)
    emitter.emit('emailChange', value)
    if (store.memoComposants.CardEmail !== undefined) {
      store.memoComposants.CardEmail.unique00.email = value
      store.memoComposants.CardEmail.unique00.confirmeEmail = value
    }
  }
}

const options = {
  typeStorage: 'localStorage',
  path: 'Tibilet-identite'
}

export function storeLocalReset() {
  window[options.typeStorage].removeItem(options.path)
}

// Cré le store local uniquement si la clef path nn'existe pas
// Attention pour un reset supprmimer manuellement le storage
export function storeLocalInit() {
  if (window[options.typeStorage].getItem(options.path) === null) {
    window[options.typeStorage].setItem(options.path, JSON.stringify(state))
  }
}

export function storeLocalGet(name) {
  try {
    // récupération du state à partir du storage
    const state = JSON.parse(window[options.typeStorage].getItem(options.path))
    return state[name]
  } catch (erreur) {
    console.log('-> StoreLocalGet', erreur)
  }
}

export function storeLocalSet(name, value) {
  try {
    // récupération du state à partir du storage
    const state = JSON.parse(window[options.typeStorage].getItem(options.path))
    state[name] = value
    // maj du storage
    window[options.typeStorage].setItem(options.path, JSON.stringify(state))
    notify(name, value)
  } catch (erreur) {
    console.log('-> StoreLocalSet', erreur)
  }
}


/*
export class StoreLocal {
  constructor() {
    // state of store
    this.state = state

    // do not change the position of the code, data required
    this.options = {
      typeStorage: 'localStorage',
      path: 'Tibilet-identite'
    }

    try {
      if (window[this.options.typeStorage].getItem(this.options.path) === null) {
        window[this.options.typeStorage].setItem(this.options.path, JSON.stringify(this.state))
      } else {
        this.state = JSON.parse(window[this.options.typeStorage].getItem(this.options.path))
      }
      this.state.options = this.options
      this.state.notify = notify

      const state = new Proxy(this.state, {
        get(target, name, receiver) {
          if (Reflect.has(target, name)) {
            return Reflect.get(target, name, receiver)
          }
          return null
        },
        set(target, name, value, receiver) {
          console.log('target =', target)

          if (Reflect.has(target, name)) {
            let newState = Reflect.set(target, name, value, receiver)
            // notify specific change
            target.notify(name, value)
            // update storage
            const typeStorage = target.options.typeStorage
            const path = target.options.path
            window[typeStorage].setItem(path, JSON.stringify(target))
            return newState
          }
        }
      })
      return state
    } catch
      (error) {
      console.log('storelocal/index.js:', error)
    }
  }
}
*/