package re.filaos.connectivityplugin

// import org.apache.cordova.*
import org.apache.cordova.CallbackContext
import org.apache.cordova.CordovaPlugin
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import android.content.Intent
import android.content.Context

// Settings object
import android.provider.Settings

// wifi
import android.net.wifi.WifiManager
import android.net.wifi.WifiInfo

// nfc
import android.nfc.NfcAdapter

// bluetooth
import android.bluetooth.BluetoothAdapter


class ConnectivityPlugin : CordovaPlugin() {
  override fun execute(action: String, args: JSONArray?, callbackContext: CallbackContext): Boolean {
    return try {
      // listen js call
      when (action) {
        "openWifiSettings" -> {
          openWifiSettings()
          callbackContext.success("Wi-Fi settings opened")
          true
        }
         "openNfcSettings" -> {
          openNfcSettings()
          callbackContext.success("Nfc settings opened")
          true
        }
        "openBluetoothSettings" -> {
          openBluetoothSettings()
          callbackContext.success("Bluetooth settings opened")
          true
        }
        "getBluetoothStatus" -> {
          try {
            // Appelle ta fonction getBluetoothStatus et récupère le résultat
            val result = getBluetoothStatus()
            // Envoie le résultat côté JS si tout s'est bien passé
            callbackContext.success(result) // result = JSONObject et pouurai être String, Int, JSONArray
          } catch (e: Exception) {
            // Envoie l'erreur côté JS si une exception est levée
            callbackContext.error("Erreur Bluetooth: ${e.message}")
          }
          true
        }
        "getWifiStatus" -> {
          try {
            // Appelle ta fonction getWifiStatus et récupère le résultat
            val result = getWifiStatus()
            // Envoie le résultat côté JS si tout s'est bien passé
            callbackContext.success(result) // result = JSONObject et pouurai être String, Int, JSONArray
          } catch (e: Exception) {
            // Envoie l'erreur côté JS si une exception est levée
            callbackContext.error("Erreur Wifi: ${e.message}")
          }
          true
        }
        "getNfcStatus" -> {
          try {
            // Appelle ta fonction getNfcStatus et récupère le résultat
            val result = getNfcStatus()
            // Envoie le résultat côté JS si tout s'est bien passé
            callbackContext.success(result) // result = JSONObject et pouurai être String, Int, JSONArray
          } catch (e: Exception) {
            // Envoie l'erreur côté JS si une exception est levée
            callbackContext.error("Erreur Nfc: ${e.message}")
          }
          true
        }
        else -> false
      }
    } catch (e: JSONException) {
      callbackContext.error("Error: ${e.message}")
      false
    }
  }

  private fun openWifiSettings() {
    val intent = Intent(Settings.ACTION_WIFI_SETTINGS)
    cordova.activity.startActivity(intent)
  }

  private fun openNfcSettings() {
    val intent = Intent(Settings.ACTION_NFC_SETTINGS)
    cordova.activity.startActivity(intent)
  }

  // Android ne fournit plus d’intent public standard pour ouvrir directement le panneau “Bluetooth”
  private fun openBluetoothSettings() {
    val intent = Intent(Settings.ACTION_BLUETOOTH_SETTINGS)
    cordova.activity.startActivity(intent)
  }

  /**
  * Récupère le statut du Bluetooth sans l'activer.
  * @return JSONObject avec le status et un message lisible.
  */
  private fun getBluetoothStatus(): JSONObject {
    val result = JSONObject()

    // Récupère l'adaptateur Bluetooth de l'appareil
    val bluetoothAdapter: BluetoothAdapter? = BluetoothAdapter.getDefaultAdapter()
    
   if (bluetoothAdapter == null) {
        result.put("status", "not_available")
        result.put("message", "Bluetooth non disponible sur cet appareil")
    } else if (bluetoothAdapter.isEnabled) {
        result.put("status", "enabled")
        result.put("message", "Bluetooth activé")
    } else {
        result.put("status", "disabled")
        result.put("message", "Bluetooth désactivé")
    }

    return result
  }

  /**
  * Récupère le statut du Wi-Fi.
  * @return JSONObject avec le status et un message lisible.
  */
  private fun getWifiStatus(): JSONObject {
    val result = JSONObject()

    // Récupère le service Wi-Fi du système
    val wifiManager = cordova.activity.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager

    if (wifiManager == null) {
        result.put("status", "not_available")
        result.put("message", "Wi-Fi non disponible sur cet appareil")
    } else if (wifiManager.isWifiEnabled) {
        result.put("status", "enabled")
        result.put("message", "Wi-Fi activé")
    } else {
        result.put("status", "disabled")
        result.put("message", "Wi-Fi désactivé")
    }
    return result
  }

  /**
  * Récupère le statut du NFC.
  * @return JSONObject avec le status et un message lisible.
  */
  private fun getNfcStatus(): JSONObject {
    val result = JSONObject()

    val nfcAdapter = NfcAdapter.getDefaultAdapter(cordova.activity.applicationContext)

    if (nfcAdapter == null) {
      // NFC non disponible sur cet appareil
      result.put("status", "not_available")
      result.put("message", "NFC not available on this device")
    } else if (nfcAdapter.isEnabled) {
      // NFC activé
      result.put("status", "enabled")
      result.put("message", "NFC enabled")
    } else {
      // NFC désactivé
      result.put("status", "disabled")
      result.put("message", "NFC disabled")
    }
    return result
  }
}
