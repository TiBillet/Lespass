package re.filaos.sunmiprinterplugin

import android.util.Log
import org.apache.cordova.CordovaPlugin
import org.apache.cordova.CallbackContext
import org.json.JSONArray
import org.json.JSONObject

class SunmiPrinterPlugin : CordovaPlugin() {

    override fun execute(action: String, args: JSONArray, callbackContext: CallbackContext): Boolean {
        when (action) {
            "initSunmiPrinterService" -> {
                val context = cordova.activity.applicationContext
                SunmiPrintHelper.initSunmiPrinterService(context) { connected ->
                    if (connected) {
                        callbackContext.success("Printer connected")
                    } else {
                        callbackContext.error("Printer not found")
                    }
                }
                return true
            }

            "printText" -> {
                val content = args.getString(0)
                val size = args.getDouble(1).toFloat()
                val isBold = args.getBoolean(2)
                val isUnderLine = args.getBoolean(3)
                SunmiPrintHelper.printText(content, size, isBold, isUnderLine)
                callbackContext.success("Text printed")
                return true
            }

            "setAlign" -> {
                val align = args.getInt(0)
                SunmiPrintHelper.setAlign(align)
                callbackContext.success("Alignment set")
                return true
            }

            "printQr" -> {
                val data = args.getString(0)
                val modulesize = if (args.length() > 1) args.getInt(1) else 8
                val errorlevel = if (args.length() > 2) args.getInt(2) else 0
                SunmiPrintHelper.printQr(data, modulesize, errorlevel)
                callbackContext.success("QR code printed")
                return true
            }

            "printBarCode" -> {
                val data = args.getString(0)
                val symbology = if (args.length() > 1) args.getInt(1) else 8
                val height = if (args.length() > 2) args.getInt(2) else 162
                val width = if (args.length() > 3) args.getInt(3) else 2
                val textPosition = if (args.length() > 4) args.getInt(4) else 2
                SunmiPrintHelper.printBarCode(data, symbology, height, width, textPosition)
                callbackContext.success("BarCode printed")
                return true
            }

            "printTable" -> {
                val txts = Array(args.getJSONArray(0).length()) { i -> args.getJSONArray(0).getString(i) }
                val widthArray = IntArray(args.getJSONArray(1).length()) { i -> args.getJSONArray(1).getInt(i) }
                val alignArray = IntArray(args.getJSONArray(2).length()) { i -> args.getJSONArray(2).getInt(i) }
                SunmiPrintHelper.printTable(txts, widthArray, alignArray)
                callbackContext.success("Table printed")
                return true
            }

            "lineWrap" -> {
                val n = if (args.length() > 0) args.getInt(0) else 3
                SunmiPrintHelper.lineWrap(n)
                callbackContext.success("Line wrapped")
                return true
            }

            "cutPaper" -> {
                SunmiPrintHelper.cutPaper()
                callbackContext.success("Paper cut")
                return true
            }

            "openDrawer" -> {
                SunmiPrintHelper.openDrawer()
                callbackContext.success("Drawer opened")
                return true
            }

            "autoOutPaper" -> {
                SunmiPrintHelper.autoOutPaper()
                callbackContext.success("Auto out paper executed")
                return true
            }

            "updatePrinterState" -> {
                val state = SunmiPrintHelper.updatePrinterState()
                callbackContext.success(state)
                return true
            }
            
            "printBitmap" -> {
              val base64 = args.getString(0)
              val decodedBytes = android.util.Base64.decode(base64, android.util.Base64.DEFAULT)
              val bitmap = android.graphics.BitmapFactory.decodeByteArray(decodedBytes, 0, decodedBytes.size)
              SunmiPrintHelper.printBitmap(bitmap)
              callbackContext.success("Bitmap printed")
              return true
            }
            
            else -> {
                callbackContext.error("Invalid action")
                return false
            }
        }
    }
}