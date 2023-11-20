console.log('-> commun.js');
const domain = `${window.location.protocol}//${window.location.host}`;
console.log('domain =', domain);

const initState = {
    page: 'inconnue',

}

let state = new Proxy(initState, {
  set(target, name, value) {
    console.log("set " + name + " to " + value);
    target[name] = value;
  }
});

console.log('1 -> state =', state);
state.page = 'accueil'
console.log('2 -> state =', state);