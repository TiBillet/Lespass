const tradData = {
  fr: [
    {"Scan your primary card.": "Scanner votre carte primaire."},
    {"close": "fermer"},
    {"Create a new member.": "Créer un nouveau membre."},
    {"Scan a booking or membership.": "Scanner une réservation ou une adhésion."},
    {"Sales points": "Points de ventes"},
    {"Scanner nfc card.": "Scanner carte nfc."},
    {"Return": "Retour"},
    {"Activate your network.": "Activer votre réseau."},
    {"Enable NFC !": "Activer le NFC !"},
    {"No NFC !": "Pas de NFC !"},
    {"NFC permission is not turned on !": "NFC n’est pas activée !"},
    {"Devices": "Périphériques"},
    {"Network": "Réseau"},
    {"The network is activated !": "Le réseau est activé !"},
    {"Enabled.": "Activé."},
    {"NFC activation time exceeded, restart application !": "Temps d'activation du NFC dépassé, relancer l'application !"},
    {"Error.": "Erreur."},
    {"Camera locked in !": "Caméra bloquée !"},
    {"Camera": "Caméra"},
    {"Network activation time exceeded, restart the application !": "Temps d'activation du réseau dépassé, relancer l'application !"},
    {"Theme": "Thème"}
  ],
  de: [
    {"Scan your primary card.": "Scannen Sie Ihre primäre Karte."},
    {"Welcome to": "Willkommen bei"},
    {hello: "hello"},
    {close: "schließen"},
    {"Create a new member.": "Erstellen Sie ein neues Mitglied."},
    {"Scan a booking or membership.": "Scannen einer Buchung oder Mitgliedschaft."},
    {"Sales points": "Verkaufsstellen"},
    {"Reload cashless card.": "Bargeldlose Karte neu laden."},
    {"Qrcode Ticket Scanner.": "Qrcode Ticket Scanner"},
    {"Scanner nfc card.": "Scanner nfc card."},
    {"Return": "zurück"},
    {"New scan": "Neuen Scan"},
    {"Activate your network.": "Activer votre réseau."},
    {"Enable NFC !": "NFC aktivieren !"},
    {"No NFC !": "Kein NFC !"},
    {"NFC permission is not turned on !": "NFC-Berechtigung ist nicht aktiviert !"},
    {"Devices": "Geräte"},
    {"Network": "Network"},
    {"The network is activated !": "Das Netzwerk ist aktiviert !"},
    {"Enabled.": "Aktiviert."},
    {"NFC activation time exceeded, restart application !": "NFC-Aktivierungszeit überschritten, Anwendung neu starten !"},
    {"Error.": "Fehler."},
    {"Camera locked in !": "Kamera gesperrt !"},
    {"Camera": "Camera"},
    {"Network activation time exceeded, restart the application !": "Netzwerkaktivierungszeit überschritten, Anwendung neu starten!"},
    {"Theme": "Thema"}
  ]
}

let tradOptions = {
  activation: true,
  language: 'fr'
}

export const tradConfig = (options) => {
  if (options === undefined) {
    options = {}
  }
  tradOptions.activation = options.activation === undefined ? true : options.activation
  tradOptions.language = options.language === undefined ? 'fr' : options.language
}

export const trad = (index) => {
  // console.log('2 - tradOptions =', tradOptions)
  if (tradOptions.activation === true) {
    try {
      const data = tradData[tradOptions.language]
      const resultat = data.find(obj => Object.keys(obj)[0] === index)
      return Object.values(resultat)[0]
    } catch (e) {
      return index
    }
  } else {
    return index
  }
}
