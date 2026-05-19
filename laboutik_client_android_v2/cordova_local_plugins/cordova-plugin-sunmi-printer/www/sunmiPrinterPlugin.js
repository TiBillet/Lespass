var exec = require('cordova/exec');

module.exports = {

  // test that the printer is available
  isPrinterAvailable() {
    return new Promise((resolve, reject) => {
      exec(resolve, reject, 'SunmiPrinterPlugin', 'isPrinterAvailable', []);
    });
  },

  // Initialiser le service
  initSunmiPrinterService() {
    return new Promise((resolve, reject) => {
      exec(resolve, reject, 'SunmiPrinterPlugin', 'initSunmiPrinterService', []);
    });
  },

  // Imprimer du texte
  printText(content, size = 24, isBold = false, isUnderLine = false, align = 0) {
    return new Promise((resolve, reject) => {
      exec(resolve, reject, 'SunmiPrinterPlugin', 'printText', [content, size, isBold, isUnderLine, align]);
    });
  },

  // Aligner le texte
  setAlign(align) {
    return new Promise((resolve, reject) => {
      exec(resolve, reject, 'SunmiPrinterPlugin', 'setAlign', [align]);
    });
  },

  // Imprimer un QR code
  printQr(data, modulesize = 8, errorlevel = 0, align = 0) {
    return new Promise((resolve, reject) => {
      exec(resolve, reject, 'SunmiPrinterPlugin', 'printQr', [data, modulesize, errorlevel, align]);
    });
  },

  // Imprimer un code-barres
  printBarCode(data, symbology = 8, height = 162, width = 2, textPosition = 2, align = 0) {
    return new Promise((resolve, reject) => {
      exec(resolve, reject, 'SunmiPrinterPlugin', 'printBarCode', [data, symbology, height, width, textPosition, align]);
    });
  },

  // Imprimer un tableau
  printTable(txts, width, align) {
    return new Promise((resolve, reject) => {
      exec(resolve, reject, 'SunmiPrinterPlugin', 'printTable', [txts, width, align]);
    });
  },

  // Sauter des lignes
  lineWrap(n = 3) {
    return new Promise((resolve, reject) => {
      exec(resolve, reject, 'SunmiPrinterPlugin', 'lineWrap', [n]);
    });
  },

  // Couper le papier
  cutPaper() {
    return new Promise((resolve, reject) => {
      exec(resolve, reject, 'SunmiPrinterPlugin', 'cutPaper', []);
    });
  },

  // Ouvrir le tiroir-caisse
  openDrawer() {
    return new Promise((resolve, reject) => {
      exec(resolve, reject, 'SunmiPrinterPlugin', 'openDrawer', []);
    });
  },

  // Sortie automatique du papier
  autoOutPaper() {
    return new Promise((resolve, reject) => {
      exec(resolve, reject, 'SunmiPrinterPlugin', 'autoOutPaper', []);
    });
  },

  // Vérifier l'état de l'imprimante
  updatePrinterState() {
    return new Promise((resolve, reject) => {
      exec(resolve, reject, 'SunmiPrinterPlugin', 'updatePrinterState', []);
    });
  },

  /**
   * Imprimer un Bitmap à partir d'une image Base64
   * @param {string} base64 
   * @returns 
   */
  printBitmap(base64, width = 384, align = 0) {
    return new Promise((resolve, reject) => {
      exec(resolve, reject, 'SunmiPrinterPlugin', 'printBitmap', [base64, width, align]);
    });
  }
};
