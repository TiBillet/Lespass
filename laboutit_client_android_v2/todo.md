Légende
⏳ : En attente
🔄 : En cours
✅ : Terminé

| Tâche                                                                       | Statut           |
|-----------------------------------------------------------------------------|------------------|
| interface de base de l'application LaBoutik                                 | terminée : ✅    |
| plugin connectivity : get and show status devices nfc, wifi, bluetooth      | terminée : ✅    |
| créer un plugin avec une lib/sdk qui build                                  | terminée : ✅    |
| chercher le bon sdk pour imprimer avec sunmi                                | En cours : 🔄    |
| ajouter dans getdevicesStatus printerSunmi                                  | En attente : ⏳  |


 //Please refer to https://developer.sunmi.com/docs/en-US/cdixeghjk491/xdzqeghjk513 for the latest version
implementation 'com.sunmi:printerx:1.0.17' dernière version

https://github.com/shangmisunmi/SunmiPrinterXSample/blob/main/sample-ktx/src/main/java/com/sunmi/samples/printerx/MainActivity.kt :
import com.sunmi.printerx.PrinterSdk
import com.sunmi.samples.printerx.ui.main.MainFragment

SUNMI Printing SDK Overview :
https://developer.sunmi.com/docs/en-US/cdixeghjk491/xdzceghjk502
