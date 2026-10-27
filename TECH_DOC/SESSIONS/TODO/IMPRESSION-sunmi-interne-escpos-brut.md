# Impression — la Sunmi interne reçoit l'ESC/POS brut, une seule traduction du ticket

> **Statut** : idée, spec à écrire. Décision du mainteneur (2026-10-27), après le retour
> « le ticket de l'innerprinter du SUNMI v3 mix ne sort pas la TVA ».
> Pré-requis : aucun côté serveur ; une mise à jour de l'application Android sur tout le parc.

## Le problème, en une phrase
Un ticket est traduit **deux fois, à la main** : en octets ESC/POS (`laboutik/printing/escpos_builder.py`)
pour les imprimantes réseau, cloud et mock, et en commandes JSON
(`laboutik/printing/sunmi_inner.py : ticket_data_to_json_commands`) pour l'imprimante interne des
tablettes Sunmi. Chaque bloc ajouté d'un côté doit l'être de l'autre, et rien ne le garantissait.

## Ce que ça a déjà coûté
Constaté le 2026-10-27, corrigé côté JSON le même jour
(`CHANGELOG/2026-10-27-sunmi-interne-tva-mentions-legales.md`) :
- ventilation TVA, mentions légales, bandeau SIMULATION absents sur la Sunmi interne (exigences LNE 3 et 5) ;
- QR code jamais imprimé : le serveur envoyait `"type": "qrcode"`, le JS attend `"qrCode"`.

Garde-fou en place depuis : un test de parité ligne à ligne
(`tests/pytest/test_ticket_client_imprime.py :
test_la_sunmi_interne_imprime_les_memes_lignes_que_l_imprimante_escpos`). Il attrape un bloc
oublié, **pas** une commande que l'application ne sait pas lire (le cas du QR code).

## Pourquoi deux traductions
L'imprimante interne n'est pas sur le réseau. Seule l'application Android la pilote, via le SDK
Sunmi, exposé au JavaScript de la page par le plugin Cordova local
`laboutik_client_android_v2/cordova_local_plugins/cordova-plugin-sunmi-printer/`.
Ce plugin n'expose que des méthodes de haut niveau (`SunmiPrinterPlugin.kt`) : `printText`,
`setAlign`, `printQr`, `printBarCode`, `printTable`, `printBitmap`, `lineWrap`, `cutPaper`,
`openDrawer`, `autoOutPaper`… **Aucune n'envoie d'octets bruts.**

Le chemin actuel : `SunmiInnerBackend` → channel layer Redis → `PrinterConsumer`
(`wsocket/consumers.py`) → websocket `ws/printer/<uuid>/` → `manageSunmiPrint.js : sunmiInnerPrint()`
→ plugin, commande par commande.

## L'idée
Le SDK embarqué (`com.sunmi:printerlibrary:1.0.23`, `src/android/build-extras.gradle`) a, d'après
la démo officielle Sunmi dont le helper du plugin est tiré, une méthode
`SunmiPrinterService.sendRAWData(byte[], callback)`. **À vérifier dans la 1.0.23** (l'AAR n'a pas
pu être téléchargé le 2026-10-27 : `dl.sunmi.com` injoignable depuis la machine de dev).

Si elle existe :

| Où | Quoi |
|---|---|
| `SunmiPrinterPlugin.kt` + `SunmiPrinterHelper.kt` | action `sendRawData` : reçoit du base64 (Cordova ne transporte que du JSON), décode, appelle `sendRAWData` |
| `www/sunmiPrinterPlugin.js` | la fonction exposée |
| `laboutik/static/js/manageSunmiPrint.js` | commande `{type: "raw", value: <base64>}` |
| `laboutik/printing/sunmi_inner.py` | envoyer le base64 de `build_escpos_from_ticket_data()` — le même builder que réseau, cloud et mock |
| Déploiement | rebuild de l'APK (`./buildAndroid`, voir `laboutik_client_android_v2/readme.md`), réinstallation sur toutes les tablettes |

À terme, `ticket_data_to_json_commands` disparaît : une seule traduction du ticket.

## Les deux risques à traiter dans la spec
1. **Transition.** Une ancienne application ignore une commande de type inconnu (la boucle de
   `sunmiInnerPrint` la saute, sans erreur). Si le serveur n'envoie que du `raw`, les tablettes
   pas encore mises à jour n'impriment **plus rien**. Il faut que l'application annonce ce
   qu'elle sait faire (version, ou capacité « raw » au moment de l'abonnement websocket), et que
   le serveur garde le JSON pour les autres tant que le parc n'est pas à jour.
2. **Rendu.** `escpos_builder` est calé sur les imprimantes cloud et LAN (largeur en points,
   encodage des accents, `✂`, taille du QR code : `module_size=8` pour un papier de 576 points).
   L'imprimante interne d'une V3 Mix (papier plus étroit ?) doit être testée **sur une vraie
   tablette** : accents, largeur des colonnes TVA, QR code, coupe.

## Ce qu'il ne faut pas faire
- Supprimer le chemin JSON avant que tout le parc soit à jour.
- Annoncer « ça marche » sur la foi des tests pytest : ils vérifient les octets et les
  commandes, pas le papier.
