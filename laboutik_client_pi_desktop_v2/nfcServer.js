import { MTE } from './httpServer/index.js'
import { readConfigFile, writeJson, startBrowser, testNetworkStatus } from './modules/commun.js'
import { env } from './env.js'
import * as os from 'node:os'
import { cors } from './modules/cors.js'
import { checkPrinter, print } from './modules/devices/thermalPrinterTcp.js'

const root = process.cwd()
let refAskTagId = null, clientGlobale = null, appDeviceEmitter = null

// 1 - affiche messages des appels socket.io et leurs méthodes uniquement
// 2 - url et méthodes affiliées
// 10 - tous les logs
const logLevel = env.logLevel

function socketEmit(msg, data) {
  if (clientGlobale !== null) {
    clientGlobale.emit(msg, data)
  }
}

// manage nfc
function manageNfc(msg) {
  let error = ''
  if (msg.errorNfcReader) {
    error = 'Nfc error'
  }
  if (msg.errorNfc) {
    error = 'Nfc error'
  }
  // emet au front les erreurs du nfc
  if (error !== '') {
    socketEmit('nfcMessage', { error })
  }
  // emet au front le status du nfc
  if (msg.status) {
    socketEmit('nfcMessage', msg)
  }
  // emet au front le tagId si demande de tag id référencée
  if (msg.tagId && refAskTagId !== null) {
    socketEmit('nfcMessage', msg)
  }
  // emet au front le tagId de test
  if (msg.tagId && refAskTagId === null) {
    socketEmit('nfcMessage', { testTagId: msg.tagId })
  }
  // console.log("msg =", msg)
}

function initNfcDevice(socket) {
  // console.log('-> initNfcDevice')
  try {
    // modules à importés en fonction du type d'application (pi ou desktop)
    const deviceFiles = {
      desktop: 'acr122u-u9.js',
      pi: 'vma405-rfid-rc522.js'
    }
    const pathDevice = root + '/modules/devices/' + deviceFiles[env.type_app]
    // console.log('pathDevice =', pathDevice)

    if (appDeviceEmitter !== null) {
      appDeviceEmitter.removeListener("nfcMessage", manageNfc)
    }
    import(pathDevice).then(module => {
      const { initNfcReader } = module
      initNfcReader(socket)
    })
  } catch (error) {
    console.log('-> initNfcDevice,', error)
  }
}

async function getNetworkStatus() {
  const networkStatus = await testNetworkStatus()
  socketEmit('networkStatus', networkStatus)
  // console.log('networkStatus =', networkStatus)
}

async function getPrintersStatus() {
  let printersStatus = []
  for (let i = 0; i < env.ipPrinters.length; i++) {
    const ip = env.ipPrinters[i]
    const status = await checkPrinter(ip)
    console.log('-> getPrinterStatus - ip =', ip, '  --  status =', status)
    printersStatus.push({ ip, status })
  }
  socketEmit('printersStatus', printersStatus)
}


async function initApp(socket) {
  // send config file
  const confIle = readConfigFile()
  socketEmit('sendConfigFile', confIle)

  // get network status  
  getNetworkStatus()
  // listen network status
  const intervalId = setInterval(getNetworkStatus, 5000); // 5000 ms = 5 seconds

  // init nfc
  initNfcDevice(socket)

  // imprimante(s)
  getPrintersStatus()
}



function writeConfigFile(req, res, rawBody, headers) {
  // console.log('-> writeConfigFile, rawBody =', rawBody)
  headers["Content-Type"] = "application/json"
  try {
    const result = writeJson(root + '/' + confFileName, rawBody)
    if (result.status === true) {
      res.writeHead(200, headers)
      res.write(JSON.stringify(result))
      res.end()
    } else {
      res.writeHead(400, headers)
      res.write(JSON.stringify(result))
      res.end()
    }
  } catch (error) {
    // writeJson(path, data)
    res.writeHead(400, headers)
    res.write(JSON.stringify({ error }))
    res.end()
  }
}

// encapsulate all errors
try {

  // --- socket.io handler ---
  const socketHandler = (client) => {
    clientGlobale = client
    console.log("Client connecté !")

    clientGlobale.on("frontReady", () => {
      initApp(clientGlobale)
    })

    /*
    clientGlobale.on("demandeTagId", (data) => {
      refAskTagId = data
      console.log("-> demandeTagIdg = " + JSON.stringify(refAskTagId))
    })

    clientGlobale.on("AnnuleDemandeTagId", () => {
      retour = null
    })

    clientGlobale.on("frontStart", () => {
      initNetwork()
      initNfcDevice()
    })
      */

    clientGlobale.on("disconnect", () => {
      console.log("Client déconnecté !!")
    })
  }

  const optionsServer = {
    socketHandler,
    config: {
      PORT: env.PORT,
      HOST: env.HOST,
      // racine du projet = process.cwd()
      PUBLIC: process.cwd() + '/www',
      DEBUG: true,
      logLevel: env.logLevel
    }
  }
  const app = new MTE(optionsServer)

  // ajout du midleware cors
  app.use(cors, {
    origin: '*',
    headers: 'Sentry-trace, Baggage, Access-Control-Allow-Headers, Origin,Accept, X-Requested-With, Content-Type, Access-Control-Request-Method, Access-Control-Request-Headers',
    methods: 'GET,HEAD,PUT,PATCH,POST,DELETE',
    optionsSuccessStatus: 204,
    maxAge: 2592000,
    credentials: true
  })

  // routes

  app.listen((host, port) => {
    console.log(`Lancement du serveur à l'adresse : ${port === 443 ? 'https' : 'http'}://${host}:${port}/`)
    console.log(`Single server version ${app.version} (c) filaos974`)
  })

  // on prod
  //startBrowser(`http://${env.HOST}:${env.PORT}/`)

} catch (error) {
  console.log('error', error)
}
