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
  private var isListening = false

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
          stopListeningInternal(notifyCallback = false)
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
        stopListeningInternal(notifyCallback = true, successCallback = callbackContext)
        true
      }

      "available" -> {
        try {
          when {
            nfcAdapter == null -> callbackContext.success("no nfc")
            nfcAdapter?.isEnabled == false -> callbackContext.success("disable")
            else -> callbackContext.success("available")
          }
        } catch (e: Exception) {
          callbackContext.error("Erreur Nfc: ${e.message}")
        }
        true
      }

      else -> false
    }
  }

  private fun stopListeningInternal(notifyCallback: Boolean, successCallback: CallbackContext? = null) {
    if (notifyCallback) {
      this.callbackContext?.let { oldCtx ->
        oldCtx.error("Listening stopped by user")
      }
    }
    this.callbackContext = null
    isListening = false
    disableThisForegroundDispatch()
    successCallback?.success("stop listening nfc !")
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
    
    callbackContext?.let { ctx ->
      Log.d(LOGTAG, "Sending NFC tag to JS: $result")
      ctx.success(result)
      callbackContext = null
    } ?: Log.w(LOGTAG, "CallbackContext is null")

    isListening = false
    disableThisForegroundDispatch()
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

  private fun enableThisForegroundDispatch() {
    Log.d(LOGTAG, "enableThisForegroundDispatch called")
    val activity = cordova.activity
    val intent = Intent(activity, activity.javaClass).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
    val pendingIntent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
      PendingIntent.getActivity(activity, 0, intent, PendingIntent.FLAG_MUTABLE)
    } else {
      PendingIntent.getActivity(activity, 0, intent, 0)
    }
    val filters = arrayOf(
      IntentFilter(NfcAdapter.ACTION_TAG_DISCOVERED),
      IntentFilter(NfcAdapter.ACTION_TECH_DISCOVERED),
      IntentFilter(NfcAdapter.ACTION_NDEF_DISCOVERED)
    )
    try {
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
