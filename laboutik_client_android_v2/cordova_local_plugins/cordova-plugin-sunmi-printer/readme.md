# plugin cordova
- langage : kotlin

# structure du plugin cordova
```
cordova-plugin-sunmi-printer/
├── plugin.xml                         # Fichier de configuration du plugin
├── src/                               # Code natif pour les différentes plateformes
│   └── android/                       # Dossier spécifique à la plateforme Android
│       └── SunmiPrinterPlugin.kt      # Code Kotlin pour l'intégration avec l'imprimante Sunmi
│
├── www/                               # Dossier contenant le code JavaScript du plugin
│   └── sunmiPrinterPlugin.js          # Fichier JavaScript exposant l'API du plugin
│
├── README.md                          # Documentation du plugin
├── package.json                       # Fichier de configuration npm pour le plugin
└── LICENSE                            # Licence du plugin
```


# package
package re.filaos.sunmiprinterplugin

# fichiers du plugin cordova

## plugin.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<plugin xmlns="http://apache.org/ns/plugins" id="re.filaos.sunmiprinterplugin" version="1.0.0">

  <!-- Informations générales sur le plugin -->
  <name>SunmiPrinterPlugin</name>
  <description>Plugin Cordova pour imprimer avec les imprimantes Sunmi</description>
  <author>filaos</author>
  <license>MIT</license>

  <!-- Déclaration du module JavaScript -->
  <js-module src="www/sunmiPrinterPlugin.js" name="sunmiPrinterPlugin">
    <clobbers target="sunmiPrinterPlugin" />
  </js-module>

  <!-- Déclaration de la plateforme Android -->
  <platform name="android">
   
    <!-- Fichier gradle pour les dépendances -->
    <framework src="src/android/build-extras.gradle" custom="true" type="gradleReference" />

    <config-file target="AndroidManifest.xml" parent="/*">
      <!-- Permissions -->
      <uses-permission android:name="android.permission.ACCESS_WIFI_STATE"/>
      <uses-permission android:name="android.permission.CHANGE_WIFI_STATE"/>
      <uses-permission android:name="android.permission.NFC" />
      <uses-permission android:name="android.permission.BLUETOOTH" />
      <uses-permission android:name="android.permission.BLUETOOTH_ADMIN" />
      <!-- Déclaration d'une fonctionnalité matérielle -->
      <uses-feature android:name="android.hardware.bluetooth" android:required="true" />
    </config-file>

    <!-- Déclaration du fichier source Kotlin -->
    <source-file src="src/android/SunmiPrinterPlugin.kt" target-dir="app/src/main/kotlin/re/filaos/sunmiprinterplugin" />

    <!-- Configuration du plugin Kotlin dans Gradle 
    <config-file target="config.xml" parent="/*">
      <preference name="AndroidPersistentFileLocation" value="Compatibility" />
      <preference name="GradlePluginKotlinEnabled" value="true" />
      <preference name="GradlePluginKotlinCodeStyle" value="official" />
    </config-file> -->

    <!-- Association de la classe Kotlin/Java à la fonctionnalité du plugin -->
    <config-file target="res/xml/config.xml" parent="/*">
      <feature name="SunmiPrinterPlugin">
        <param name="android-package" value="re.filaos.sunmiprinterplugin.SunmiPrinterPlugin" />
        <param name="onload" value="true" />
      </feature>
    </config-file>

  </platform>

</plugin>
```

await sunmiPrinterPlugin.isPrinterAvailable((retour) => console.log('retour =',retour), (error) => console.log('error =',error))
await sunmiPrinterPlugin.printText('salut la compagnie',(retour) => console.log('retour =',retour), (error) => console.log('error =',error))