package re.filaos.sunmiprinterplugin

import android.util.Log
import org.apache.cordova.CordovaPlugin
import org.apache.cordova.CallbackContext
import org.json.JSONArray
import org.json.JSONObject
import android.graphics.Bitmap
import android.graphics.BitmapFactory

class SunmiPrinterPlugin : CordovaPlugin() {

    override fun execute(action: String, args: JSONArray, callbackContext: CallbackContext): Boolean {
        when (action) {
            "isPrinterAvailable" -> {
              if(SunmiPrintHelper.isPrinterAvailable()) {
                callbackContext.success("enabled")
              } else {
                callbackContext.error("disabled")
              }
              return true
            }

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
                val align = args.getInt(4)
                SunmiPrintHelper.printText(content, size, isBold, isUnderLine, align)
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
                val align = if (args.length() > 3) args.getInt(3) else 0
                SunmiPrintHelper.printQr(data, modulesize, errorlevel, align)
                callbackContext.success("QR code printed")
                return true
            }

            "printBarCode" -> {
                val data = args.getString(0)
                val symbology = if (args.length() > 1) args.getInt(1) else 8
                val height = if (args.length() > 2) args.getInt(2) else 162
                val width = if (args.length() > 3) args.getInt(3) else 2
                val textPosition = if (args.length() > 4) args.getInt(4) else 2
                val align = if (args.length() > 5) args.getInt(5) else 0
                SunmiPrintHelper.printBarCode(data, symbology, height, width, textPosition, align)
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
                var base64 = args.getString(0)

                // Nettoyage si base64 contient header data:image/...
                if (base64.contains(",")) {
                    base64 = base64.substringAfter(",")
                }
                
                val decodedBytes = android.util.Base64.decode(base64, android.util.Base64.DEFAULT)
                var bitmap = BitmapFactory.decodeByteArray(decodedBytes, 0, decodedBytes.size)

                // Vérifier que le décodage a réussi
                if (bitmap == null) {
                    callbackContext.error("Invalid image data")
                    return true
                }

                // Largeur personnalisée ou défaut 384 (58mm)
                val requestedWidth = if (args.length() > 1) args.getInt(1) else 384
                val targetWidth = minOf(requestedWidth, 384)
                if (targetWidth <= 0) {
                    callbackContext.error("Width must be positive")
                    return true
                }

                val ratio = bitmap.height.toFloat() / bitmap.width.toFloat()
                val targetHeight = (targetWidth * ratio).toInt()

                val align = if (args.length() > 2) args.getInt(2) else 0

                bitmap = Bitmap.createScaledBitmap(bitmap, targetWidth, targetHeight, true)

                // forcer multiple de 8 (important SUNMI)
                val w = (bitmap.width / 8) * 8
                val h = (bitmap.height / 8) * 8
                bitmap = Bitmap.createScaledBitmap(bitmap, w, h, true)
                
                SunmiPrintHelper.printBitmap(bitmap, align)
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