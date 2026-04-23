# Création de l'application android(apk) 

## Créer votre fichier de conf
- A la racine du projet, créer env.js et modifier le :   
  . type_app: 'cordova', // android 
  . server_pin_code: "http://tibillet.localhost", // votre serveur de pin_code

```bash
cp ./mobile-app/www/env-example.js ./mobile-app/www/env.js
```

## Créer le conteneur docker (environnement de travail cordova)
- dans le dossier docker
```bash
docker compose build
```

## Lancer le conteneur docker
```bash
docker compose up -d
```

## Entrer dans le conteneur docker
```bash
docker exect -it cordova bash
```

## Installer l'application sur mobile, tablette

### Sur le mobile
- Activer le mode développeur
- Activer le débeugage sans fil
- Appairer le mobile au conteneur (appairage par code)
  L'appairage par code donne un ip, port et le code d'appairage à entrer.

### Dans le conteneur

#### Lancer le serveur adb et vérifier les appareils connectés
```bash
adb devices
```

#### Appairage dans le conteneur docker si besoin
```bash
adb pair <ip du mobile>:<port d'appairage>
```

#### Vérifier l'appairage
```bash
adb devices
```
retour
```bash
List of devices attached
adb-DE13P48F10229-39R4ti._adb-tls-connect._tcp  device
```

#### Vérification prérequis (dans mobile-app, application cordova)
```bash
cordova requirements
```

#### Reset projet (pour un build propre)
```bash
./reset_projet
```

#### Installer les plugins du projet et lance un build
```bash
./buildAndroid
```

#### build et installation de l'application sur le mobile, tablette ou émulateur
```bash
./runAndroid
```

## Infos divers
### Création et installaion de l'application sur mobile
```bash
# build debug for only Android
cordova run android --debug
# or build release for only Android
cordova run android --release
```

### debug mobile
```bash
adb devices
```
retour:   
List of devices attached
adb-DE13P48F10229-39R4ti._adb-tls-connect._tcp  device

```bash
clear && adb logcat
clear && adb logcat | grep ConnectivityPlugin
adb -s 192.168.1.10:39173 logcat | grep SunmiPrintHelper
adb logcat | grep SunmiPrintHelper
```


## Attention
- En cas de souci d'installation supprimer l'ancienne application sur le mobile
