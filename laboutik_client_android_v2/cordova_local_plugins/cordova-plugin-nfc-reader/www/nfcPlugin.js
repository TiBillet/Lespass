const exec = require('cordova/exec')

module.exports = {
  startListening() {
    return new Promise((resolve, reject) => {
      exec(resolve, reject, 'NfcPlugin', 'startListening', [])
    })
  },
  stopListening() {
    return new Promise((resolve, reject) => {
      exec(resolve, reject, 'NfcPlugin', 'stopListening', [])
    })
  },
  available() {
    return new Promise((resolve, reject) => {
      exec(resolve, reject, 'NfcPlugin', 'available', [])
    })
  }
}
