const exec = require('cordova/exec');

module.exports = {
  openWifiSettings() {
    return new Promise((resolve, reject) => {
      // call kotlin ConnectivityPlugin.openWifiSettings function
      exec(
        resolve,
        (err) => reject(new Error(err)),
        'ConnectivityPlugin',
        'openWifiSettings',
        []
      )
    })
  },
  openNfcSettings() {
    return new Promise((resolve, reject) => {
      // call kotlin ConnectivityPlugin.openNfcSettings function
      exec(
        resolve,
        (err) => reject(new Error(err)),
        'ConnectivityPlugin',
        'openNfcSettings',
        []
      )
    })
  },
  openBluetoothSettings() {
    return new Promise((resolve, reject) => {
      // call kotlin ConnectivityPlugin.openBluetoothSettings function
      exec(
        resolve,
        (err) => reject(new Error(err)),
        'ConnectivityPlugin',
        'openBluetoothSettings',
        []
      )
    })
  },
  getBluetoothStatus() {
    return new Promise((resolve, reject) => {
      // call kotlin ConnectivityPlugin.getBluetoothStatus function
      exec(
        resolve,
        (err) => reject(new Error(err)),
        'ConnectivityPlugin',
        'getBluetoothStatus',
        []
      )
    })
  },
  getWifiStatus() {
    return new Promise((resolve, reject) => {
      // call kotlin ConnectivityPlugin.getWifiStatus function
      exec(
        resolve,
        (err) => reject(new Error(err)),
        'ConnectivityPlugin',
        'getWifiStatus',
        []
      )
    })
  },
  getNfcStatus() {
    return new Promise((resolve, reject) => {
      // call kotlin ConnectivityPlugin.getNfcStatus function
      exec(
        resolve,
        (err) => reject(new Error(err)),
        'ConnectivityPlugin',
        'getNfcStatus',
        []
      )
    })
  }

}