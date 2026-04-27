package re.filaos.nfcplugin

import android.app.PendingIntent
import android.content.Intent
import android.content.IntentFilter
import android.nfc.NfcAdapter
import android.nfc.Tag
import android.os.Build
import android.util.Log
import org.apache.cordova.*
import org.json.JSONArray
import org.json.JSONObject

class NfcPlugin : CordovaPlugin() {
  private var LOGTAG = "NfcPlugin"
  private var nfcAdapter: NfcAdapter? = null
  private var callbackContext: CallbackContext? = null
  // Flag pour éviter les appels multiples
  private var isListening = false

  // Cordova appelle cette méthode automatiquement quand le plugin est initialisé
  override fun initialize(cordova: CordovaInterface, webView: CordovaWebView) {
    super.initialize(cordova, webView)
    nfcAdapter = NfcAdapter.getDefaultAdapter(cordova.activity)
    if (nfcAdapter == null) {
      Log.e(LOGTAG, "NFC not available on this device")
    } else {
      Log.d(LOGTAG, "NFC adapter initialized")
    }
  }

  override fun execute(action: String, args: JSONArray?, callbackContext: CallbackContext): Boolean {
    return when (action) {
      "startListening" -> {
        if (isListening) {
          callbackContext.error("Already listening for NFC tags")
          return true
        }

        this.callbackContext = callbackContext

        if (nfcAdapter == null) {
          callbackContext.error("NFC not available on this device or permission missing")
          return true
        }
        
        if (nfcAdapter?.isEnabled == false) {
          callbackContext.error("NFC is disabled")
          return true
        }
        
        isListening = true
        enableThisForegroundDispatch()
        Log.d(LOGTAG, "Start listening for NFC tags")
        true
      }
      
      "stopListening" -> {
        // Si un startListening est en cours, résoudre/rejeter son callback
        // avant de traiter le callback de stopListening
        this.callbackContext?.let { oldCtx ->
          oldCtx.error("Listening stopped by user")
          this.callbackContext = null
        }
        isListening = false
        disableThisForegroundDispatch()
        callbackContext.success("stop listening nfc !")
        true
      }
      
      "available" -> {
        try {
          val result = JSONObject()
          if ( nfcAdapter == null || nfcAdapter?.isEnabled == false ) {
            result.put("status", false)
            callbackContext.success(result)
          } else {
            result.put("status", true)
            callbackContext.success(result)
          }
        } catch (e: Exception) {
          callbackContext.error("Erreur Nfc: ${e.message}")
        }
        true
      }
      
      else -> false
    }
  }
    
  override fun onResume(multitasking: Boolean) {
    super.onResume(multitasking)
    if (isListening) {
      enableThisForegroundDispatch()
    }
  }

  override fun onPause(multitasking: Boolean) {
    super.onPause(multitasking)
    if (isListening) {
      disableThisForegroundDispatch()
    }
  }

  private fun handleTag(intent: Intent) {
    val tag: Tag? = intent.getParcelableExtra(NfcAdapter.EXTRA_TAG) ?: return
    val uid = tag?.id?.joinToString("") { byte -> "%02X".format(byte) } ?: return
    Log.d(LOGTAG, "Tag detected with UID: $uid")
    val result = JSONObject()
    result.put("tagId", uid)
    
    // 1 scan = 1 réponse = 1 promesse résolue
    // Si callbackContext existe, alors appelle success(result) dessus
    callbackContext?.let { ctx ->
      Log.d(LOGTAG, "Sending NFC tag to JS: $result")
      ctx.success(result)
      callbackContext = null
    } ?: Log.w(LOGTAG, "CallbackContext is null")

    // Nettoyer l'état dans tous les cas
    isListening = false
    disableThisForegroundDispatch()

    // Consommer l'Intent pour éviter une relecture
    intent.removeExtra(NfcAdapter.EXTRA_TAG)
  }

  override fun onNewIntent(intent: Intent) {
    super.onNewIntent(intent)
    Log.d(LOGTAG, "onNewIntent called with action: ${intent.action}")
    when (intent.action) {
      NfcAdapter.ACTION_TAG_DISCOVERED,
      NfcAdapter.ACTION_TECH_DISCOVERED,
      NfcAdapter.ACTION_NDEF_DISCOVERED -> {
        Log.d(LOGTAG, "onNewIntent called with NFC action: ${intent.action}")
        handleTag(intent)
      }
    } 
  }

  // permet à cordova.activity de recevoir directement les Intents NFC
  private fun enableThisForegroundDispatch() {
    Log.d(LOGTAG, "enableThisForegroundDispatch called")
    val activity = cordova.activity
    // val intent = Intent(activity, activity.javaClass) = nfcPlugin
    // FLAG_ACTIVITY_SINGLE_TOP = si déjà lancer ne pas le relancer 
    val intent = Intent(activity, activity.javaClass).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
    // créer un Intent en attente, qui s’exécutera plus tard
    val pendingIntent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
      PendingIntent.getActivity(activity, 0, intent, PendingIntent.FLAG_MUTABLE)
    } else {
      PendingIntent.getActivity(activity, 0, intent, 0)
    }
    val filters = arrayOf(
      IntentFilter(NfcAdapter.ACTION_TAG_DISCOVERED),  // tag basique
      IntentFilter(NfcAdapter.ACTION_TECH_DISCOVERED), // tags utilisant des technologies spécifiques (IsoDep, NfcA…).
      IntentFilter(NfcAdapter.ACTION_NDEF_DISCOVERED)  // tags contenant des messages NDEF
    )
    try {
      // lors de la lecture d'un tag nfc , lancer le pendingIntent qui cible activity (plugin nfc)
      // et dans le plugin nfc on réception pendingIntent par la méthode override fun onNewIntent. 
      nfcAdapter?.enableForegroundDispatch(activity, pendingIntent, filters, null)
      Log.d(LOGTAG, "Foreground dispatch enabled")
    } catch (e: Exception) {
      Log.e(LOGTAG, "Failed to enable foreground dispatch: ${e.message}")
    }
  }

  private fun disableThisForegroundDispatch() {
    try {
      nfcAdapter?.disableForegroundDispatch(cordova.activity)
      Log.d(LOGTAG, "Foreground dispatch disabled")
    } catch (e: Exception) {
      Log.e(LOGTAG, "Failed to disable foreground dispatch: ${e.message}")
    }
  }
}