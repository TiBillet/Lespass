package re.filaos.sunmiprinterplugin

import android.content.Context
import android.os.RemoteException
import android.util.Log
import com.sunmi.peripheral.printer.*
import android.graphics.Bitmap

object SunmiPrintHelper {
    private const val TAG = "SunmiPrintHelper"

    const val NoSunmiPrinter = 0x00000000
    const val CheckSunmiPrinter = 0x00000001
    const val FoundSunmiPrinter = 0x00000002
    const val LostSunmiPrinter = 0x00000003

    private var sunmiPrinterService: SunmiPrinterService? = null
    private var sunmiPrinter = CheckSunmiPrinter

    // Callback interne pour le binding
    private val innerPrinterCallback = object : InnerPrinterCallback() {
        override fun onConnected(service: SunmiPrinterService) {
            sunmiPrinterService = service
            sunmiPrinter = FoundSunmiPrinter
            Log.d(TAG, "Printer connected")
            try {
                sunmiPrinterService?.printerInit(null)
            } catch (e: RemoteException) {
                e.printStackTrace()
            }
        }

        override fun onDisconnected() {
            sunmiPrinterService = null
            sunmiPrinter = LostSunmiPrinter
            Log.w(TAG, "Printer disconnected")
        }
    }

    // Initialisation du service
    fun initSunmiPrinterService(context: Context, onReady: (Boolean) -> Unit) {
        try {
            val ret = InnerPrinterManager.getInstance().bindService(context, innerPrinterCallback)
            if (!ret) {
                onReady(false)
                return
            }
            // La callback onConnected s'assure que printerInit() est appelé
            onReady(true)
        } catch (e: InnerPrinterException) {
            e.printStackTrace()
            onReady(false)
        }
    }

    fun deInitSunmiPrinterService(context: Context) {
        try {
            sunmiPrinterService?.let {
                InnerPrinterManager.getInstance().unBindService(context, innerPrinterCallback)
            }
            sunmiPrinterService = null
            sunmiPrinter = LostSunmiPrinter
        } catch (e: InnerPrinterException) {
            e.printStackTrace()
        }
    }

    fun isPrinterAvailable(): Boolean {
        return sunmiPrinterService != null && sunmiPrinter == FoundSunmiPrinter
    }

    // Fonction commune pour exécuter toute action avec retry
    private fun <T> withPrinterService(action: (SunmiPrinterService) -> T) {
        val maxRetries = 5
        val delayMs: Long = 100
        var attempt = 0

        while (attempt < maxRetries) {
            val service = sunmiPrinterService
            if (service != null && sunmiPrinter == FoundSunmiPrinter) {
                try {
                    action(service)
                } catch (e: RemoteException) {
                    e.printStackTrace()
                }
                return
            } else {
                Thread.sleep(delayMs)
                attempt++
            }
        }
        Log.w(TAG, "Printer not ready after $maxRetries attempts. Action not executed.")
    }

    // Méthodes d'impression
    fun printerInit() {
        withPrinterService { it.printerInit(null) }
    }

   fun printText(content: String, size: Float = 24f, isBold: Boolean = false, isUnderLine: Boolean = false) {
    withPrinterService { service ->
        service.setFontSize(size, null) // <--- Float direct
        service.setPrinterStyle(WoyouConsts.ENABLE_BOLD, if (isBold) WoyouConsts.ENABLE else WoyouConsts.DISABLE)
        service.setPrinterStyle(WoyouConsts.ENABLE_UNDERLINE, if (isUnderLine) WoyouConsts.ENABLE else WoyouConsts.DISABLE)
        service.printText(content, null)
    }
  }

    fun setAlign(align: Int) {
        withPrinterService { it.setAlignment(align, null) }
    }

    fun printQr(data: String, modulesize: Int = 8, errorlevel: Int = 0) {
        withPrinterService { it.printQRCode(data, modulesize, errorlevel, null) }
    }

    fun printBarCode(data: String, symbology: Int = 8, height: Int = 162, width: Int = 2, textposition: Int = 2) {
        withPrinterService { it.printBarCode(data, symbology, height, width, textposition, null) }
    }

    fun printTable(txts: Array<String>, width: IntArray, align: IntArray) {
        withPrinterService { it.printColumnsString(txts, width, align, null) }
    }

    fun lineWrap(n: Int = 3) {
        withPrinterService { it.lineWrap(n, null) }
    }

    fun cutPaper() {
        withPrinterService { it.cutPaper(null) }
    }

    fun openDrawer() {
        withPrinterService { it.openDrawer(null) }
    }

    fun autoOutPaper() {
        withPrinterService { it.autoOutPaper(null) }
    }

    fun updatePrinterState(): Int {
        return if (isPrinterAvailable()) {
            try {
                sunmiPrinterService!!.updatePrinterState()
            } catch (e: RemoteException) {
                e.printStackTrace()
                505
            }
        } else {
            505
        }
      }

    fun printBitmap(bitmap: Bitmap) {
      /* 
      withPrinterService { service ->
        try {
            service.printBitmap(bitmap, null) // null = callback optionnel
        } catch (e: RemoteException) {
            e.printStackTrace()
            Log.e(TAG, "Erreur lors de l'impression du bitmap")
        }
      }
        */
    }
}