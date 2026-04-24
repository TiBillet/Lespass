# ConnectivityPlugin

## ConnectivityPlugin methods
- ConnectivityPlugin.openWifiSettings
- ConnectivityPlugin.openBluetoothSettings
- ConnectivityPlugin.openNfcSettings
- ConnectivityPlugin.getBluetoothStatus
- ConnectivityPlugin.getNfcStatus
- ConnectivityPlugin.getWifiStatus

## Example call method in front/js 
```js
// Ouvrir Wi-Fi
await ConnectivityPlugin.openWifiSettings(
    () => console.log('Wi-Fi ouvert'),
    (err) => console.error(err)
)
```

