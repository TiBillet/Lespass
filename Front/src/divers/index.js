export class StoreLocal {
  constructor(typeStorage, path, content) {
    // console.log('-> constructor !')
    let state = content
    if (window[typeStorage].getItem(path) === null) {
      window[typeStorage].setItem(path, JSON.stringify(content))
    } else {
      state = JSON.parse(window[typeStorage].getItem(path))
    }
    this.state = new Proxy(state, {
      path,
      typeStorage,
      get(target, name, receiver) {
        if (Reflect.has(target, name)) {
          return Reflect.get(target, name, receiver)
        }
        return null
      },
      set(target, name, value, receiver) {
        console.log('set -> path =', path, '  --  name =', name)
        console.log('value =', value)
        if (Reflect.has(target, name)) {
          let newState = Reflect.set(target, name, value, receiver)
          // update storage
          console.log('target =', target)
          window[this.typeStorage].setItem(this.path, JSON.stringify(target))
          return newState

        }
        console.log(`propriété inconnue '${name}' !`);
      }
    })

  }
}