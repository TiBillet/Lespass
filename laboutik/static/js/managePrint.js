/**
 * Sunmi inner printer is on ?
 * @returns 
 */
async function sunmiInnerPrinterIsOn() {
  if (await SunmiPrinterPlugin.initSunmiPrinterService() === 'Printer connected' && await SunmiPrinterPlugin.isPrinterAvailable() === 'enabled') {
    return true
  } else {
    return false
  }
}

async function loadAndConvertImageToB64(url) {
  const load = await new Promise((resolve) => {
    try {
      let img = new Image()
      // Important pour les images cross-origin
      img.crossOrigin = 'anonymous'
      img.src = url
      img.onload = () => {
        let canvas = document.createElement('canvas')
        let ctx = canvas.getContext('2d')
        canvas.height = img.naturalHeight;
        canvas.width = img.naturalWidth;
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        const base64String = canvas.toDataURL('image/png')
        resolve(base64String)
      }
      img.onerror = () => {
        throw new Error("-> loadAndConvertImageToB64 - erreur chargement :", url);
      }
    } catch (error) {
      console.log('-> loadAndConvertImageToB64,', error)
      resolve(null)
    }
  })
  return load
}

/*

autoOutPaper
cutPaper
lineWrap
openDrawer
printBarCode
printBitmap
printQr
printTable
printText(String, 24(taille de base), isBold = Boolean, isUnderLine, align)
setAlign (number)
*/
async function sunmiInnerPrint(printUuid) {
  console.log('-> sunmiInnerPrint - printUuid =', printUuid)
  // initialise le service d'impression de sunmi
  await SunmiPrinterPlugin.initSunmiPrinterService()
  // find current impression in queue
  const currentPrint = sunmiPrintQueue.find(imp => imp.printUuid === printUuid)

  // commandes à imprimer
  for (const com of currentPrint.content) {
    // alignement 0 = gauche 1=centre 2=droite
    let align = 0
    if (com?.align === 'left') {
      align = 0
    }
    if (com?.align === 'center') {
      align = 1
    }
    if (com?.align === 'right') {
      align = 2
    }

    // text
    if (com.type === 'text') {
      const bold = com?.bold === undefined ? false : com.bold
      const size = com?.size === undefined ? 1 : com.size
      const text = com?.value === undefined ? '' : com.value
      const underLine = com?.underLine === undefined ? false : com.underLine
      await SunmiPrinterPlugin.printText(text + '\r\n', 24 * size, bold, underLine, align)
    }

    // code barre
    if (com.type === "qrCode") {
      const modulesize = com?.modulesize === undefined ? 8 : com.modulesize
      const errorlevel = com?.errorlevel === undefined ? 0 : com.errorlevel
      await SunmiPrinterPlugin.printQr(com.value, modulesize, errorlevel, align)
    }

    // qr code
    if (com.type === "barCode") {
      const symbology = com?.symbology === undefined ? 8 : com.symbology
      const height = com?.height === undefined ? 162 : com.height
      const width = com?.width === undefined ? 2 : com.width
      const textPosition = com?.textPosition === undefined ? 2 : com.textPosition
      await SunmiPrinterPlugin.printBarCode(com.value, symbology, height, width, textPosition, align)
    }

    // image
    if (com.type === "image") {
      try {
        const image = await loadAndConvertImageToB64(com.value)
        const size = com?.size === undefined ? 24 : com.size
        await SunmiPrinterPlugin.printBitmap(image, size, align)
      } catch (error) {
        console.log('imprimer image :', error);

      }
    }

    if (com.type === 'cut') {
      await SunmiPrinterPlugin.lineWrap(3)
      await SunmiPrinterPlugin.cutPaper()
    }
  }
}

/**
 * Initialise une connexion websocket si printer uuid
 */
async function initWebsocket() {
  console.log('-> initWebsocket - printer =', state.printer)
  const sunmiInnerPrinterOK = await sunmiInnerPrinterIsOn()
  console.log('sunmiInnerPrinterOK =', sunmiInnerPrinterOK)


  if (state?.printer?.uuid) {
    const server = `wss://${window.location.host}/ws/printer/${state.printer.uuid}/`

    // ---- websocket handler ----
    async function wsHandlerMessag(dataString) {
      // console.log('-> ws, dataString =', dataString)
      try {
        const data = JSON.parse(dataString)
        // console.log('-> wsHandlerMessag - data =', data)
        // message d'impression
        if (data.action === 'print') {
          // create print sunmi queue
          if (window.sunmiPrintQueue === undefined) {
            window.sunmiPrintQueue = []
          }
          // sunmi inner printer
          if (sunmiInnerPrinterOK === true) {
            const options = { printUuid: crypto.randomUUID(), content: data.commands }
            sunmiPrintQueue.push(options)
            // imprimer data
            await sunmiInnerPrint(options.printUuid)
          }
        }
      } catch (error) {
        console.log("-> wsHandlerMessag, erreur :", error)
      }
    }

    // TODO: changer la route si besoin
    window.wsTerminal = {
      socket: new WebSocket(server),
      on: false
    }

    // Connection ws ok
    wsTerminal.socket.addEventListener("open", (event) => {
      console.log("-> connection ws -", new Date())
      wsTerminal.on = true
    })

    // écoute data ws
    wsTerminal.socket.addEventListener("message", function (event) {
      // aiguillage en fonction du message
      wsHandlerMessag(event.data)
    })

    // connection hs
    wsTerminal.socket.addEventListener("close", (event) => {
      console.log("The connection has been closed successfully.");
      // supprime le WebSocket
      wsTerminal = null
    })
  }
}


document.addEventListener('deviceready', async () => {
  try {
    await initWebsocket()
  } catch (error) {
    console.log('-> initWebsocket,', error);

  }

})
