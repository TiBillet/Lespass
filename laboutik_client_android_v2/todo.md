Légende
⏳ : En attente
🔄 : En cours
✅ : Terminé

| Tâche                                                                       | Statut           |
|-----------------------------------------------------------------------------|------------------|
| interface de base de l'application LaBoutik                                 | terminée : ✅    |
| plugin connectivity : get and show status devices nfc, wifi, bluetooth      | terminée : ✅    |
| créer un plugin avec une lib/sdk qui build                                  | terminée : ✅    |
| chercher le bon sdk pour imprimer avec sunmi                                | terminée : ✅    |
| appairage device                                                            | terminée : ✅    |
| ajout bt menu avec item logs et change serveur discovery                    | En cours : 🔄    |
| logguer l'obtention du fichier de sauvegarde                                | En attente : ⏳  |
| ajouter dans getdevicesStatus printerSunmi                                  | En attente : ⏳  |
| Signature de l'apk                                                          | En attente : ⏳  |

# Etapes (asyncrones)
- page index.html chargé :
  . clique sur bt 'add place' = managedPinCode
  . clique sur bt 'logs' = showLogs

- Cordova ready :
  Etapes syncrones.
  1 - getDevicesStatusAndShow() :
      . réseau ok
      . nfc ok
      . printerSunmi - En attente

  2 - getConfigurationAndSave() :
      si pas de fichier de configuration sauvegardé ou erreur lecture revenir au fichier env.js 

  3 - showMainContent (bt 'add place' et liste de serveurs) :
      clique sur bt serveur = updateCurrentServerAndGoServer()
    

# infos
 //Please refer to https://developer.sunmi.com/docs/en-US/cdixeghjk491/xdzqeghjk513 for the latest version
implementation 'com.sunmi:printerx:1.0.17' dernière version

https://github.com/shangmisunmi/SunmiPrinterXSample/blob/main/sample-ktx/src/main/java/com/sunmi/samples/printerx/MainActivity.kt :
import com.sunmi.printerx.PrinterSdk
import com.sunmi.samples.printerx.ui.main.MainFragment

SUNMI Printing SDK Overview :
https://developer.sunmi.com/docs/en-US/cdixeghjk491/xdzceghjk502
