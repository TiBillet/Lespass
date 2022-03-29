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