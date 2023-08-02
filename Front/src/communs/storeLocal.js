const index = 'TiBillet-local'
const initState = {}

// init
if (localStorage.getItem(index) === null) {
  localStorage.setItem(index, JSON.stringify(initState))
}

export function getLocalState () {
  try {
    return JSON.parse(localStorage.getItem(index))
  } catch (error) {
    console.log(`locale storage "${index} - getLocalState, error: ${error}`)
  }
}

export function setLocalStateKey (key, data) {
  try {
    const state = JSON.parse(localStorage.getItem(index))
    localStorage.removeItem(index)
    state[key] = data
    state[key]['timestampStore'] = new Date().getTime()
    localStorage.setItem(index, JSON.stringify(state))
  } catch (error) {
    console.log(`locale storage "${index} - setLocalState, error: ${error}`)
  }
}

export function getLocalStateKey (key) {
  try {
    const state = JSON.parse(localStorage.getItem(index))
    return state[key]
  } catch (error) {
    console.log(`locale storage "${index} - getLocal, error: ${error}`)
  }
}

export function resetLocalState () {
  try {
    localStorage.removeItem(index)
    localStorage.setItem(index, JSON.stringify(initState))
  } catch (error) {
    console.log(`locale storage "${index} - resetLocalState, error: ${error}`)
  }
}

export function deleteLocalState () {
  try {
    localStorage.removeItem(index)
  } catch (error) {
    console.log(`locale storage "${index} - deleteLocalState, error: ${error}`)
  }
}
